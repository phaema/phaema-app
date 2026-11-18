# SPDX-License-Identifier: AGPL-3.0-or-later
from django.contrib import admin

from .models import Action, EstateStrategy, HealthAnswer, HealthCheck, HealthQuestion, Objective


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


@admin.register(HealthQuestion)
class HealthQuestionAdmin(admin.ModelAdmin):
    """The questions in the annual asset management health check. Changes apply to checks started afterwards; past
    checks keep the wording they were answered with."""

    list_display = ("text", "heading", "active", "order")
    list_editable = ("active", "order")
    list_filter = ("heading", "active")
    search_fields = ("text",)
    fields = ("heading", "text", "guidance", "active", "order")


class HealthAnswerInline(admin.TabularInline):
    model = HealthAnswer
    extra = 0
    fields = ("heading", "wording", "answer", "answered_by", "answered_on", "action")
    readonly_fields = ("heading", "wording", "answered_by", "answered_on", "action")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(HealthCheck)
class HealthCheckAdmin(admin.ModelAdmin):
    """Each year's health check. Answer it on its own page (Estate strategy, Health check); here an administrator
    can change the lead or the status."""

    list_display = ("__str__", "lead", "status", "finished_on")
    fields = ("year", "lead", "status", "finished_on", "summary")
    inlines = [HealthAnswerInline]
