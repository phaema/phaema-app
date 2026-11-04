# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import date
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.core.models import ModuleSettings
from apps.leases.models import Lease, Party
from apps.ledger import billing
from apps.ledger.models import Charge
from apps.properties.models import Property
from apps.servicecharges import apportion
from apps.servicecharges.importing import ExpenditureWorkbook
from apps.servicecharges.models import BudgetLine, CostHeading, Expenditure, Schedule, ScheduleMember, ScheduleYear

D = Decimal


@pytest.fixture
def estate(db):
    """An estate of four units: 100, 100, 200 and 100 m². Units 1–3 are let; unit 4 is empty."""
    s = ModuleSettings.load()
    s.rent_ledger_enabled = s.service_charges_enabled = True
    s.save()
    root = Property.objects.create(reference="E", name="Estate", property_type="estate")
    units = [Property.objects.create(reference=f"U{i}", name=f"Unit {i}", property_type="unit", parent=root,
                                     nia_sqm=D(a)) for i, a in enumerate(["100", "100", "200", "100"], start=1)]
    tenant = Party.objects.create(name="Tenant Ltd", party_type="company")
    leases = []
    for i, unit in enumerate(units[:3], start=1):
        lease = Lease.objects.create(reference=f"L{i}", agreement_type="lease", counterparty=tenant,
                                     term_start=date(2024, 12, 25), term_end=date(2035, 12, 24),
                                     annual_rent=D("10000"), rent_frequency="quarter_days")
        lease.properties.add(unit)
        leases.append(lease)
    schedule = Schedule.objects.create(name="Estate services")
    schedule.properties.add(root)
    members = [ScheduleMember.objects.create(schedule=schedule, lease=lease) for lease in leases]
    year = ScheduleYear.objects.create(schedule=schedule, start=date(2025, 4, 1), end=date(2026, 3, 31),
                                       status=ScheduleYear.Status.APPROVED)
    BudgetLine.objects.create(year=year, heading=CostHeading.objects.get(code="CLN"), amount=D("10000"))
    return {"schedule": schedule, "year": year, "leases": leases, "members": members, "units": units}


def test_shares_by_area_with_council_bearing_empty_units(estate):
    share_list, total, void = apportion.shares(estate["schedule"])
    assert total == D("500")
    assert [s.share for s in share_list] == [D("0.2"), D("0.2"), D("0.4")]
    assert void == D("0.2")


def test_fixed_and_equal_bases(estate):
    schedule = estate["schedule"]
    schedule.basis = Schedule.Basis.EQUAL
    schedule.save()
    assert [s.share for s in apportion.shares(schedule)[0]] == [D("0.25")] * 3
    schedule.basis = Schedule.Basis.FIXED
    schedule.save()
    ScheduleMember.objects.filter(pk=estate["members"][0].pk).update(fixed_percentage=D("50"))
    assert apportion.shares(schedule)[0][0].share == D("0.5")


def test_on_account_demands_follow_rent_dates_and_split_at_year_end(estate):
    charges = apportion.proposed_service_charges(date(2025, 3, 1), date(2025, 12, 31), date(2025, 3, 1), D("20"))
    first = [c for c in charges if c.lease.reference == "L1"]
    # The 25 March 2025 quarter is split: 1 April onwards falls in the approved 2025/26 year; the days
    # before it fall in no approved year, so nothing is charged for them.
    assert [(c.period_start, c.due_date) for c in first] == [
        (date(2025, 4, 1), date(2025, 3, 25)), (date(2025, 6, 24), date(2025, 6, 24)),
        (date(2025, 9, 29), date(2025, 9, 29)), (date(2025, 12, 25), date(2025, 12, 25))]
    assert first[1].net == D("500.00")  # £10,000 × 20% ÷ 4
    assert first[0].net == (D("2000") * 84 / 365).quantize(D("0.01"))  # 1 April to 23 June
    assert all(c.vat == 0 for c in first)


def test_demand_run_includes_service_and_never_charges_twice(estate):
    run = billing.issue_run(date(2025, 6, 1), date(2025, 6, 30))
    kinds = sorted(run.charges.values_list("kind", flat=True))
    assert kinds == ["rent"] * 3 + ["service"] * 3
    assert billing.issue_run(date(2025, 6, 1), date(2025, 6, 30)) is None
    only_rent = billing.issue_run(date(2025, 9, 1), date(2025, 9, 30), rent=True, service=False)
    assert set(only_rent.charges.values_list("kind", flat=True)) == {"rent"}


