# SPDX-License-Identifier: AGPL-3.0-or-later
"""The RICS service charge timetable: budgets to tenants at least one month before the year starts,
year-end statements within four months of the year end."""
from dataclasses import dataclass
from datetime import date, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.template.loader import render_to_string

from apps.core.dates import add_months
from apps.core.roles import ADMINISTRATORS

from .models import Schedule

WARN_DAYS = 60


@dataclass
class Deadline:
    schedule: object
    year: object  # None when next year's budget has not been set up
    what: str
    due: date

    @property
    def days(self):
        return (self.due - date.today()).days

    @property
    def colour(self):
        return "red" if self.days < 0 else "orange" if self.days <= 30 else "yellow"


def upcoming(today=None, window=WARN_DAYS):
    """Deadlines not yet met that are overdue or fall within `window` days."""
    today = today or date.today()
    out = []
    for schedule in Schedule.objects.filter(active=True).prefetch_related("years"):
        years = list(schedule.years.all())
        for year in years:
            if year.budget_issued_on is None and year.start > today - timedelta(days=365):
                if (year.budget_due - today).days <= window and year.end >= today:
                    out.append(Deadline(schedule, year, f"Issue the {year.label} budget to tenants", year.budget_due))
            if year.end < today and year.statements_issued_on is None:
                out.append(Deadline(schedule, year, f"Issue the {year.label} year-end statements", year.statements_due))
        latest = max(years, key=lambda y: y.start, default=None)
        if latest and (latest.end - today).days <= window + 31:
            next_start = latest.end + timedelta(days=1)
            due = add_months(next_start, -1)
            out.append(Deadline(schedule, None, f"Set up and issue the budget for the year from {next_start:%d/%m/%Y}",
                                due))
    return sorted(out, key=lambda d: d.due)


def send_weekly(today=None, base_url=""):
    """On Mondays, email administrators the service charge deadlines coming up. Returns emails sent."""
    today = today or date.today()
    if today.weekday() != 0:
        return 0
    items = upcoming(today)
    if not items:
        return 0
    admins = get_user_model().objects.filter(is_active=True, groups__name=ADMINISTRATORS).exclude(email="").distinct()
    count = 0
    for user in admins:
        body = render_to_string("servicecharges/email/deadlines.txt",
                                {"user": user, "items": items, "today": today, "base_url": base_url.rstrip("/")})
        send_mail(f"PHAEMA: {len(items)} service charge deadline{'s' if len(items) != 1 else ''}", body,
                  settings.DEFAULT_FROM_EMAIL, [user.email])
        count += 1
    return count
