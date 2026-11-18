# SPDX-License-Identifier: AGPL-3.0-or-later
from django.apps import AppConfig


class StrategyConfig(AppConfig):
    name = "apps.strategy"
    label = "strategy"
    verbose_name = "Estate strategy"

    def ready(self):
        from apps.core import audit

        from .models import Action, EstateStrategy, Objective

        for model in (EstateStrategy, Objective, Action):
            audit.register(model)
