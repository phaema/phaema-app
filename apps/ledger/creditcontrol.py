# SPDX-License-Identifier: AGPL-3.0-or-later
"""Credit control: chasing overdue rent in stages, and payment plans.

Each account with overdue rent is in an *episode* that began when its oldest unpaid charge fell due. The council's
stages (Manage data, Credit control stages; by default a reminder at 7 days, a final notice at 21, a rent arrears
recovery case at 35 and a review at 60) are taken in order once the debt is old enough. A stage done in this episode
is not asked for again; once the account is clear, the next debt starts afresh.

Accounts are not chased while rent demands are on hold, after the debt has been passed to debt collectors or legal,
or while a payment plan is being kept. A plan is broken when the tenant falls behind its instalments (and, where
agreed, the rent as it falls due) by more than the days allowed; chasing then resumes.
"""
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction

from . import billing
from .models import ChaseAction, ChaseStage, Instalment, PaymentPlan

ZERO = Decimal("0")


# ------------------------------------------------------------------ payment plans

@dataclass
class PlanState:
    plan: object
    expected_paid: Decimal  # instalments due (and past the days allowed) by today
    owed_now: Decimal  # arrears covered by the plan still unpaid, plus late current rent where that counts
    behind: Decimal
    remaining: Decimal  # arrears covered by the plan still unpaid


def plan_state(plan, today=None, account=None):
    today = today or date.today()
    account = account or billing.account(plan.lease, today)
    cutoff = today - timedelta(days=plan.grace_days)
    expected = sum((i.amount for i in plan.instalments.all() if i.due_date <= cutoff), ZERO)
    debts = [line for line in account.lines if line.kind == "charge" and line.debit > 0]
    old = sum((line.outstanding for line in debts if line.obj.due_date <= plan.agreed_on), ZERO)
    late_new = sum((line.outstanding for line in debts
                    if plan.agreed_on < line.obj.due_date <= cutoff), ZERO) if plan.also_current_rent else ZERO
    owed = old + late_new
    allowed = max(plan.amount - expected, ZERO)
    return PlanState(plan, expected, owed, max(owed - allowed, ZERO), old)


def refresh_plan(plan, today=None, account=None):
    """Mark the plan completed or broken where that has happened. Returns its state."""
    state = plan_state(plan, today, account)
    if plan.status == PaymentPlan.Status.ACTIVE:
        if state.remaining <= 0 and state.behind <= 0:
            plan.status = PaymentPlan.Status.COMPLETED
            plan.save(update_fields=["status", "updated_at"])
        elif state.behind > Decimal("0.01"):
            plan.status = PaymentPlan.Status.BROKEN
            plan.save(update_fields=["status", "updated_at"])
    return state


@transaction.atomic
def make_plan(lease, agreed_on, amount, count, first_due, every="month", notes="", case=None, grace_days=7,
              also_current_rent=True):
    """A plan of `count` equal instalments (the last one takes any pennies), monthly or weekly from `first_due`."""
    from apps.core.dates import add_months

    if count < 1 or amount <= 0:
        raise ValueError("A payment plan needs at least one instalment and an amount.")
    from apps.core.audit import audited_update

    audited_update(PaymentPlan.objects.filter(lease=lease, status=PaymentPlan.Status.ACTIVE),
                   status=PaymentPlan.Status.CANCELLED)
    plan = PaymentPlan.objects.create(lease=lease, agreed_on=agreed_on, amount=amount, notes=notes, case=case,
                                      grace_days=grace_days, also_current_rent=also_current_rent)
    each = (amount / count).quantize(Decimal("0.01"))
    for n in range(count):
        due = add_months(first_due, n) if every == "month" else first_due + timedelta(weeks=n)
        value = each if n < count - 1 else amount - each * (count - 1)
        Instalment.objects.create(plan=plan, due_date=due, amount=value)
    return plan


def active_plan(lease):
    return lease.payment_plans.filter(status=PaymentPlan.Status.ACTIVE).prefetch_related("instalments").first()


# ------------------------------------------------------------------ chasing

@dataclass
class Due:
    account: object
    stage: object
    since: date  # when the oldest unpaid charge fell due
    days: int
    broken_plan: object = None


def episode_start(account, today):
    overdue = [line.obj.due_date for line in account.lines
               if line.kind == "charge" and line.outstanding > 0 and line.obj.due_date < today]
    return min(overdue) if overdue else None


def due_actions(today=None, leases=None):
    """The next chasing step for every account that needs one, oldest debt first."""
    today = today or date.today()
    stages = list(ChaseStage.objects.all())
    if not stages:
        return []
    out = []
    for acc in billing.accounts(today, leases):
        lease = acc.lease
        if acc.overdue <= 0 or lease.demands_on_hold or lease.arrears_referral:
            continue
        start = episode_start(acc, today)
        if start is None:
            continue
        broken = None
        plan = active_plan(lease)
        if plan is not None:
            refresh_plan(plan, today, acc)
            if plan.status == PaymentPlan.Status.ACTIVE:
                continue  # the plan is being kept
            if plan.status == PaymentPlan.Status.BROKEN:
                broken = plan
        if broken is None:
            broken = lease.payment_plans.filter(status=PaymentPlan.Status.BROKEN, updated_at__date__gte=start).first()
        done = set(ChaseAction.objects.filter(lease=lease, taken_on__gte=start).values_list("stage_id", flat=True))
        days = (today - start).days
        stage = next((s for s in stages if s.pk not in done and days >= s.days_overdue
                      and acc.overdue >= s.minimum_overdue), None)
        if stage is not None:
            out.append(Due(acc, stage, start, days, broken))
    return sorted(out, key=lambda d: (-d.days, -d.account.overdue))


def history(lease, account=None, today=None):
    """Chasing steps taken in the current episode."""
    today = today or date.today()
    account = account or billing.account(lease, today)
    start = episode_start(account, today)
    if start is None:
        return []
    return list(ChaseAction.objects.filter(lease=lease, taken_on__gte=start).select_related("stage", "case",
                                                                                              "taken_by"))


@transaction.atomic
def take(lease, stage, user=None, today=None, notes="", account=None):
    """Record a chasing step. A case stage opens a rent arrears recovery case (unless one is open already)."""
    today = today or date.today()
    account = account or billing.account(lease, today)
    case = None
    if stage.action == ChaseStage.Action.CASE:
        from apps.cases import workflow
        from apps.cases.models import CaseType

        case = next((c for c in lease.cases.filter(case_type__code="arrears") if c.is_open), None)
        if case is None:
            case_type = CaseType.objects.filter(code="arrears").first()
            if case_type is not None:
                case = workflow.open_case(
                    case_type, title=f"Rent arrears: {lease.counterparty.name} ({lease.reference})"[:200], lease=lease,
                    owner=user if user is not None and user.is_authenticated else None)
    return ChaseAction.objects.create(lease=lease, stage=stage, taken_on=today, overdue=account.overdue,
                                      taken_by=user if user is not None and user.is_authenticated else None,
                                      case=case, notes=notes[:255])


def auto_open_cases(today=None):
    """Daily: take any case stage that is due by itself, so arrears cases open without waiting for someone."""
    taken = 0
    for due in due_actions(today):
        if due.stage.action == ChaseStage.Action.CASE:
            take(due.account.lease, due.stage, today=today, notes="Opened automatically by credit control.",
                 account=due.account)
            taken += 1
    return taken
