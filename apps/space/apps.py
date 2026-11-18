# SPDX-License-Identifier: AGPL-3.0-or-later
from django.apps import AppConfig
from django.db import connection
from django.db.models.signals import post_migrate


class SpaceConfig(AppConfig):
    name = "apps.space"
    label = "space"
    verbose_name = "Space and costing"

    def ready(self):
        from apps.core import audit

        from .models import Headcount, Occupation, Occupier, Space, UseFigure, UseMeasure

        for model in (Occupier, Space, Occupation, Headcount, UseMeasure, UseFigure):
            audit.register(model)

        def seed(sender, **kwargs):
            if sender.label == "space" and "space_usemeasure" in connection.introspection.table_names():
                from .seed import ensure_measures

                ensure_measures()

        post_migrate.connect(seed, dispatch_uid="phaema_space_measures", weak=False)
