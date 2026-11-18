# SPDX-License-Identifier: AGPL-3.0-or-later
from django.contrib import admin

from .models import Action, EstateStrategy, Objective


class ObjectiveInline(admin.TabularInline):
    model = Objective
    extra = 1
    fields = ("number", "title", "owner", "target_date", "order")
    show_change_link = True


@admin.register(EstateStrategy)
class EstateStrategyAdmin(admin.ModelAdmin):
    """The council's estate (asset management) strategy. Its objectives are listed here; open one to fill in its
    detail and action plan."""

    list_display = ("title", "starts_on", "ends_on", "status", "approved_by", "approved_on")
    list_filter = ("status",)
    inlines = [ObjectiveInline]
    fieldsets = ((None, {"fields": ("title", "starts_on", "ends_on", "status")}),
                 ("Approval", {"fields": ("approved_by", "approved_on", "minute_reference", "document_url")}),
                 ("Policy", {"fields": ("principles",)}))


class ActionInline(admin.TabularInline):
    model = Action
    extra = 1
    fields = ("title", "project", "case", "owner", "target_date", "status", "notes")
    raw_id_fields = ("project", "case")


@admin.register(Objective)
class ObjectiveAdmin(admin.ModelAdmin):
    list_display = ("__str__", "strategy", "owner", "target_date", "reported_status")
    list_filter = ("strategy", "reported_status")
    search_fields = ("title", "number")
    inlines = [ActionInline]
    fieldsets = ((None, {"fields": ("strategy", "number", "title", "owner", "target_date", "order")}),
                 ("As the RICS guidance suggests (all optional)", {
                     "fields": ("corporate_aim", "outcomes", "measures", "financial_effect", "risks")}),
                 ("Progress", {"fields": ("reported_status", "progress_note")}))
