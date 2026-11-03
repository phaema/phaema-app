# SPDX-License-Identifier: AGPL-3.0-or-later
from django.apps import AppConfig
from django.db.models.signals import post_migrate


class ReportsConfig(AppConfig):
    name = "apps.reports"
    label = "reports"
    verbose_name = "Reports"

    def ready(self):
        from apps.core import audit

        from .models import Report
        from .starter import ensure_starter_reports

        audit.register(Report)

        def starters(sender, **kwargs):
            if sender.label == "reports":
                ensure_starter_reports()

        post_migrate.connect(starters, dispatch_uid="phaema_starter_reports", weak=False)
