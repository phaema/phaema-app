# SPDX-License-Identifier: AGPL-3.0-or-later
from django.contrib import admin

from apps.core.admin_roles import RoleAdminMixin

from .models import Case, CaseType, CaseTypeTask


class TaskTemplateInline(admin.TabularInline):
    model = CaseTypeTask
    extra = 0


@admin.register(CaseType)
class CaseTypeAdmin(RoleAdminMixin, admin.ModelAdmin):
    list_display = ("name", "group", "target_days", "acknowledge_working_days", "fee", "event_type", "active")
    list_filter = ("group", "active")
    search_fields = ("name", "code")
    inlines = [TaskTemplateInline]


@admin.register(Case)
class CaseAdmin(RoleAdminMixin, admin.ModelAdmin):
    list_display = ("__str__", "case_type", "stage", "status", "owner", "received_on", "target_date")
    list_filter = ("status", "stage", "case_type__group")
    search_fields = ("title", "number", "lease__reference", "property__reference", "party__name")
    autocomplete_fields = ["lease", "property", "party"]
    filter_horizontal = ("contributors",)
    readonly_fields = ("event",)

    def view_on_site(self, obj):
        return obj.get_absolute_url()
