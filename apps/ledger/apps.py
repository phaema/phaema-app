# SPDX-License-Identifier: AGPL-3.0-or-later
from django.apps import AppConfig


class LedgerConfig(AppConfig):
    name = "apps.ledger"
    label = "ledger"
    verbose_name = "Rent ledger"

    def ready(self):
        from apps.core import audit

        from .models import Charge, DemandRun, ExportBatch, Receipt

        for model in (Charge, DemandRun, ExportBatch, Receipt):
            audit.register(model)
