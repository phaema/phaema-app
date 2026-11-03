# SPDX-License-Identifier: AGPL-3.0-or-later
"""Lease events and rent schedules: generating events from leases and recording outcomes.

Events are generated from the lease record: the next rent review, each break option (the
break date and the last date to serve notice) and the contractual expiry. Editing the lease
moves the open events; completed events are kept as history. Events can also be added by hand.
"""
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.core.dates import add_months

from .models import Lease, LeaseEvent, RentScheduleEntry

LIVE = (Lease.Status.CURRENT, Lease.Status.HOLDING_OVER)
OPEN = (LeaseEvent.Status.OPEN, LeaseEvent.Status.IN_PROGRESS)


# ------------------------------------------------------------------ rent schedule

def rent_on(lease, when):
    """The annual rent in force on a date, from the rent schedule (or the lease if it has none)."""
    entry = lease.rent_schedule.filter(effective_from__lte=when).order_by("-effective_from").first()
    return entry.annual_rent if entry else lease.annual_rent


def ensure_initial_entry(lease):
    if lease.pk and not lease.rent_schedule.exists():
        RentScheduleEntry.objects.create(lease=lease, effective_from=lease.term_start,
                                         annual_rent=lease.annual_rent, reason=RentScheduleEntry.Reason.INITIAL)


def refresh_current_rent(lease, today=None):
    """Make the lease's current rent match the schedule (e.g. when a stepped rent takes effect)."""
    today = today or date.today()
    if not lease.rent_schedule.exists():
        return False
    current = rent_on(lease, today)
    if current != lease.annual_rent:
        lease.annual_rent = current
        lease.save(update_fields=["annual_rent", "updated_at"])
        return True
    return False


# ------------------------------------------------------------------ payment dates

QUARTER_DAYS = ((3, 25), (6, 24), (9, 29), (12, 25))
PERIODS = {"quarter_days": 4, "quarterly": 4, "monthly": 12, "annually": 1}


def payment_dates(lease, start, count):
    """The next `count` rent payment dates on or after `start`."""
    freq = lease.rent_frequency
    if freq not in PERIODS:
        return []
    dates, step = [], 12 // PERIODS[freq]
    if freq == "quarter_days":
        year = start.year - 1
        while len(dates) < count:
            for m, d in QUARTER_DAYS:
                candidate = date(year, m, d)
                if candidate >= max(start, lease.term_start) and len(dates) < count:
                    dates.append(candidate)
            year += 1
    else:
        n = 0
        while len(dates) < count and n < 2400:
            candidate = add_months(lease.term_start, n * step)
            if candidate >= start:
                dates.append(candidate)
            n += 1
    end = lease.actual_end or lease.term_end
    if end and lease.status not in (Lease.Status.HOLDING_OVER,):
        dates = [d for d in dates if d <= end]
    return dates


def payments_preview(lease, start=None, count=4):
    """Upcoming payments: (date, amount) using the rent in force on each date. Ignores part periods."""
    start = start or date.today()
    periods = PERIODS.get(lease.rent_frequency)
    if not periods:
        return []
    return [(d, (rent_on(lease, d) / periods).quantize(Decimal("0.01"))) for d in payment_dates(lease, start, count)]


# ------------------------------------------------------------------ events

def default_assignee(lease):
    prop = lease.properties.filter(managing_surveyor__isnull=False).select_related("managing_surveyor").first()
    return prop.managing_surveyor if prop else None


def _wanted_events(lease, today):
    """What the lease says should be on the event list: {source: (type, due_date, title)}."""
    wanted = {}
    if lease.status not in LIVE:
        return wanted
    if lease.next_review_date:
        wanted["review"] = (LeaseEvent.EventType.REVIEW, lease.next_review_date, "")
    for b in lease.breaks.all():
        who = b.get_exercisable_by_display().lower()
        if b.break_date >= today:
            wanted[f"break:{b.pk}"] = (LeaseEvent.EventType.BREAK, b.break_date, f"Break date ({who})")
        if b.notice_deadline and b.notice_deadline >= today:
            wanted[f"notice:{b.pk}"] = (LeaseEvent.EventType.BREAK_NOTICE, b.notice_deadline,
                                        f"Last date to serve break notice ({who})")
    if lease.term_end:
        title = "Holding over: renew or recover possession" if lease.status == Lease.Status.HOLDING_OVER else ""
        wanted["expiry"] = (LeaseEvent.EventType.EXPIRY, lease.term_end, title)
    return wanted


