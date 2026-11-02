# SPDX-License-Identifier: AGPL-3.0-or-later
from django.apps import AppConfig


class PropertiesConfig(AppConfig):
    name = "apps.properties"
    label = "properties"
    verbose_name = "Property register"

    def ready(self):
        from apps.core import audit

        from .models import Property, Title

        audit.register(Property)
        audit.register(Title)