def test_reconciliation_with_cap_and_part_year(estate):
    year, members = estate["year"], estate["members"]
    heading = CostHeading.objects.get(code="CLN")
    Expenditure.objects.create(year=year, heading=heading, spent_on=date(2025, 6, 1), description="Cleaning",
                               amount=D("12000"))
    members[1].annual_cap = D("1000")
    members[1].save()
    lease3 = estate["leases"][2]
    lease3.term_start = date(2025, 10, 1)  # in force for 182 of 365 days
    lease3.save()
    billing.issue_run(date(2025, 3, 1), date(2026, 3, 31), date(2025, 3, 1), service=True, rent=False)
    recon = apportion.reconcile(year)
    l1, l2, l3 = recon.lines
    assert l1.due == D("2400.00")  # 20% of £12,000
    assert l2.due == D("1000.00") and l2.capped
    assert l3.days == 182 and l3.due == (D("12000") * D("0.4") * 182 / 365).quantize(D("0.01"))
    assert recon.council == recon.actual - recon.recovered
    made = apportion.finalise(year, date(2026, 5, 1))
    year.refresh_from_db()
    assert year.status == ScheduleYear.Status.RECONCILED
    assert {c.lease.reference: c.net for c in made} == {line.share.member.lease.reference: line.balance
                                                         for line in recon.lines if line.balance}
    assert all(c.invoice_number for c in made) and all(c.period_start is None for c in made)


def test_finance_export_uses_service_charge_income_code(estate):
    s = ModuleSettings.load()
    s.rent_income_code, s.service_charge_income_code = "RENT-1", "SC-1"
    s.save()
    billing.issue_run(date(2025, 6, 1), date(2025, 6, 30))
    from apps.ledger import finance

    batch = finance.create_batch()
    response = finance.download(batch, "csv", ModuleSettings.load())
    text = response.content.decode("utf-8-sig")
    assert text.count("RENT-1") == 3 and text.count("SC-1") == 3


def test_expenditure_import(estate):
    rows = ("Schedule,Date,Heading,Supplier,Description,Invoice reference,Amount\n"
            "Estate services,15/05/2025,CLN,Clean Co,May cleaning,C-1,800\n"
            "estate services,15/06/2025,Cleaning,Clean Co,June cleaning,C-2,820\n"
            "Estate services,15/05/2027,CLN,Clean Co,No year,C-3,10\n"
            "Nowhere,15/05/2025,CLN,,Bad schedule,,10\n"
            "Estate services,15/05/2025,Nonsense,,Bad heading,,10\n")
    workbook = ExpenditureWorkbook()
    result, prepared = workbook.validate(SimpleUploadedFile("spend.csv", rows.encode()))
    errors = {r.number: " ".join(r.errors) for r in result.rows}
    assert not errors[2] and not errors[3]
    assert "no service charge year" in errors[4]
    assert "no service charge schedule" in errors[5]
    assert "not a cost heading" in errors[6]
    good = "\n".join(rows.splitlines()[:3]) + "\n"
    workbook = ExpenditureWorkbook()
    result, prepared = workbook.validate(SimpleUploadedFile("spend.csv", good.encode()))
    workbook.apply(prepared)
    assert apportion.actual_total(estate["year"]) == D("1620")
    result, _p = ExpenditureWorkbook().validate(SimpleUploadedFile("spend.csv", good.encode()))
    assert [r.action for r in result.rows] == ["unchanged", "unchanged"]


def test_pages_and_permissions(client, make_user, estate):
    year, member = estate["year"], estate["members"][0]
    client.force_login(make_user("viewer", "Viewers"))
    for url in ("/service-charges/", estate["schedule"].get_absolute_url(), year.get_absolute_url(),
                f"/service-charges/years/{year.pk}/statement/{member.pk}/"):
        assert client.get(url).status_code == 200, url
    assert client.get(f"/service-charges/years/{year.pk}/reconcile/").status_code == 403
    admin = make_user("admin", "Administrators")
    client.force_login(admin)
    assert client.get(f"/service-charges/years/{year.pk}/reconcile/").status_code == 200
    client.post(f"/service-charges/years/{year.pk}/reconcile/")  # the demo year has ended
    year.refresh_from_db()
    assert year.status == ScheduleYear.Status.RECONCILED
    draft = ScheduleYear.objects.create(schedule=estate["schedule"], start=date(2026, 4, 1), end=date(2027, 3, 31))
    client.post(f"/service-charges/years/{draft.pk}/approve/")
    draft.refresh_from_db()
    assert draft.status == ScheduleYear.Status.DRAFT  # no budget yet
    assert "Service charges" in client.get("/").content.decode()


def test_switched_off(client, make_user, db):
    client.force_login(make_user("viewer", "Viewers"))
    response = client.get("/service-charges/")
    assert response.status_code == 404 and b"switched off" in response.content


def test_demo(db):
    from django.core.management import call_command

    call_command("load_demo_data", verbosity=0)
    assert Charge.objects.filter(kind="service").exists()
    year = ScheduleYear.objects.filter(schedule__name__startswith="Riverside").order_by("start").first()
    assert apportion.reconcile(year).actual > 0
    call_command("load_demo_data", "--reset", verbosity=0)
    assert Schedule.objects.count() == 2  # Riverside and Northfield Business Park


# ------------------------------------------------------------------ RICS 2nd edition additions

