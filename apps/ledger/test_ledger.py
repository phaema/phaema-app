# SPDX-License-Identifier: AGPL-3.0-or-later
import csv
import io
from datetime import date
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.core.models import ModuleSettings
from apps.leases.models import Lease, Party
from apps.ledger import billing, finance
from apps.ledger.importing import ReceiptWorkbook
from apps.ledger.models import Charge, ExportBatch, Receipt
from apps.properties.models import Property

D = Decimal


@pytest.fixture
def ledger_on(db):
    s = ModuleSettings.load()
    s.rent_ledger_enabled, s.invoice_prefix, s.next_invoice_number = True, "INV", 1
    s.save()
    return s


@pytest.fixture
def tenant(db):
    return Party.objects.create(name="Tenant Ltd", party_type="company", finance_customer_ref="C1")


def make_lease(tenant, ref="L1", start=date(2025, 12, 25), end=date(2030, 12, 31), rent="12000", freq="quarter_days",
               vat=False, **extra):
    unit = Property.objects.create(reference=f"P-{ref}", name=f"Unit {ref}", property_type="unit")
    lease = Lease.objects.create(reference=ref, agreement_type="lease", counterparty=tenant, term_start=start,
                                 term_end=end, annual_rent=D(rent), rent_frequency=freq, vat_chargeable=vat, **extra)
    lease.properties.add(unit)
    return lease


def test_quarter_day_lease_starting_mid_quarter_gets_a_part_period(ledger_on, tenant):
    lease = make_lease(tenant, start=date(2026, 2, 10), vat=True)
    periods = billing.rent_periods(lease, date(2026, 1, 1), date(2026, 6, 30))
    assert periods == [(date(2026, 2, 10), date(2026, 3, 24), date(2026, 2, 10), False),
                       (date(2026, 3, 25), date(2026, 6, 23), date(2026, 3, 25), True),
                       (date(2026, 6, 24), date(2026, 9, 28), date(2026, 6, 24), True)]
    charges = billing.proposed_charges(date(2026, 1, 1), date(2026, 6, 30))
    part, full = charges[0], charges[1]
    assert part.net == (D("12000") * 43 / 365).quantize(D("0.01")) and "part period" in part.description
    assert full.net == D("3000.00") and full.vat == D("600.00") and full.gross == D("3600.00")


def test_last_period_cut_short_by_expiry_is_apportioned(ledger_on, tenant):
    lease = make_lease(tenant, start=date(2020, 3, 25), end=date(2026, 5, 31), freq="quarter_days")
    (start, end, due, full), = billing.rent_periods(lease, date(2026, 3, 1), date(2026, 4, 30))
    assert (start, end, full) == (date(2026, 3, 25), date(2026, 5, 31), False)
    assert billing.period_rent(lease, start, end, full) == (D("12000") * 68 / 365).quantize(D("0.01"))


def test_monthly_and_peppercorn_and_held_leases(ledger_on, tenant):
    make_lease(tenant, "M1", start=date(2026, 1, 15), rent="6000", freq="monthly")
    make_lease(tenant, "PC", freq="peppercorn", rent="0")
    make_lease(tenant, "IN", direction=Lease.Direction.IN)
    charges = billing.proposed_charges(date(2026, 1, 1), date(2026, 3, 31))
    assert {c.lease.reference for c in charges} == {"M1"}
    assert [c.due_date for c in charges] == [date(2026, 1, 15), date(2026, 2, 15), date(2026, 3, 15)]
    assert all(c.net == D("500.00") for c in charges)


def test_demand_run_numbers_invoices_and_never_charges_twice(ledger_on, tenant):
    make_lease(tenant)
    run = billing.issue_run(date(2026, 1, 1), date(2026, 6, 30), date(2026, 1, 1))
    assert [c.invoice_number for c in run.charges.order_by("due_date")] == ["INV000001", "INV000002"]
    assert billing.issue_run(date(2026, 1, 1), date(2026, 6, 30)) is None
    again = billing.issue_run(date(2026, 1, 1), date(2026, 9, 30))
    assert again.charges.count() == 1 and again.charges.get().invoice_number == "INV000003"


