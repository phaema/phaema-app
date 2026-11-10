# SPDX-License-Identifier: AGPL-3.0-or-later
from django.apps import AppConfig


class ConnectorsConfig(AppConfig):
    name = "apps.connectors"
    label = "connectors"
    verbose_name = "Connectors"

    def ready(self):
        from apps.core import audit

        from .models import SsoGroupMapping

        audit.register(SsoGroupMapping)
