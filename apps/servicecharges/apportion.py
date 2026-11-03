# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sharing a schedule's costs between leases, and the year-end reconciliation.

Shares are worked out over the lettable units in the schedule, including empty ones, so the
council bears the share of any unit that is not let (the void share). Over a year, each lease's
share is also scaled by the days it was in force, and capped where the lease says so.
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from apps.leases.models import Lease
from apps.leases.workflow import PERIODS
from apps.ledger.models import PENNY, Charge

from .models import Schedule, ScheduleYear

ZERO = Decimal("0")


LETTABLE = ("unit", "building")


def units(schedule):
    """The lettable units a schedule covers: the lowest-level units and buildings within it
    (land such as estate roads is left out)."""
    found, stack = {}, list(schedule.properties.all())
    while stack:
        prop = stack.pop()
        children = list(prop.children.all())
        if children:
            stack.extend(children)
        elif prop.property_type in LETTABLE:
            found[prop.pk] = prop
    return list(found.values())


@dataclass
class Share:
    member: object
    area: Decimal
    share: Decimal  # fraction of the schedule's costs, 0–1


def shares(schedule):
    """Each contributing lease's share of the costs, and the council's share for empty units."""
    unit_list = units(schedule)
    ids = {u.pk for u in unit_list}
    total_area = sum((u.nia_sqm or ZERO for u in unit_list), ZERO)
    members = list(schedule.members.select_related("lease", "lease__counterparty").prefetch_related("lease__properties"))
    out = []
    for m in members:
        mine = [p for p in m.lease.properties.all() if p.pk in ids]
        area = sum((p.nia_sqm or ZERO for p in mine), ZERO)
        if schedule.basis == Schedule.Basis.FIXED:
            share = (m.fixed_percentage or ZERO) / 100
        elif schedule.basis == Schedule.Basis.EQUAL:
            share = Decimal(len(mine)) / len(unit_list) if unit_list else ZERO
        else:
            share = area / total_area if total_area else ZERO
        out.append(Share(m, area, share))
    return out, total_area, max(ZERO, 1 - sum((s.share for s in out), ZERO))


def budget_total(year):
    return year.budget_lines.aggregate(t=Sum("amount"))["t"] or ZERO


def _sum(qs):
    return qs.aggregate(t=Sum("amount"))["t"] or ZERO


def recoverable_costs(year):
    return _sum(year.expenditure.filter(kind="cost", recoverable=True))


def income_total(year):
    """Interest, rebates and commissions credited to the service charge."""
    return _sum(year.expenditure.filter(kind="income"))


def non_recoverable_total(year):
    """Costs the council bears itself, such as improvements."""
    return _sum(year.expenditure.filter(kind="cost", recoverable=False))


def actual_total(year):
    """The net cost to share: recoverable costs less income and credits."""
    return recoverable_costs(year) - income_total(year)


def by_heading(year):
    """[(heading, budget, actual)]: budget and recoverable costs for every heading with either."""
    from .models import CostHeading

    budget = dict(year.budget_lines.values_list("heading", "amount"))
    actual = dict(year.expenditure.filter(kind="cost", recoverable=True).values("heading").annotate(t=Sum("amount"))
                  .values_list("heading", "t"))
    rows = []
    for h in CostHeading.objects.filter(pk__in=set(budget) | set(actual)):
        rows.append((h, budget.get(h.pk, ZERO), actual.get(h.pk, ZERO)))
    return rows


def capped(amount, cap, fraction=Decimal("1")):
    if cap is None:
        return amount
    return min(amount, (cap * fraction).quantize(PENNY))


def on_account_annual(year, share):
    """A lease's annual on-account payment for the year: its share of the budget, capped."""
    return capped((budget_total(year) * share.share).quantize(PENNY), share.member.annual_cap)


def years_overlapping(schedule, start, end):
    return list(schedule.years.filter(start__lte=end, end__gte=start, status=ScheduleYear.Status.APPROVED))


