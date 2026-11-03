# SPDX-License-Identifier: AGPL-3.0-or-later
from django.contrib import admin

from apps.core.admin_roles import RoleAdminMixin, RoleInlineMixin

from .models import BudgetLine, CostHeading, Expenditure, Schedule, ScheduleMember, ScheduleYear


class MemberInline(RoleInlineMixin, admin.TabularInline):
    model = ScheduleMember
    extra = 0
    autocomplete_fields = ["lease"]


@admin.register(Schedule)
class ScheduleAdmin(RoleAdminMixin, admin.ModelAdmin):
    list_display = ("name", "basis", "active")
    list_filter = ("active", "basis")
    search_fields = ("name",)
    filter_horizontal = ("properties",)
    inlines = [MemberInline]

    def view_on_site(self, obj):
        return obj.get_absolute_url()


class BudgetInline(RoleInlineMixin, admin.TabularInline):
    model = BudgetLine
    extra = 0


class ExpenditureInline(RoleInlineMixin, admin.TabularInline):
    model = Expenditure
    extra = 0
    fields = ("spent_on", "kind", "heading", "supplier", "description", "invoice_reference", "amount", "recoverable")


@admin.register(ScheduleYear)
class ScheduleYearAdmin(RoleAdminMixin, admin.ModelAdmin):
    list_display = ("schedule", "start", "end", "status")
    list_filter = ("status", "schedule")
    readonly_fields = ("status", "budget_approved_on", "reconciled_on")
    fields = ("schedule", "start", "end", "status", "budget_approved_on", "budget_commentary", "budget_issued_on",
              "reconciled_on", "statements_issued_on", "certified_by", "certification_notes", "notes")
    inlines = [BudgetInline, ExpenditureInline]

    def view_on_site(self, obj):
        return obj.get_absolute_url()

    def get_inlines(self, request, obj):
        if obj and obj.status == ScheduleYear.Status.RECONCILED:
            return []  # a reconciled year is closed
        return super().get_inlines(request, obj)


@admin.register(CostHeading)
class CostHeadingAdmin(RoleAdminMixin, admin.ModelAdmin):
    list_display = ("code", "name", "order")
    list_editable = ("order",)