def test_finance_raises_invoices_mode(ledger_on, tenant):
    ledger_on.invoicing = ModuleSettings.Invoicing.FINANCE
    ledger_on.save()
    make_lease(tenant)
    run = billing.issue_run(date(2026, 3, 1), date(2026, 3, 31))
    charge = run.charges.get()
    assert charge.invoice_number == "" and charge.reference == f"PHC{charge.pk:06d}"


def test_account_pays_oldest_debt_first_and_ages_arrears(ledger_on, tenant):
    lease = make_lease(tenant)
    billing.issue_run(date(2026, 1, 1), date(2026, 9, 30), date(2026, 1, 1))  # 25/3, 24/6, 29/9: £3,000 each
    Receipt.objects.create(lease=lease, received_on=date(2026, 4, 1), amount=D("4000"), payment_reference="R1")
    acc = billing.account(lease, today=date(2026, 10, 15))
    assert acc.balance == D("5000")
    owed = [line.outstanding for line in acc.lines if line.kind == "charge"]
    assert owed == [D("0"), D("2000"), D("3000")]
    assert acc.overdue == D("5000")
    assert dict(acc.aged) == {"1–30 days": D("3000"), "31–60 days": D("0"), "61–90 days": D("0"),
                              "Over 90 days": D("2000")}


def test_credit_notes(ledger_on, tenant):
    lease = make_lease(tenant, vat=True)
    charge = billing.issue_run(date(2026, 3, 1), date(2026, 3, 31)).charges.get()  # £3,600 gross
    note = billing.credit(charge, "rent free agreed", D("1200"))
    assert (note.gross, note.net, note.vat) == (D("-1200.00"), D("-1000.00"), D("-200.00"))
    assert note.invoice_number == "INV000002" and note.credit_for == charge
    with pytest.raises(ValueError):
        billing.credit(charge, "too much", D("2400.01"))
    billing.credit(charge, "rest")
    assert billing.account(lease, today=date(2026, 4, 1)).balance == 0


def _receipts_file(rows):
    text = "Payment reference,Date received,Amount,Lease reference,Invoice reference,Customer reference\n"
    text += "".join(",".join(r) + "\n" for r in rows)
    return SimpleUploadedFile("receipts.csv", text.encode())


def test_receipt_import_matching(ledger_on, tenant):
    lease = make_lease(tenant)
    other = Party.objects.create(name="Two Leases Ltd", party_type="company", finance_customer_ref="C2")
    make_lease(other, "L2")
    make_lease(other, "L3")
    charge = billing.issue_run(date(2026, 3, 1), date(2026, 3, 31)).charges.get(lease=lease)
    upload = _receipts_file([
        ["A1", "26/03/2026", "1000", "L1", "", ""],
        ["A2", "27/03/2026", "1000", "", charge.invoice_number, ""],
        ["A3", "28/03/2026", "500", "", f"PHC{charge.pk:06d}", ""],
        ["A4", "29/03/2026", "500", "", "", "C1"],
        ["A5", "29/03/2026", "500", "", "", "C2"],
        ["A6", "29/03/2026", "0", "L1", "", ""],
        ["A7", "29/03/2026", "10", "", "", ""],
    ])
    result, _p = ReceiptWorkbook().validate(upload)
    errors = {r.number: " ".join(r.errors) for r in result.rows}
    assert not any(errors[n] for n in (2, 3, 4, 5))
    assert "more than one agreement" in errors[6]
    assert "cannot be £0" in errors[7]
    assert "Cannot tell which agreement" in errors[8]


