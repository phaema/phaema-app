# SPDX-License-Identifier: AGPL-3.0-or-later
from django.apps import AppConfig


class MaintenanceConfig(AppConfig):
    name = "apps.maintenance"
    label = "maintenance"
    verbose_name = "Maintenance"

    def ready(self):
        from apps.core import audit

        from .models import Component, Contract, Contractor, Job, JobDocument, PlannedTask, RepairReport

        for model in (Component, Contract, Contractor, Job, JobDocument, PlannedTask, RepairReport):
            audit.register(model)
