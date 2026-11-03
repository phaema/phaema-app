# SPDX-License-Identifier: AGPL-3.0-or-later
from django.conf import settings
from django.core.management.base import BaseCommand

from apps.leases.reminders import send_reminders
from apps.leases.workflow import sync_all


class Command(BaseCommand):
    help = ("Daily housekeeping: apply stepped rents that take effect today, bring lease events up to date, "
            "and send reminders. Safe to run as often as you like.")

    def handle(self, *args, **options):
        rents = sync_all()
        from apps.cases.workflow import auto_open

        cases = auto_open()
        emails = send_reminders(base_url=settings.PHAEMA_BASE_URL)
        from apps.core.models import ModuleSettings

        if ModuleSettings.load().service_charges_enabled:
            from apps.servicecharges.deadlines import send_weekly

            emails += send_weekly(base_url=settings.PHAEMA_BASE_URL)
        jobs = 0
        if ModuleSettings.load().maintenance_enabled:
            from apps.maintenance.workflow import auto_raise

            jobs = auto_raise()
        self.stdout.write(f"Rents updated: {rents}. Cases opened: {cases}. Planned jobs raised: {jobs}. "
                          f"Reminder emails sent: {emails}.")