@transaction.atomic
def sync_events(lease, today=None):
    """Bring the lease's generated events into line with the lease record."""
    today = today or date.today()
    wanted = _wanted_events(lease, today)
    assignee = default_assignee(lease)
    existing = list(lease.events.exclude(source=""))
    for source, (etype, due, title) in wanted.items():
        same = [e for e in existing if e.source == source]
        open_ = next((e for e in same if e.is_open), None)
        if open_:
            changed = []
            if open_.due_date != due:
                open_.due_date = due
                changed.append("due_date")
            if open_.title != title:
                open_.title = title
                changed.append("title")
            if open_.assigned_to_id is None and assignee:
                open_.assigned_to = assignee
                changed.append("assigned_to")
            if changed:
                open_.save(update_fields=changed + ["updated_at"])
        elif not any(e.due_date == due for e in same):  # not already dealt with for this date
            LeaseEvent.objects.create(lease=lease, event_type=etype, due_date=due, title=title,
                                      source=source, assigned_to=assignee)
    for e in existing:
        if e.is_open and e.source not in wanted:
            if lease.status in LIVE:
                e.delete()  # e.g. the break option was removed
            else:
                e.status = LeaseEvent.Status.LAPSED
                e.outcome = (e.outcome + "\n" if e.outcome else "") + "Agreement ended."
                e.completed_on = today
                e.save(update_fields=["status", "outcome", "completed_on", "updated_at"])
    # Events added by hand also get the surveyor if nobody was chosen.
    if assignee:
        lease.events.filter(source="", assigned_to__isnull=True, status__in=OPEN).update(assigned_to=assignee)


def _close(event, user, status, outcome):
    event.status = status
    event.completed_on = timezone.localdate()
    event.completed_by = user
    if outcome:
        event.outcome = (event.outcome + "\n" if event.outcome else "") + outcome
    event.save()


@transaction.atomic
def complete_review(event, user, new_rent, effective_from, next_review_date, notes=""):
    """Record a settled rent review: the new rent from its date, and when the next review is."""
    lease = event.lease
    RentScheduleEntry.objects.update_or_create(
        lease=lease, effective_from=effective_from,
        defaults={"annual_rent": new_rent, "reason": RentScheduleEntry.Reason.REVIEW, "notes": notes[:255]},
    )
    _close(event, user, LeaseEvent.Status.DONE,
           f"Review settled at £{new_rent:,.2f} a year from {effective_from:%d %B %Y}. {notes}".strip())
    lease.refresh_from_db()
    lease.next_review_date = next_review_date
    lease.save()  # moves the open review event on to the next review
    refresh_current_rent(lease)


def suggested_next_review(event):
    lease = event.lease
    if lease.review_interval_years:
        nxt = add_months(event.due_date, 12 * lease.review_interval_years)
        if not lease.term_end or nxt < lease.term_end:
            return nxt
    return None


BREAK_OUTCOMES = {
    "served": "Break notice served",
    "not_served": "No notice served: break lapsed",
    "exercised": "Break exercised: agreement ends",
    "not_exercised": "Break not exercised",
}
EXPIRY_OUTCOMES = {
    "vacated": "Tenant vacated: agreement ended",
    "renewed": "Renewed: agreement ended (record the new agreement separately)",
    "holding_over": "Tenant holding over",
}


@transaction.atomic
def complete_break(event, user, outcome, notes=""):
    lease = event.lease
    text = f"{BREAK_OUTCOMES[outcome]}. {notes}".strip()
    if outcome == "not_served":
        _close(event, user, LeaseEvent.Status.LAPSED, text)
        # the break date itself is now academic
        break_source = event.source.replace("notice:", "break:")
        for e in lease.events.filter(source=break_source, status__in=OPEN):
            _close(e, user, LeaseEvent.Status.LAPSED, "No break notice was served.")
    elif outcome == "exercised":
        _close(event, user, LeaseEvent.Status.DONE, text)
        lease.status, lease.actual_end = Lease.Status.ENDED, event.due_date
        lease.save()
    elif outcome == "not_exercised":
        _close(event, user, LeaseEvent.Status.LAPSED, text)
    else:  # served
        _close(event, user, LeaseEvent.Status.DONE, text)


@transaction.atomic
def complete_expiry(event, user, outcome, end_date=None, notes=""):
    lease = event.lease
    text = f"{EXPIRY_OUTCOMES[outcome]}. {notes}".strip()
    if outcome == "holding_over":
        event.status = LeaseEvent.Status.IN_PROGRESS
        event.outcome = (event.outcome + "\n" if event.outcome else "") + text
        event.save()
        lease.status = Lease.Status.HOLDING_OVER
        lease.save()
        return
    _close(event, user, LeaseEvent.Status.DONE, text)
    lease.status, lease.actual_end = Lease.Status.ENDED, end_date or event.due_date
    lease.save()


def complete_other(event, user, status, notes=""):
    _close(event, user, status, notes)


def sync_all(today=None):
    """Daily housekeeping: stepped rents take effect, and events catch up with the calendar."""
    changed = 0
    for lease in Lease.objects.filter(status__in=LIVE).prefetch_related("breaks"):
        changed += refresh_current_rent(lease, today)
        sync_events(lease, today)
    return changed

