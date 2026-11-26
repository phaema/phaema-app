# SPDX-License-Identifier: AGPL-3.0-or-later
"""Interest on late rent, credit control stages, payment plans and the rent deposit account."""
from datetime import date
from decimal import Decimal

import pytest

from apps.cases.models import Case
from apps.core.models import ModuleSettings
from apps.leases.models import DepositEntry, Lease, Party, deposit_account
from apps.ledger import billing, creditcontrol, interest
from apps.ledger.models import BaseRate, Charge, ChaseAction, ChaseStage, PaymentPlan, Receipt
from apps.properties.models import Property

D = Decimal


@pytest.fixture
def ledger_on(db):
    s = ModuleSettings.load()
    s.rent_ledger_enabled, s.invoice_prefix, s.next_invoice_number = True, "INV", 1
    s.save()
    return s


@pytest.fixture
def surveyor(make_user):
    return make_user("sue", "Surveyors", email="sue@example.org")


@pytest.fixture
def lease(ledger_on, surveyor):
    unit = Property.objects.create(reference="P1", name="Unit 1", property_type="unit", managing_surveyor=surveyor)
    tenant = Party.objects.create(name="Tenant Ltd", party_type="company")
    obj = Lease.objects.create(reference="L1", agreement_type="lease", counterparty=tenant, term_start=date(2025, 12, 25),
                               term_end=date(2035, 12, 24), annual_rent=D("12000"), rent_frequency="quarter_days",
                               interest_basis="fixed", interest_margin_pct=D("8"), interest_grace_days=14)
    obj.properties.add(unit)
    return obj


def pay(lease, day, amount, ref):
    return Receipt.objects.create(lease=lease, received_on=day, amount=D(amount), payment_reference=ref)


def quarters(lease):
    """Charges of £3,000 due 25 March, 24 June and 29 September 2026."""
    billing.issue_run(date(2026, 1, 1), date(2026, 9, 30), date(2026, 1, 1))
    return list(lease.charges.order_by("due_date"))


# ------------------------------------------------------------------ interest

def test_interest_runs_from_the_due_date_once_past_the_grace_period(lease):
    march, june, september = quarters(lease)
    pay(lease, date(2026, 4, 4), "3000", "R1")  # 10 days late: within the 14 allowed
    pay(lease, date(2026, 8, 23), "3000", "R2")  # 60 days late
    result = interest.calculate(lease, until=date(2026, 10, 29))  # September unpaid for 30 days
    assert result.ok
    by_charge = {line.charge.pk: (line.days, line.interest) for line in result.lines}
    assert by_charge == {june.pk: (60, D("39.45")), september.pk: (30, D("19.73"))}
    assert result.total == D("59.18")


def test_raised_interest_is_not_charged_twice_or_on_itself(lease):
    _march, _june, september = quarters(lease)
    pay(lease, date(2026, 3, 25), "3000", "R1")
    pay(lease, date(2026, 6, 24), "3000", "R2")
    charge = interest.raise_charge(lease, date(2026, 10, 29), issue_date=date(2026, 10, 29))
    assert charge.kind == Charge.Kind.INTEREST and charge.gross == D("19.73") and charge.invoice_number
    assert (charge.period_start, charge.period_end) == (september.due_date, date(2026, 10, 29))
    later = interest.calculate(lease, until=date(2026, 11, 28))
    assert [(line.charge.pk, line.days) for line in later.lines] == [(september.pk, 30)]


def test_base_rate_plus_margin_follows_rate_changes(lease):
    lease.interest_basis, lease.interest_margin_pct, lease.interest_grace_days = "base_plus", D("4"), 0
    lease.save()
    BaseRate.objects.create(effective_from=date(2025, 1, 1), rate=D("4"))
    BaseRate.objects.create(effective_from=date(2026, 4, 4), rate=D("2"))
    quarters(lease)
    pay(lease, date(2026, 4, 4), "3000", "R1")  # 10 days: 3 at 8%, 7 at 6%... the new rate starts 4 April
    pay(lease, date(2026, 6, 24), "3000", "R2")
    pay(lease, date(2026, 9, 29), "3000", "R3")
    result = interest.calculate(lease, until=date(2026, 10, 1))
    expected = (D("3000") * (D("8") * 9 + D("6") * 1) / 100 / 365).quantize(D("0.01"))  # 26 Mar–3 Apr, 4 Apr
    assert result.total == expected and len(result.lines) == 1


def test_missing_base_rate_is_explained(lease):
    lease.interest_basis, lease.interest_margin_pct = "base_plus", D("4")
    lease.save()
    quarters(lease)
    result = interest.calculate(lease, until=date(2026, 10, 1))
    assert not result.ok and "base rate" in result.problem


def test_only_finance_users_raise_interest(lease, surveyor, client, make_user):
    quarters(lease)
    client.force_login(make_user("vic", "Viewers"))
    assert client.post(f"/rents/accounts/{lease.pk}/interest/", {"until": "2026-10-29"}).status_code == 403
    client.force_login(make_user("ann", "Administrators"))
    page = client.get(f"/rents/accounts/{lease.pk}/").content.decode()
    assert "Interest on late payment" in page
    client.post(f"/rents/accounts/{lease.pk}/interest/", {"until": "2026-10-29"})
    assert lease.charges.filter(kind="interest").exists()


# ------------------------------------------------------------------ credit control

