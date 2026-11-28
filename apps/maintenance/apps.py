# SPDX-License-Identifier: AGPL-3.0-or-later
from django.apps import AppConfig


class MaintenanceConfig(AppConfig):
    name = "apps.maintenance"
    label = "maintenance"
    verbose_name = "Maintenance"

    def ready(self):
        from apps.core import audit

        from .models import (
            Component,
            ConditionSurvey,
            Contract,
            Contractor,
            ContractorAccount,
            Job,
            JobDocument,
            JobUpdate,
            PlannedTask,
            RepairReport,
            SurveyItem,
        )

        # Condition surveys and their findings drive capital spending decisions, and contractors' updates are
        # evidence of the work done, so all of them go in the change log. Contractor sign-in codes do not: they
        # are short-lived secrets, and a sign-in is recorded on the account's last_sign_in (see core.audit).
        for model in (Component, ConditionSurvey, Contract, Contractor, ContractorAccount, Job, JobDocument,
                      JobUpdate, PlannedTask, RepairReport, SurveyItem):
            audit.register(model)
