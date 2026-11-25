# SPDX-License-Identifier: AGPL-3.0-or-later
from django.contrib import admin

from .models import BaseRate, ChaseStage


@admin.register(BaseRate)
class BaseRateAdmin(admin.ModelAdmin):
    list_display = ("effective_from", "rate")
    date_hierarchy = "effective_from"


@admin.register(ChaseStage)
class ChaseStageAdmin(admin.ModelAdmin):
    list_display = ("name", "days_overdue", "action", "template_code", "minimum_overdue")
    list_editable = ("days_overdue",)
    fields = ("order", "name", "days_overdue", "action", "template_code", "minimum_overdue")
