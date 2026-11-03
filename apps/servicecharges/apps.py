# SPDX-License-Identifier: AGPL-3.0-or-later
from django.apps import AppConfig
from django.db.models.signals import post_migrate


class ServiceChargesConfig(AppConfig):
    name = "apps.servicecharges"
    label = "servicecharges"
    verbose_name = "Service charges"

    def ready(self):
        from apps.core import audit

        from .models import BudgetLine, CostHeading, Expenditure, Schedule, ScheduleMember, ScheduleYear

        for model in (BudgetLine, CostHeading, Expenditure, Schedule, ScheduleMember, ScheduleYear):
            audit.register(model)

        def headings(sender, **kwargs):
            if sender.label == "servicecharges":
                from .models import ensure_headings

                ensure_headings()

        post_migrate.connect(headings, dispatch_uid="phaema_sc_headings", weak=False)
