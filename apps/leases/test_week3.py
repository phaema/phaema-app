# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core import mail
from django.urls import reverse

from apps.core.models import ModuleSettings
from apps.leases import events as dashboard_events
from apps.leases import workflow
from apps.leases.models import BreakOption, CalendarFeed, Lease, LeaseEvent, Party, RentScheduleEntry
from apps.leases.reminders import due_reminders, send_reminders
from apps.properties.models import Property

TODAY = date.today()


@pytest.fixture
def surveyor(make_user):
    return make_user("sue", "Surveyors", email="sue@example.org", first_name="Sue")


@pytest.fixture
def lease(db, surveyor):
    prop = Property.objects.create(reference="P1", name="Shop", property_type="unit", managing_surveyor=surveyor)
    tenant = Party.objects.create(name="Tenant Ltd", party_type="company")
    obj = Lease.objects.create(
        reference="L1", agreement_type="lease", counterparty=tenant, term_start=date(2022, 3, 25),
        term_end=date(2032, 3, 24), annual_rent=Decimal("12000"), rent_frequency="quarter_days",
        review_basis="om_up", review_interval_years=5, next_review_date=TODAY + timedelta(days=60))
    obj.properties.add(prop)
    return obj


def events_of(lease, **kw):
    return {e.source: e for e in lease.events.filter(**kw)}


# ------------------------------------------------------------------ rent schedule

def test_initial_rent_entry_and_stepped_rent(lease):
    assert [(e.effective_from, e.annual_rent) for e in lease.rent_schedule.all()] == [(date(2022, 3, 25), Decimal("12000"))]
    step = TODAY + timedelta(days=10)
    RentScheduleEntry.objects.create(lease=lease, effective_from=step, annual_rent=Decimal("15000"), reason="step")
    lease.refresh_from_db()
    assert lease.annual_rent == Decimal("12000")  # not yet
    assert workflow.rent_on(lease, step) == Decimal("15000")
    assert workflow.refresh_current_rent(lease, today=step)
    lease.refresh_from_db()
    assert lease.annual_rent == Decimal("15000")


def test_payment_dates(lease):
    assert workflow.payment_dates(lease, date(2026, 11, 3), 4) == [
        date(2026, 12, 25), date(2027, 3, 25), date(2027, 6, 24), date(2027, 9, 29)]
    assert workflow.payments_preview(lease, date(2026, 11, 3), 1) == [(date(2026, 12, 25), Decimal("3000.00"))]
    lease.rent_frequency = "monthly"
    assert workflow.payment_dates(lease, date(2026, 11, 3), 2) == [date(2026, 11, 25), date(2026, 12, 25)]
    lease.rent_frequency = "peppercorn"
    assert workflow.payment_dates(lease, date(2026, 11, 3), 2) == []


# ------------------------------------------------------------------ event generation

def test_events_generated_and_assigned(lease, surveyor):
    ev = events_of(lease)
    assert set(ev) == {"review", "expiry"}
    assert all(e.assigned_to == surveyor for e in ev.values())
    b = BreakOption.objects.create(lease=lease, break_date=TODAY + timedelta(days=400), exercisable_by="tenant",
                                   notice_months=6)
    ev = events_of(lease)
    assert {f"break:{b.pk}", f"notice:{b.pk}"} <= set(ev)
    assert ev[f"notice:{b.pk}"].due_date == b.notice_deadline
    # past breaks are not added: they have lapsed
    old = BreakOption.objects.create(lease=lease, break_date=date(2024, 3, 25), exercisable_by="tenant", notice_months=6)
    assert f"break:{old.pk}" not in events_of(lease)
    # editing the lease moves the open event rather than adding another
    lease.next_review_date = TODAY + timedelta(days=90)
    lease.save()
    reviews = lease.events.filter(event_type="review")
    assert reviews.count() == 1 and reviews.get().due_date == TODAY + timedelta(days=90)
    # removing the break removes its open events
    b.delete()
    assert f"break:{b.pk}" not in events_of(lease)
    workflow.sync_events(lease)
    assert lease.events.count() == 2  # idempotent


