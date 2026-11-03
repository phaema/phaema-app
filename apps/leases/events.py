# SPDX-License-Identifier: AGPL-3.0-or-later
"""Lease events (reviews, breaks, expiries) and rent roll figures for the dashboard.

Only live agreements count: those marked current or holding over.
"Overdue" means an event date has passed but the record has not been brought up to date:
  - rent review: the next review date has passed (the review has not been settled and recorded);
  - expiry: the contractual expiry has passed but the agreement is still marked current;
  - holding over: the tenant remains in occupation after expiry (renewal or exit to resolve).
Break dates and break notice deadlines are not "overdue" once passed (the right simply lapses),
so they are shown as coming up only.
"""
from collections import OrderedDict
from datetime import date
from decimal import Decimal

from django.utils.translation import gettext_lazy as _

from apps.core.dates import add_months

from .models import BreakOption, Lease

LIVE = (Lease.Status.CURRENT, Lease.Status.HOLDING_OVER)
WINDOW_MONTHS = 6

EVENTS = OrderedDict([
    ("review", _("Rent reviews")),
    ("expiry", _("Lease expiries")),
    ("holding_over", _("Holding over")),
    ("notice", _("Break notice deadlines")),
    ("break", _("Break dates")),
])

# Lease list filter values, with a description shown on the filtered list.
FILTERS = OrderedDict([
    ("review_overdue", _("Rent review overdue")),
    ("review_due", _("Rent review in the next 6 months")),
    ("expiry_overdue", _("Expired but still marked current")),
    ("expiry_due", _("Expiring in the next 6 months")),
    ("holding_over", _("Holding over")),
    ("notice_due", _("Break notice deadline in the next 6 months")),
    ("break_due", _("Break date in the next 6 months")),
])


def live():
    return Lease.objects.filter(status__in=LIVE)


def _break_lease_ids(today, end, use_notice):
    ids = set()
    for b in BreakOption.objects.filter(lease__status__in=LIVE).select_related("lease"):
        when = b.notice_deadline if use_notice else b.break_date
        if when and today <= when <= end:
            ids.add(b.lease_id)
    return ids


def filter_leases(qs, key, today=None):
    """Narrow a lease queryset to one event filter."""
    today = today or date.today()
    end = add_months(today, WINDOW_MONTHS)
    qs = qs.filter(status__in=LIVE)
    if key == "review_overdue":
        return qs.filter(next_review_date__lt=today)
    if key == "review_due":
        return qs.filter(next_review_date__gte=today, next_review_date__lte=end)
    if key == "expiry_overdue":
        return qs.filter(status=Lease.Status.CURRENT, term_end__lt=today)
    if key == "expiry_due":
        return qs.filter(term_end__gte=today, term_end__lte=end)
    if key == "holding_over":
        return qs.filter(status=Lease.Status.HOLDING_OVER)
    if key == "notice_due":
        return qs.filter(pk__in=_break_lease_ids(today, end, use_notice=True))
    if key == "break_due":
        return qs.filter(pk__in=_break_lease_ids(today, end, use_notice=False))
    return qs


def event_summary(today=None):
    """Rows for the dashboard: label, overdue count and filter, due-soon count and filter."""
    today = today or date.today()
    base = Lease.objects.all()

    def n(key):
        return filter_leases(base, key, today).count()

    return [
        {"label": EVENTS["review"], "overdue": n("review_overdue"), "overdue_key": "review_overdue",
         "due": n("review_due"), "due_key": "review_due"},
        {"label": EVENTS["expiry"], "overdue": n("expiry_overdue"), "overdue_key": "expiry_overdue",
         "due": n("expiry_due"), "due_key": "expiry_due"},
        {"label": EVENTS["holding_over"], "overdue": n("holding_over"), "overdue_key": "holding_over",
         "due": None, "due_key": None},
        {"label": EVENTS["notice"], "overdue": None, "overdue_key": None,
         "due": n("notice_due"), "due_key": "notice_due"},
        {"label": EVENTS["break"], "overdue": None, "overdue_key": None,
         "due": n("break_due"), "due_key": "break_due"},
    ]


def _years(start, end):
    return Decimal(max((end - start).days, 0)) / Decimal("365.25")


def rent_roll(today=None):
    """Income from live agreements let out by the council, and rent the council pays."""
    today = today or date.today()
    income = list(live().filter(direction=Lease.Direction.OUT).prefetch_related("properties", "breaks"))
    paying = [lease for lease in income if lease.annual_rent > 0]
    total = sum((lease.annual_rent for lease in income), Decimal("0"))

    by_purpose = OrderedDict()
    for lease in paying:
        props = list(lease.properties.all())
        label = props[0].get_holding_purpose_display() if props and props[0].holding_purpose else _("Not set")
        row = by_purpose.setdefault(str(label), {"rent": Decimal("0"), "count": 0})
        row["rent"] += lease.annual_rent
        row["count"] += 1

    # Weighted average unexpired lease term (WAULT), weighted by rent. Periodic agreements are excluded.
    fixed = [lease for lease in paying if lease.term_end]
    weight = sum((lease.annual_rent for lease in fixed), Decimal("0"))
    wault_expiry = wault_break = None
    if weight:
        wault_expiry = sum(lease.annual_rent * _years(today, lease.term_end) for lease in fixed) / weight
        to_break = Decimal("0")
        for lease in fixed:
            tenant_breaks = [b.break_date for b in lease.breaks.all()
                             if b.break_date >= today and b.exercisable_by in ("tenant", "either")]
            first = min(tenant_breaks + [lease.term_end])
            to_break += lease.annual_rent * _years(today, first)
        wault_break = to_break / weight

    payable = live().filter(direction=Lease.Direction.IN)
    return {
        "total": total,
        "agreements": len(income),
        "paying": len(paying),
        "nil_rent": len(income) - len(paying),
        "by_purpose": list(by_purpose.items()),
        "wault_expiry": wault_expiry.quantize(Decimal("0.1")) if wault_expiry is not None else None,
        "wault_break": wault_break.quantize(Decimal("0.1")) if wault_break is not None else None,
        "payable": sum((lease.annual_rent for lease in payable), Decimal("0")),
        "payable_count": payable.count(),
    }
