# SPDX-License-Identifier: AGPL-3.0-or-later
from django.apps import AppConfig
from django.db import connection
from django.db.models.signals import post_migrate


class ValuationsConfig(AppConfig):
    name = "apps.valuations"
    label = "valuations"
    verbose_name = "Asset valuation"

    def ready(self):
        from apps.core import audit

        from .models import AssetClass, Classification, Valuation, ValuationComponent, ValuationSettings, Valuer

        for model in (AssetClass, Classification, Valuation, ValuationComponent, ValuationSettings, Valuer):
            audit.register(model)

        def seed(sender, **kwargs):
            if sender.label == "valuations" and "valuations_assetclass" in connection.introspection.table_names():
                from .seed import ensure_classes

                ensure_classes()

        post_migrate.connect(seed, dispatch_uid="phaema_asset_classes", weak=False)