def test_ended_lease_lapses_open_events(lease):
    lease.status = "ended"
    lease.save()
    assert not lease.events.filter(status__in=workflow.OPEN).exists()
    assert lease.events.filter(status="lapsed").count() == 2


# ------------------------------------------------------------------ outcomes

def test_complete_review(lease, surveyor):
    event = lease.events.get(event_type="review")
    due = event.due_date
    nxt = workflow.suggested_next_review(event)
    assert nxt.year == due.year + 5
    workflow.complete_review(event, surveyor, Decimal("13500"), due, nxt, "Agreed")
    event.refresh_from_db()
    assert event.status == "done" and "13,500.00" in event.outcome and event.completed_by == surveyor
    assert workflow.rent_on(lease, due) == Decimal("13500")
    reviews = lease.events.filter(event_type="review", status="open")
    assert reviews.count() == 1 and reviews.get().due_date == nxt


def test_break_outcomes(lease, surveyor):
    b = BreakOption.objects.create(lease=lease, break_date=TODAY + timedelta(days=400), exercisable_by="tenant",
                                   notice_months=6)
    notice = lease.events.get(source=f"notice:{b.pk}")
    workflow.complete_break(notice, surveyor, "not_served")
    assert lease.events.get(source=f"break:{b.pk}").status == "lapsed"
    b2 = BreakOption.objects.create(lease=lease, break_date=TODAY + timedelta(days=500), exercisable_by="tenant")
    workflow.complete_break(lease.events.get(source=f"break:{b2.pk}"), surveyor, "exercised")
    lease.refresh_from_db()
    assert lease.status == "ended" and lease.actual_end == b2.break_date


def test_expiry_outcomes(lease, surveyor):
    expiry = lease.events.get(event_type="expiry")
    workflow.complete_expiry(expiry, surveyor, "holding_over")
    lease.refresh_from_db()
    expiry.refresh_from_db()
    assert lease.status == "holding_over" and expiry.status == "in_progress" and expiry.title.startswith("Holding over")
    workflow.complete_expiry(expiry, surveyor, "vacated", date(2032, 6, 30))
    lease.refresh_from_db()
    assert lease.status == "ended" and lease.actual_end == date(2032, 6, 30)


# ------------------------------------------------------------------ screens and permissions

def test_event_pages_and_actions(client, lease, surveyor, make_user):
    event = lease.events.get(event_type="review")
    client.force_login(surveyor)
    resp = client.get(reverse("leases:events"), {"assigned": "me"})
    assert resp.context["paginator"].count == 2
    html = client.get(event.get_absolute_url()).content.decode()
    assert "Record the outcome" in html and "Agreed annual rent" in html
    nxt = workflow.suggested_next_review(event)
    resp = client.post(event.get_absolute_url(), {"record_outcome": "1", "new_rent": "14000",
                                                  "effective_from": event.due_date.isoformat(),
                                                  "next_review_date": nxt.isoformat(), "notes": ""})
    assert resp.status_code == 302
    lease.refresh_from_db()
    assert workflow.rent_on(lease, event.due_date) == Decimal("14000")
    html = client.get(lease.get_absolute_url()).content.decode()
    assert "Rent schedule" in html and "14,000.00" in html and "Next payments due" in html

    other = make_user("sam", "Surveyors")
    client.force_login(other)
    open_review = lease.events.get(event_type="review", status="open")
    assert "Record the outcome" not in client.get(open_review.get_absolute_url()).content.decode()
    assert client.post(open_review.get_absolute_url(), {"record_outcome": "1"}).status_code == 403
    assert client.get(reverse("leases:event-add", args=[lease.pk])).status_code == 403
    assert client.get(reverse("leases:rent-add", args=[lease.pk])).status_code == 403