def test_income_and_non_recoverable_costs(estate):
    year = estate["year"]
    h = {c.code: c for c in CostHeading.objects.all()}
    Expenditure.objects.create(year=year, heading=h["CLN"], spent_on=date(2025, 6, 1), description="Cleaning",
                               amount=D("10000"))
    Expenditure.objects.create(year=year, heading=h["INC"], spent_on=date(2026, 3, 1), description="Interest",
                               amount=D("500"), kind="income")
    Expenditure.objects.create(year=year, heading=h["ROAD"], spent_on=date(2026, 3, 1), description="Upgrade",
                               amount=D("4000"), recoverable=False)
    recon = apportion.reconcile(year)
    assert (recon.costs, recon.income, recon.actual, recon.non_recoverable) == (D("10000"), D("500"), D("9500"),
                                                                                 D("4000"))
    assert recon.lines[0].due == D("1900.00")  # 20% of £9,500
    assert [h.code for h, _b, _a in apportion.by_heading(year)] == ["CLN"]


def test_matrix_rows_match_reconciliation_and_are_kept(estate):
    year = estate["year"]
    h = {c.code: c for c in CostHeading.objects.all()}
    for code, amount in (("CLN", "7000.01"), ("SEC", "3333.33")):
        Expenditure.objects.create(year=year, heading=h[code], spent_on=date(2025, 6, 1), description=code,
                                   amount=D(amount))
    Expenditure.objects.create(year=year, heading=h["INC"], spent_on=date(2025, 6, 1), description="Rebate",
                               amount=D("100"), kind="income")
    estate["members"][1].annual_cap = D("500")
    estate["members"][1].save()
    m = apportion.matrix(year)
    assert m.basis == "actual" and m.headings == ["Cleaning", "Security", "Income and credits"]
    recon = apportion.reconcile(year)
    assert [D(r[4]) for r in m.rows[:-1]] == [line.due for line in recon.lines]
    assert sum(D(r[4]) for r in m.rows) == recon.actual  # leases + council = everything
    apportion.finalise(year, date(2026, 5, 1))
    year.refresh_from_db()
    Expenditure.objects.create(year=year, heading=h["CLN"], spent_on=date(2025, 7, 1), description="Late",
                               amount=D("999"))
    assert apportion.matrix(year).rows == m.rows  # fixed at reconciliation


def test_deadlines(estate):
    from apps.servicecharges import deadlines

    year = estate["year"]  # 1 April 2025 to 31 March 2026
    assert (year.budget_due, year.statements_due) == (date(2025, 3, 1), date(2026, 7, 31))
    found = {d.what: d for d in deadlines.upcoming(today=date(2026, 5, 1))}
    assert "Issue the 2025/26 year-end statements" in found
    assert any("budget for the year from 01/04/2026" in w for w in found)
    year.statements_issued_on = date(2026, 6, 30)
    year.save()
    assert not any("year-end statements" in d.what for d in deadlines.upcoming(today=date(2026, 5, 1)))


def test_weekly_deadline_email(estate, make_user, mailoutbox):
    from apps.servicecharges import deadlines

    make_user("admin", "Administrators", email="admin@example.org")
    assert deadlines.send_weekly(today=date(2026, 5, 5)) == 0  # a Tuesday
    assert deadlines.send_weekly(today=date(2026, 5, 4)) == 1  # a Monday
    assert "year-end statements" in mailoutbox[0].body


def test_issue_dates_matrix_and_budget_statement_pages(client, make_user, estate):
    year, member = estate["year"], estate["members"][0]
    client.force_login(make_user("admin", "Administrators"))
    client.post(f"/service-charges/years/{year.pk}/issued/", {"what": "budget", "date": "2025-02-20"})
    client.post(f"/service-charges/years/{year.pk}/issued/", {"what": "statements", "date": "2026-07-01",
                                                              "certified_by": "A Accountant"})
    year.refresh_from_db()
    assert year.budget_issued_on == date(2025, 2, 20) and year.certified_by == "A Accountant"
    page = client.get(f"/service-charges/years/{year.pk}/budget/{member.pk}/")
    assert page.status_code == 200 and page.context["annual"] == D("2000.00") and page.context["per_payment"] == D("500.00")
    assert client.get(f"/service-charges/years/{year.pk}/apportionment/").status_code == 200
    assert client.get(f"/service-charges/years/{year.pk}/apportionment/?format=xlsx").status_code == 200
    assert client.get("/").status_code == 200


def test_expenditure_import_income_and_recoverable(estate):
    rows = ("Schedule,Date,Heading,Description,Amount,Type,Recoverable\n"
            "Estate services,15/05/2025,INC,Interest,50,Income,\n"
            "Estate services,15/05/2025,ROAD,Upgrade,900,Cost,No\n"
            "Estate services,15/05/2025,CLN,Negative,-5,,\n")
    workbook = ExpenditureWorkbook()
    result, prepared = workbook.validate(SimpleUploadedFile("spend.csv", rows.encode()))
    assert "positive amount" in " ".join(result.rows[2].errors)
    good = "\n".join(rows.splitlines()[:3]) + "\n"
    workbook = ExpenditureWorkbook()
    result, prepared = workbook.validate(SimpleUploadedFile("spend.csv", good.encode()))
    workbook.apply(prepared)
    assert apportion.income_total(estate["year"]) == D("50") and apportion.non_recoverable_total(estate["year"]) == D("900")