def test_stages_are_taken_in_order_and_the_case_stage_opens_a_case(lease, surveyor):
    quarters(lease)
    today = date(2026, 5, 10)  # March unpaid for 46 days
    names = []
    for _ in range(3):
        (due,) = creditcontrol.due_actions(today)
        names.append(due.stage.name)
        creditcontrol.take(lease, due.stage, surveyor, today)
    assert names == ["Reminder letter", "Final notice", "Rent arrears recovery case"]
    case = ChaseAction.objects.get(stage__action="case").case
    assert case.case_type.code == "arrears" and case.lease == lease
    assert creditcontrol.due_actions(today) == []  # the review stage is not due until 60 days


def test_a_cleared_account_starts_a_new_episode(lease, surveyor):
    quarters(lease)
    first = ChaseStage.objects.get(days_overdue=7)
    creditcontrol.take(lease, first, surveyor, date(2026, 4, 10))
    pay(lease, date(2026, 4, 20), "3000", "R1")
    # June is now overdue: the reminder is due again for this new debt.
    (due,) = creditcontrol.due_actions(date(2026, 7, 5))
    assert due.stage == first and due.since == date(2026, 6, 24)


def test_accounts_on_hold_or_passed_to_legal_are_not_chased(lease):
    quarters(lease)
    lease.arrears_referral = "legal"
    lease.save()
    assert creditcontrol.due_actions(date(2026, 5, 10)) == []


def test_daily_task_opens_due_cases_by_itself(lease, surveyor):
    quarters(lease)
    today = date(2026, 5, 10)
    for stage in ChaseStage.objects.filter(action="letter"):
        creditcontrol.take(lease, stage, surveyor, today)
    assert creditcontrol.auto_open_cases(today) == 1
    assert Case.objects.filter(case_type__code="arrears", lease=lease).count() == 1


def test_credit_control_page_records_a_step(lease, surveyor, client, monkeypatch):
    quarters(lease)
    client.force_login(surveyor)
    page = client.get("/rents/credit-control/").content.decode()
    assert "L1" in page and "Reminder letter" in page
    assert "/documents/arrears-reminder/create/" in page  # the stage finds its letter in the library
    stage = ChaseStage.objects.get(days_overdue=7)
    client.post("/rents/credit-control/", {"lease": lease.pk, "stage": stage.pk})
    assert ChaseAction.objects.filter(lease=lease, stage=stage).exists()


# ------------------------------------------------------------------ payment plans

def test_a_kept_plan_pauses_chasing_and_a_broken_one_resumes_it(lease, surveyor):
    march, _june, _september = quarters(lease)
    plan = creditcontrol.make_plan(lease, date(2026, 4, 30), D("3000"), 3, date(2026, 5, 15),
                                   also_current_rent=False)
    assert [i.amount for i in plan.instalments.all()] == [D("1000.00")] * 3
    pay(lease, date(2026, 5, 15), "1000", "R1")
    assert creditcontrol.due_actions(date(2026, 6, 1)) == []  # kept so far
    # The second instalment (15 June) is not paid: broken seven days later.
    (due,) = creditcontrol.due_actions(date(2026, 6, 23))
    plan.refresh_from_db()
    assert plan.status == PaymentPlan.Status.BROKEN and due.broken_plan == plan


def test_plan_completes_when_the_arrears_are_cleared(lease):
    quarters(lease)
    plan = creditcontrol.make_plan(lease, date(2026, 4, 30), D("3000"), 2, date(2026, 5, 15))
    pay(lease, date(2026, 5, 15), "1500", "R1")
    pay(lease, date(2026, 6, 15), "1500", "R2")
    pay(lease, date(2026, 6, 24), "3000", "R3")  # and the June rent on time
    creditcontrol.refresh_plan(plan, date(2026, 6, 30))
    assert plan.status == PaymentPlan.Status.COMPLETED


def test_plan_set_up_from_the_account_page(lease, surveyor, client, make_user):
    quarters(lease)
    client.force_login(make_user("vic", "Viewers"))
    assert client.post(f"/rents/accounts/{lease.pk}/plan/", {"amount": "3000", "count": "3",
                                                             "first_due": "2026-05-15"}).status_code == 403
    client.force_login(surveyor)
    client.post(f"/rents/accounts/{lease.pk}/plan/", {"amount": "3000", "count": "3", "first_due": "2026-05-15",
                                                     "every": "month", "also_current_rent": "1"})
    plan = PaymentPlan.objects.get(lease=lease)
    assert plan.instalments.count() == 3 and plan.also_current_rent


# ------------------------------------------------------------------ deposit account

def test_deposit_balance_and_top_up_warning(lease, surveyor, client):
    lease.deposit = D("3000")
    lease.save()
    DepositEntry.objects.create(lease=lease, date=date(2025, 12, 25), kind="received", amount=D("3000"))
    DepositEntry.objects.create(lease=lease, date=date(2026, 5, 1), kind="drawdown", amount=D("1000"),
                                notes="March quarter's rent")
    DepositEntry.objects.create(lease=lease, date=date(2026, 6, 1), kind="interest", amount=D("12.50"))
    rows, balance = deposit_account(lease)
    assert balance == D("2012.50") and [b for _e, b in rows] == [D("3000"), D("2000"), D("2012.50")]
    client.force_login(surveyor)
    page = client.get(lease.get_absolute_url()).content.decode()
    assert "Rent deposit account" in page and "top it up" in page
