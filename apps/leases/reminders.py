# SPDX-License-Identifier: AGPL-3.0-or-later
"""Email reminders for lease events.

Each event type has reminder points, e.g. 180, 90 and 30 days before (set in Module settings).
Each person gets one email a day at most, listing every event that has reached a new reminder
point. Each point is sent once only, so running this more often is harmless; if a day is missed,
only the most recent point is sent. Overdue events are listed again once a week, on Mondays.
Events assigned to nobody are sent to the administrators.
"""
from collections import defaultdict
from datetime import date

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.template.loader import render_to_string

from apps.core.models import ModuleSettings
from apps.core.roles import ADMINISTRATORS

from .models import LeaseEvent, ReminderLog
from .workflow import OPEN


def _stage(event, days, settings_obj, today):
    """The reminder point this event has reached today, or None."""
    to_go = (event.due_date - today).days
    if to_go < 0:
        if settings_obj.overdue_reminders and today.weekday() == 0:
            year, week, _ = today.isocalendar()
            return f"overdue-{year}-W{week:02d}"
        return None
    reached = [d for d in days if to_go <= d]
    return str(min(reached)) if reached else None


def _recipients(event, admins):
    if event.assigned_to and event.assigned_to.is_active and event.assigned_to.email:
        return [event.assigned_to]
    return admins


def due_reminders(today=None):
    """{user: [(event, stage), ...]} for reminders not yet sent."""
    today = today or date.today()
    settings_obj = ModuleSettings.load()
    admins = list(get_user_model().objects.filter(is_active=True, groups__name=ADMINISTRATORS)
                  .exclude(email="").distinct())
    days_for = {t: settings_obj.reminder_days(t) for t, _label in LeaseEvent.EventType.choices}
    sent = set(ReminderLog.objects.values_list("event_id", "stage", "sent_to"))
    out = defaultdict(list)
    events = (LeaseEvent.objects.filter(status__in=OPEN, lease__status__in=("current", "holding_over"))
              .select_related("lease", "lease__counterparty", "assigned_to"))
    for event in events:
        stage = _stage(event, days_for.get(event.event_type, []), settings_obj, today)
        if not stage:
            continue
        for user in _recipients(event, admins):
            if (event.pk, stage, user.email) not in sent:
                out[user].append((event, stage))
    return out


def send_reminders(today=None, base_url=""):
    """Send the emails. Returns the number of emails sent."""
    today = today or date.today()
    count = 0
    for user, items in due_reminders(today).items():
        items.sort(key=lambda pair: pair[0].due_date)
        context = {"user": user, "items": [(e, (e.due_date - today).days) for e, _s in items],
                   "base_url": base_url.rstrip("/"), "today": today}
        subject = f"PHAEMA: {len(items)} lease event{'s' if len(items) != 1 else ''} need{'s' if len(items) == 1 else ''} attention"
        body = render_to_string("leases/email/reminders.txt", context)
        with transaction.atomic():
            try:
                for event, stage in items:
                    ReminderLog.objects.create(event=event, stage=stage, sent_to=user.email)
            except IntegrityError:
                continue  # another run got there first
            send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email])
        count += 1
    return count
