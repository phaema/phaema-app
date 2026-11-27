# SPDX-License-Identifier: AGPL-3.0-or-later
from django.apps import AppConfig


class PortalConfig(AppConfig):
    name = "apps.portal"
    verbose_name = "Tenant portal"

    def ready(self):
        from apps.core import audit

        from .models import ContactChange, PortalAccount

        audit.register(PortalAccount)
        audit.register(ContactChange)
