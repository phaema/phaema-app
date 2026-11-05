# SPDX-License-Identifier: AGPL-3.0-or-later
"""Save and restore the real sign-ins (and open test account requests) on a public test site, so its data can be
reset without losing them.

    python manage.py demo_accounts export > accounts.json
    python manage.py demo_accounts import < accounts.json

Demonstration people (usernames starting "demo.") are left out: the demo data recreates them.
Passwords are kept as their stored hashes, never in plain text.
"""
import json
import sys

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.core.models import AccessArea, AccountRequest, StaffProfile

FIELDS = ("username", "first_name", "last_name", "email", "password", "is_active", "is_staff", "is_superuser")


class Command(BaseCommand):
    help = "Export or import the non-demonstration user accounts of a test site (as JSON on stdout/stdin)."
    stealth_options = ("stdin",)

    def add_arguments(self, parser):
        parser.add_argument("action", choices=("export", "import"))

    def handle(self, *args, action, **options):
        if not settings.PHAEMA_DEMO_SITE:
            raise CommandError("Only for a test site: set PHAEMA_DEMO_SITE=True first.")
        if action == "export":
            data = {"accounts": export_accounts(), "requests": export_requests()}
            self.stdout.write(json.dumps(data, indent=1))
        else:
            data = json.load(options.get("stdin") or sys.stdin)
            count = import_accounts(data["accounts"])
            requests = import_requests(data.get("requests", []))
            self.stderr.write(f"Restored {count} accounts and {requests} account requests.")


def export_accounts():
    rows = []
    for user in get_user_model().objects.exclude(username__startswith="demo.").order_by("pk"):
        profile = StaffProfile.objects.filter(user=user).select_related("supervisor").first()
        rows.append({
            **{f: getattr(user, f) for f in FIELDS},
            "groups": sorted(user.groups.values_list("name", flat=True)),
            "areas": sorted(user.access_areas.values_list("code", flat=True)),
            "job_title": profile.job_title if profile else "",
            "supervisor": profile.supervisor.username if profile and profile.supervisor else "",
        })
    return rows


@transaction.atomic
def import_accounts(rows):
    User = get_user_model()
    for row in rows:
        user, _ = User.objects.update_or_create(username=row["username"],
                                                defaults={f: row[f] for f in FIELDS if f != "username"})
        user.groups.set(Group.objects.filter(name__in=row["groups"]))
        user.access_areas.set(AccessArea.objects.filter(code__in=row["areas"]))
    for row in rows:  # supervisors second, once everyone exists
        if row["job_title"] or row["supervisor"]:
            StaffProfile.objects.update_or_create(user=User.objects.get(username=row["username"]), defaults={
                "job_title": row["job_title"],
                "supervisor": User.objects.filter(username=row["supervisor"]).first() if row["supervisor"] else None,
            })
    return len(rows)


REQUEST_FIELDS = ("name", "email", "organisation", "reason", "done")


def export_requests():
    return [{**{f: getattr(r, f) for f in REQUEST_FIELDS}, "requested_at": r.requested_at.isoformat()}
            for r in AccountRequest.objects.filter(done=False)]


@transaction.atomic
def import_requests(rows):
    from django.utils.dateparse import parse_datetime

    for row in rows:
        req = AccountRequest.objects.create(**{f: row[f] for f in REQUEST_FIELDS})
        AccountRequest.objects.filter(pk=req.pk).update(requested_at=parse_datetime(row["requested_at"]))
    return len(rows)