def proposed_service_charges(due_from, due_to, issue_date, vat_rate):
    """Unsaved on-account service charges for periods due between two dates, not raised before.

    They follow the lease's rent payment dates. A period that runs over a service charge year end
    is split, each part charged at its own year's budget, so each year's account is right.
    """
    from apps.ledger.billing import rent_periods

    done = set(Charge.objects.filter(kind=Charge.Kind.SERVICE, period_start__isnull=False)
               .values_list("lease_id", "period_start", "service_year_id"))
    out = []
    for schedule in Schedule.objects.filter(active=True, years__status=ScheduleYear.Status.APPROVED).distinct():
        share_list, _area, _void = shares(schedule)
        for s in share_list:
            lease = s.member.lease
            if lease.direction != Lease.Direction.OUT or lease.status not in ("current", "holding_over"):
                continue
            for start, end, due, full in rent_periods(lease, due_from, due_to):
                for year in years_overlapping(schedule, start, end):
                    part_start, part_end = max(start, year.start), min(end, year.end)
                    if (lease.pk, part_start, year.pk) in done:
                        continue
                    annual = on_account_annual(year, s)
                    whole = full and (part_start, part_end) == (start, end)
                    net = (annual / PERIODS[lease.rent_frequency]).quantize(PENNY) if whole else \
                        (annual * ((part_end - part_start).days + 1) / 365).quantize(PENNY)
                    if net <= 0:
                        continue
                    rate = vat_rate if lease.vat_chargeable else ZERO
                    net, vat, gross = Charge.amounts(net, rate)
                    out.append(Charge(lease=lease, kind=Charge.Kind.SERVICE, service_year=year,
                                      period_start=part_start, period_end=part_end, due_date=due,
                                      issue_date=issue_date, net=net, vat_rate=rate, vat=vat, gross=gross,
                                      description=f"Service charge on account ({schedule.name}) "
                                                  f"{part_start:%d/%m/%Y} to {part_end:%d/%m/%Y}"[:200]))
    return out


# ------------------------------------------------------------------ reconciliation

@dataclass
class ReconLine:
    share: Share
    days: int
    fraction: Decimal  # days in the year / days in the year the lease was in force
    due: Decimal  # share of actual costs for the time in force, capped
    demanded: Decimal  # on-account net already charged for this year
    balance: Decimal  # due − demanded: positive = charge, negative = credit
    capped: bool = False


@dataclass
class Reconciliation:
    year: object
    lines: list
    actual: Decimal
    budget: Decimal
    recovered: Decimal  # charged to tenants in total
    council: Decimal  # borne by the council: voids, part-year gaps and caps
    rows: list = field(default_factory=list)  # [(heading, budget, actual)]
    costs: Decimal = ZERO  # recoverable costs before income
    income: Decimal = ZERO  # interest, rebates and commissions credited
    non_recoverable: Decimal = ZERO  # costs the council bears itself


def _days_in_force(lease, year):
    start = max(lease.term_start, year.start)
    end_candidates = [year.end] + [d for d in (lease.actual_end, lease.term_end if lease.status != "holding_over"
                                               else None) if d]
    end = min(end_candidates)
    return max(0, (end - start).days + 1)


def reconcile(year):
    actual = actual_total(year)
    share_list, _area, _void = shares(year.schedule)
    demanded = dict(Charge.objects.filter(service_year=year).values("lease").annotate(t=Sum("net"))
                    .values_list("lease", "t"))
    lines = []
    for s in share_list:
        days = _days_in_force(s.member.lease, year)
        fraction = Decimal(days) / Decimal(year.days)
        uncapped = (actual * s.share * fraction).quantize(PENNY)
        due = capped(uncapped, s.member.annual_cap, fraction)
        paid = demanded.get(s.member.lease_id, ZERO)
        lines.append(ReconLine(s, days, fraction, due, paid, due - paid, capped=due < uncapped))
    recovered = sum((line.due for line in lines), ZERO)
    return Reconciliation(year, lines, actual, budget_total(year), recovered, actual - recovered, by_heading(year),
                          costs=recoverable_costs(year), income=income_total(year),
                          non_recoverable=non_recoverable_total(year))


