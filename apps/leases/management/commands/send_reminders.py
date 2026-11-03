# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import date

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.leases.reminders import send_reminders


class Command(BaseCommand):
    help = "Email lease event reminders that have fallen due (safe to run repeatedly)."

    def add_arguments(self, parser):
        parser.add_argument("--date", help="Pretend today is this date (YYYY-MM-DD), for testing.")

    def handle(self, *args, **options):
        today = date.fromisoformat(options["date"]) if options.get("date") else None
        n = send_reminders(today, base_url=settings.PHAEMA_BASE_URL)
        self.stdout.write(f"Reminder emails sent: {n}")
