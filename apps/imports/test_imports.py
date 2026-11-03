# SPDX-License-Identifier: AGPL-3.0-or-later
import io
from datetime import date
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import Workbook, load_workbook

from apps.imports.sheets import LeaseSheet, LeaseWorkbook, PartySheet, PartyWorkbook
from apps.leases.models import BreakOption, Lease, LeaseEvent, Party
from apps.properties.models import Property


@pytest.fixture
def admin(make_user):
    return make_user("admin1", "Administrators")


@pytest.fixture
def units(db):
    return [Property.objects.create(reference=f"U{i}", name=f"Unit {i}", property_type="unit") for i in (1, 2)]


def _book(sheets):
    """sheets: {name: (columns, [rows])} → an uploaded .xlsx"""
    wb = Workbook()
    wb.remove(wb.active)
    for name, (headings, rows) in sheets.items():
        ws = wb.create_sheet(name)
        ws.append(headings)
        for row in rows:
            ws.append(row)
    out = io.BytesIO()
    wb.save(out)
    return SimpleUploadedFile("data.xlsx", out.getvalue())


def _headings(sheet_cls, fields):
    return [next(c.heading for c in sheet_cls.columns if c.field == f) for f in fields]


LEASE_FIELDS = ["reference", "counterparty", "properties", "agreement_type", "term_start", "term_end", "annual_rent",
                "review_basis", "next_review_date"]


def test_templates_open_with_expected_sheets(admin, client):
    client.force_login(admin)
    for key, sheets in (("leases", ["Parties", "Leases", "Breaks", "Guidance"]), ("parties", ["Parties", "Guidance"])):
        response = client.get(f"/import/{key}/template.xlsx")
        assert response.status_code == 200
        wb = load_workbook(io.BytesIO(response.content))
        assert [s for s in wb.sheetnames if s != "Lists"] == sheets


def test_lease_workbook_creates_parties_leases_and_breaks(units):
    upload = _book({
        "Parties": (["Name", "Type", "Email"], [["New Tenant Ltd", "Company", "a@example.org"]]),
        "Leases": (_headings(LeaseSheet, LEASE_FIELDS),
                   [["IMP-1", "New Tenant Ltd", "U1; U2", "Lease", date(2024, 3, 25), "24/03/2034", "12,500",
                     "Open market, upwards only", "25/03/2029"]]),
        "Breaks": (["Lease reference", "Break date", "Exercisable by", "Notice (months)"],
                   [["IMP-1", "25/03/2029", "Tenant only", 6]]),
    })
    workbook = LeaseWorkbook()
    result, prepared = workbook.validate(upload)
    assert result.ok, [r.errors for r in result.rows]
    assert [s[1:] for s in result.summary()] == [(1, 0, 0), (1, 0, 0), (1, 0, 0)]
    workbook.apply(prepared)
    lease = Lease.objects.get(reference="IMP-1")
    assert lease.counterparty.name == "New Tenant Ltd"
    assert set(lease.properties.values_list("reference", flat=True)) == {"U1", "U2"}
    assert lease.annual_rent == Decimal("12500") and lease.term_end == date(2034, 3, 24)
    assert lease.rent_schedule.count() == 1
    assert BreakOption.objects.get(lease=lease).notice_months == 6
    # Key dates were generated from the imported terms.
    assert LeaseEvent.objects.filter(lease=lease, event_type="break").exists()
    assert LeaseEvent.objects.filter(lease=lease, event_type="review").exists()


def test_reimport_is_unchanged_then_updates(units):
    party = Party.objects.create(name="Tenant Ltd", party_type="company")
    lease = Lease.objects.create(reference="L1", agreement_type="lease", counterparty=party,
                                 term_start=date(2020, 1, 1), annual_rent=Decimal("1000"))
    lease.properties.add(units[0])
    same = _book({"Leases": (["Reference", "Tenant or landlord", "Premises", "Permitted use"],
                             [["L1", "Tenant Ltd", "U1", ""]])})
    result, _p = LeaseWorkbook().validate(same)
    assert result.ok and result.rows[0].action == "unchanged"
    changed = _book({"Leases": (["Reference", "Tenant or landlord", "Premises", "Permitted use"],
                                [["L1", "Tenant Ltd", "U2", "Offices"]])})
    workbook = LeaseWorkbook()
    result, prepared = workbook.validate(changed)
    assert result.rows[0].action == "update" and set(result.rows[0].changed) == {"Premises", "Permitted use"}
    workbook.apply(prepared)
    lease.refresh_from_db()
    assert lease.permitted_use == "Offices"
    assert list(lease.properties.values_list("reference", flat=True)) == ["U2"]


