# SPDX-License-Identifier: AGPL-3.0-or-later
from django.apps import AppConfig


class LeasesConfig(AppConfig):
    name = "apps.leases"
    label = "leases"
    verbose_name = "Leases and licences"

    def ready(self):
        from apps.core import audit

        from .models import BreakOption, Lease, Party

        for model in (Party, Lease, BreakOption):
            audit.register(model)
