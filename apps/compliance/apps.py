# SPDX-License-Identifier: AGPL-3.0-or-later
from django.apps import AppConfig
from django.db import connection
from django.db.models.signals import post_migrate


class ComplianceConfig(AppConfig):
    name = "apps.compliance"
    label = "compliance"
    verbose_name = "Compliance and building information"

    def ready(self):
        from apps.core import audit

        from .models import Action, BuildingDocument, BuildingSafety, Certificate, ComplianceType, Requirement

        for model in (Action, BuildingDocument, BuildingSafety, Certificate, ComplianceType, Requirement):
            audit.register(model)

        def seed(sender, **kwargs):
            if sender.label == "compliance" and "compliance_compliancetype" in connection.introspection.table_names():
                from .seed import ensure_types

                ensure_types()

        post_migrate.connect(seed, dispatch_uid="phaema_compliance_types", weak=False)