def test_problems_are_reported_and_nothing_saved(units):
    Party.objects.create(name="Tenant Ltd", party_type="company")
    upload = _book({
        "Leases": (_headings(LeaseSheet, LEASE_FIELDS), [
            ["BAD-1", "Nobody Ltd", "U1", "Lease", "25/03/2024", "", "", "", ""],
            ["BAD-2", "Tenant Ltd", "NOPE", "Lease", "not a date", "", "", "", ""],
            ["OK-1", "Tenant Ltd", "U1", "Lease", "25/03/2024", "24/03/2020", "", "", ""],
            ["OK-1", "Tenant Ltd", "U1", "Lease", "25/03/2024", "", "", "", ""],
        ]),
        "Breaks": (["Lease reference", "Break date", "Exercisable by"], [["MISSING", "01/01/2030", "Tenant only"]]),
    })
    result, _prepared = LeaseWorkbook().validate(upload)
    assert not result.ok
    errors = {(r.sheet, r.number): " ".join(r.errors) for r in result.rows}
    assert "no party called Nobody Ltd" in errors[("Leases and licences", 2)]
    assert "no property with reference NOPE" in errors[("Leases and licences", 3)]
    assert "not a date" in errors[("Leases and licences", 3)]
    assert "expiry date must be after" in errors[("Leases and licences", 4)]
    assert "repeats row 4" in errors[("Leases and licences", 5)]
    assert "no agreement with reference MISSING" in errors[("Break options", 2)]
    assert not Lease.objects.filter(reference__in=["BAD-1", "OK-1"]).exists()


def test_rent_change_on_scheduled_lease_is_refused(units):
    party = Party.objects.create(name="Tenant Ltd", party_type="company")
    lease = Lease.objects.create(reference="L1", agreement_type="lease", counterparty=party,
                                 term_start=date(2020, 1, 1), annual_rent=Decimal("1000"))
    lease.properties.add(units[0])
    upload = _book({"Leases": (["Reference", "Tenant or landlord", "Annual rent"], [["L1", "Tenant Ltd", "2000"]])})
    result, _p = LeaseWorkbook().validate(upload)
    assert "rent schedule" in " ".join(result.rows[0].errors)


def test_party_csv_matches_by_name_and_finance_reference(db):
    Party.objects.create(name="Old Name Ltd", party_type="company", finance_customer_ref="C123")
    Party.objects.create(name="Same Name", party_type="company")
    csv_text = ("Name,Type,Finance customer reference,Phone\n"
                "New Name Ltd,,C123,\n"
                "same name,,,01632 960001\n"
                "Brand New,Charity or community group,,\n"
                "Missing Type,,,\n")
    upload = SimpleUploadedFile("parties.csv", csv_text.encode("utf-8-sig"))
    result, _p = PartyWorkbook().validate(upload)
    actions = [(r.action, bool(r.errors)) for r in result.rows]
    assert actions == [("update", False), ("update", False), ("create", False), ("create", True)]
    assert PartySheet.label == result.rows[0].sheet


def test_upload_preview_and_confirm(client, admin, units):
    client.force_login(admin)
    assert client.get("/import/").status_code == 200
    assert client.get("/import/leases/").status_code == 200
    assert client.get("/import/nothing/").status_code == 404
    upload = _book({"Parties": (["Name", "Type"], [["Web Tenant", "Company"]])})
    preview = client.post("/import/parties/", {"file": upload})
    assert preview.status_code == 200 and preview.context["result"].ok
    assert not Party.objects.filter(name="Web Tenant").exists()
    done = client.post("/import/parties/", {"confirm": "1", "token": preview.context["token"]})
    assert done.status_code == 302
    assert Party.objects.filter(name="Web Tenant").exists()


def test_import_is_for_administrators_only(client, make_user, db):
    client.force_login(make_user("surv", "Surveyors"))
    assert client.get("/import/").status_code == 403
    assert client.get("/import/leases/template.xlsx").status_code == 403