# ------------------------------------------------------------------ apportionment matrix

@dataclass
class Matrix:
    basis: str  # "actual" or "budget"
    headings: list  # column names
    rows: list  # [(label, share, days, [amounts], total)]
    totals: list  # column totals, then the grand total


def matrix(year, basis=None):
    """How each heading's cost is shared between the leases and the council, for the year.

    Uses actual costs once the year has spending, otherwise the budget. Income and credits are a
    final, negative column. A capped lease's amounts are scaled down in proportion to its cap.
    """
    from .models import CostHeading

    if year.apportionment and basis is None:
        return Matrix(**year.apportionment)  # fixed at reconciliation
    basis = basis or ("actual" if year.expenditure.exists() else "budget")
    if basis == "actual":
        values = dict(year.expenditure.filter(kind="cost", recoverable=True).values("heading")
                      .annotate(t=Sum("amount")).values_list("heading", "t"))
    else:
        values = dict(year.budget_lines.values_list("heading", "amount"))
    headings = list(CostHeading.objects.filter(pk__in=values).exclude(code="INC"))
    columns = [(h.name, values[h.pk]) for h in headings]
    income = income_total(year) if basis == "actual" else ZERO
    if income:
        columns.append(("Income and credits", -income))
    total = sum((v for _n, v in columns), ZERO)
    share_list, _area, _void = shares(year.schedule)
    rows, used = [], [ZERO] * len(columns)
    for s in share_list:
        days = _days_in_force(s.member.lease, year)
        fraction = Decimal(days) / Decimal(year.days)
        uncapped = total * s.share * fraction
        due = capped(uncapped.quantize(PENNY), s.member.annual_cap, fraction)
        scale = (due / uncapped) if uncapped else ZERO
        amounts = [(v * s.share * fraction * scale).quantize(PENNY) for _n, v in columns]
        if amounts:  # put any rounding difference on the largest heading, so the row matches the reconciliation
            biggest = max(range(len(amounts)), key=lambda i: abs(amounts[i]))
            amounts[biggest] += due - sum(amounts, ZERO)
        used = [u + a for u, a in zip(used, amounts)]
        rows.append([f"{s.member.lease.reference} {s.member.lease.counterparty.name}", str(s.share), days,
                     [str(a) for a in amounts], str(sum(amounts, ZERO))])
    council = [(v - u).quantize(PENNY) for (_n, v), u in zip(columns, used)]
    rows.append(["Council (empty units, part years, caps)", "", "", [str(a) for a in council],
                 str(sum(council, ZERO))])
    return Matrix(basis, [n for n, _v in columns], rows, [str(v) for _n, v in columns] + [str(total)])


@transaction.atomic
def finalise(year, issue_date=None):
    """Raise balancing charges and credits, and mark the year reconciled."""
    from apps.ledger.billing import _number, settings_row

    issue_date = issue_date or date.today()
    recon = reconcile(year)
    vat_rate = settings_row().vat_rate
    made = []
    for line in recon.lines:
        if line.balance == 0:
            continue
        lease = line.share.member.lease
        rate = vat_rate if lease.vat_chargeable else ZERO
        net, vat, gross = Charge.amounts(line.balance, rate)
        kind = "balancing charge" if line.balance > 0 else "balancing credit"
        made.append(Charge(lease=lease, kind=Charge.Kind.SERVICE, service_year=year, issue_date=issue_date,
                           due_date=issue_date, net=net, vat_rate=rate, vat=vat, gross=gross,
                           description=f"Service charge {kind} ({year.schedule.name} {year.label})"[:200]))
    _number(made)
    for charge in made:
        charge.save()
    snapshot = matrix(year, basis="actual")
    year.apportionment = {"basis": snapshot.basis, "headings": snapshot.headings, "rows": snapshot.rows,
                          "totals": snapshot.totals}
    year.status, year.reconciled_on = ScheduleYear.Status.RECONCILED, issue_date
    year.save(update_fields=["status", "reconciled_on", "apportionment", "updated_at"])
    return made
