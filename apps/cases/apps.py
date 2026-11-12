# SPDX-License-Identifier: AGPL-3.0-or-later
from django.apps import AppConfig
from django.db.models.signals import post_migrate, post_save


class CasesConfig(AppConfig):
    name = "apps.cases"
    label = "cases"
    verbose_name = "Case management"

    def ready(self):
        from apps.core import audit
        from apps.leases.models import LeaseEvent

        from apps.core.models import StaffProfile

        from .models import (Approval, Case, CaseDocument, CaseNote, CaseTask, CaseType, CaseTypeChecklistItem,
                             CaseTypeTask, Correspondence)

        for model in (Approval, Case, CaseDocument, CaseNote, CaseTask, CaseType, CaseTypeChecklistItem, CaseTypeTask,
                      Correspondence,
                      StaffProfile):
            audit.register(model)

        def seed(sender, **kwargs):
            from django.db import connection

            if sender.label == "cases" and "cases_casetype" in connection.introspection.table_names():
                from .seed import ensure_case_types

                ensure_case_types()

        def event_saved(sender, instance, **kwargs):
            from .workflow import close_for_event

            close_for_event(instance)

        post_migrate.connect(seed, dispatch_uid="phaema_case_types", weak=False)
        post_save.connect(event_saved, sender=LeaseEvent, dispatch_uid="phaema_case_event", weak=False)