def test_receipt_import_saves_and_is_safe_to_repeat(ledger_on, tenant):
    lease = make_lease(tenant)
    rows = [["B1", "26/03/2026", "3000.00", "L1", "", ""], ["B2", "01/04/2026", "-50", "L1", "", ""]]
    workbook = ReceiptWorkbook()
    result, prepared = workbook.validate(_receipts_file(rows))
    assert result.ok
    workbook.apply(prepared)
    assert lease.receipts.count() == 2 and sum(r.amount for r in lease.receipts.all()) == D("2950")
    result, _p = ReceiptWorkbook().validate(_receipts_file(rows))
    assert [r.action for r in result.rows] == ["unchanged", "unchanged"]


def test_finance_export_batches(ledger_on, tenant):
    ledger_on.rent_income_code = "EST-1"
    ledger_on.save()
    lease = make_lease(tenant, vat=True)
    run = billing.issue_run(date(2026, 1, 1), date(2026, 6, 30))
    billing.credit(run.charges.first(), "error")
    batch = finance.create_batch()
    assert batch.charges.count() == 3 and finance.create_batch() is None
    response = finance.download(batch, "csv", ModuleSettings.load())
    rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert [r["Record type"] for r in rows] == ["Invoice", "Invoice", "Credit note"]
    assert rows[0]["Customer reference"] == "C1" and rows[0]["Income code"] == "EST-1"
    assert rows[0]["VAT code"] == "S" and rows[0]["Lease reference"] == lease.reference
    assert rows[2]["Credit for"] == rows[0]["Invoice number"]
    billing.issue_run(date(2026, 7, 1), date(2026, 9, 30))
    assert finance.create_batch().charges.count() == 1 and ExportBatch.objects.count() == 2


def test_pages_and_permissions(client, make_user, ledger_on, tenant):
    lease = make_lease(tenant)
    viewer, admin = make_user("viewer", "Viewers"), make_user("admin", "Administrators")
    client.force_login(viewer)
    for url in ("/rents/", "/rents/arrears/", "/rents/receipts/", "/rents/exports/", f"/rents/accounts/{lease.pk}/"):
        assert client.get(url).status_code == 200, url
    assert client.get("/rents/runs/new/").status_code == 403
    assert client.post("/rents/exports/").status_code == 403
    client.force_login(admin)
    preview = client.get("/rents/runs/new/", {"due_from": "2026-01-01", "due_to": "2026-03-31"})
    assert len(preview.context["charges"]) == 1
    done = client.post("/rents/runs/new/", {"due_from": "2026-01-01", "due_to": "2026-03-31", "issue_date": "2026-01-01",
                                            "confirm": "1"})
    assert done.status_code == 302 and lease.charges.count() == 1
    charge = lease.charges.first()
    client.post(f"/rents/charges/{charge.pk}/credit/", {"amount": "100", "reason": "goodwill"})
    assert lease.charges.filter(kind="credit", gross=D("-100")).exists()
    client.post(f"/rents/charges/{charge.pk}/credit/", {"amount": "100", "reason": ""})
    assert lease.charges.filter(kind="credit").count() == 1
    assert "Rent account" in client.get(lease.get_absolute_url()).content.decode()
    assert "Rent arrears" in client.get("/").content.decode()
    assert client.get("/import/receipts/").status_code == 200


def test_switched_off(client, make_user, db):
    client.force_login(make_user("viewer", "Viewers"))
    response = client.get("/rents/")
    assert response.status_code == 404 and b"switched off" in response.content
    assert client.get("/import/").status_code in (200, 403)
    assert b"Rents</a>" not in client.get("/").content


def test_demo_ledger(db):
    from django.core.management import call_command

    call_command("load_demo_data", verbosity=0)
    assert Charge.objects.filter(lease__reference__startswith="DL-").exists()
    assert billing.arrears_summary()["count"] >= 1
    call_command("load_demo_data", "--reset", verbosity=0)
    assert Charge.objects.filter(lease__reference__startswith="DL-").exists()