def test_add_event_and_rent_step(client, lease, surveyor):
    client.force_login(surveyor)
    resp = client.post(reverse("leases:event-add", args=[lease.pk]),
                       {"title": "Insurance renewal", "due_date": (TODAY + timedelta(days=20)).isoformat(),
                        "assigned_to": surveyor.pk, "outcome": ""})
    assert resp.status_code == 302 and lease.events.filter(title="Insurance renewal", event_type="other").exists()
    resp = client.post(reverse("leases:rent-add", args=[lease.pk]),
                       {"effective_from": "2027-03-25", "annual_rent": "13000", "reason": "step", "notes": ""})
    assert resp.status_code == 302
    entry = lease.rent_schedule.get(effective_from=date(2027, 3, 25))
    resp = client.post(reverse("leases:rent-add", args=[lease.pk]),
                       {"effective_from": "2027-03-25", "annual_rent": "1", "reason": "step", "notes": ""})
    assert b"already a rent from that date" in resp.content
    client.post(reverse("leases:rent-delete", args=[entry.pk]))
    assert not lease.rent_schedule.filter(pk=entry.pk).exists()


def test_dashboard_counts_events(lease):
    rows = {r["type"]: r for r in dashboard_events.event_summary()}
    assert rows["review"]["due"] == 1 and rows["review"]["overdue"] == 0 and rows["expiry"]["due"] == 0
    LeaseEvent.objects.filter(event_type="review").update(due_date=TODAY - timedelta(days=5))
    rows = {r["type"]: r for r in dashboard_events.event_summary()}
    assert rows["review"]["overdue"] == 1 and rows["notice"]["overdue"] is None


# ------------------------------------------------------------------ calendar feed

def test_calendar_feed(client, lease, surveyor):
    client.force_login(surveyor)
    page = client.get(reverse("leases:calendar"))
    feed = CalendarFeed.objects.get(user=surveyor)
    assert feed.token in page.content.decode()
    client.logout()
    resp = client.get(f"/calendar/{feed.token}.ics")  # no sign-in needed: the token is the key
    body = resp.content.decode()
    assert resp["Content-Type"].startswith("text/calendar")
    assert body.startswith("BEGIN:VCALENDAR") and body.count("BEGIN:VEVENT") == 2
    assert "Rent review: Tenant Ltd (L1)" in body and "\r\n" in body
    assert all(len(line.encode()) <= 75 for line in body.split("\r\n"))
    old = feed.token
    feed.regenerate()
    assert client.get(f"/calendar/{old}.ics").status_code == 404


# ------------------------------------------------------------------ reminders

def test_reminder_stages_and_no_duplicates(lease, surveyor, settings):
    event = lease.events.get(event_type="review")  # due in 60 days: past the 90-day point
    items = due_reminders(TODAY)[surveyor]
    assert [(e.pk, stage) for e, stage in items] == [(event.pk, "90")]
    assert send_reminders(TODAY) == 1
    assert len(mail.outbox) == 1 and "Rent review: Tenant Ltd (L1)" in mail.outbox[0].body
    assert send_reminders(TODAY) == 0  # not sent twice
    # 30 days before is a new point
    assert send_reminders(event.due_date - timedelta(days=30)) == 1


def test_overdue_reminders_weekly_and_unassigned_go_to_admins(lease, make_user):
    admin = make_user("ann", "Administrators", email="ann@example.org")
    LeaseEvent.objects.filter(lease=lease).update(assigned_to=None)
    event = lease.events.get(event_type="review")
    event.due_date = TODAY - timedelta(days=10)
    event.save()
    monday = TODAY + timedelta(days=(7 - TODAY.weekday()) % 7)
    tuesday = monday + timedelta(days=1)
    assert admin not in due_reminders(tuesday) or not any(e.pk == event.pk for e, _s in due_reminders(tuesday)[admin])
    stages = [s for e, s in due_reminders(monday)[admin] if e.pk == event.pk]
    assert stages and stages[0].startswith("overdue-")
    s = ModuleSettings.load()
    s.overdue_reminders = False
    s.save()
    assert not any(e.pk == event.pk for e, _s in due_reminders(monday).get(admin, []))


def test_reminder_days_setting_validation(db):
    from django.core.exceptions import ValidationError

    s = ModuleSettings.load()
    s.reminder_days_review = "120, 60,x"
    with pytest.raises(ValidationError):
        s.full_clean()
    s.reminder_days_review = "120, 60"
    assert s.reminder_days("review") == [120, 60]
