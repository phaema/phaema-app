# SPDX-License-Identifier: AGPL-3.0-or-later
from django.contrib import admin

from apps.core.admin_roles import RoleAdminMixin

from .models import Component, Contract, Contractor, Job, PlannedTask


@admin.register(Contractor)
class ContractorAdmin(RoleAdminMixin, admin.ModelAdmin):
    list_display = ("name", "trades", "approved", "insurance_expires", "active")
    list_filter = ("approved", "active")
    search_fields = ("name", "trades", "company_number")
    fieldsets = (
        (None, {"fields": ("name", "company_number", "trades", "approved", "active")}),
        ("Contact", {"fields": ("contact_name", "email", "phone", "emergency_phone", "address")}),
        ("Insurance and accreditation", {"fields": ("insurer", "public_liability", "insurance_expires",
                                                    "accreditations")}),
        ("Finance", {"fields": ("finance_supplier_ref", "notes")}),
    )

    def view_on_site(self, obj):
        return obj.get_absolute_url()


@admin.register(Contract)
class ContractAdmin(RoleAdminMixin, admin.ModelAdmin):
    list_display = ("title", "contractor", "starts", "ends", "annual_value", "retender_due")
    search_fields = ("title", "reference", "contractor__name")
    autocomplete_fields = ("contractor", "properties")


@admin.register(Component)
class ComponentAdmin(RoleAdminMixin, admin.ModelAdmin):
    list_display = ("name", "property", "category", "condition", "replace_year", "replacement_cost")
    list_filter = ("category", "condition", "capital")
    search_fields = ("name", "property__reference", "property__name", "uniclass")
    autocomplete_fields = ("property",)
    fieldsets = (
        (None, {"fields": ("property", "name", "category", "location")}),
        ("Classification", {"fields": ("uniclass", "nrm3", "quantity", "unit")}),
        ("Life and condition", {"fields": ("installed_year", "life_years", "condition", "condition_on",
                                           "replacement_cost", "capital")}),
        ("Notes", {"fields": ("notes",)}),
    )

    def view_on_site(self, obj):
        return obj.get_absolute_url()


@admin.register(PlannedTask)
class PlannedTaskAdmin(RoleAdminMixin, admin.ModelAdmin):
    list_display = ("title", "property", "frequency_months", "statutory", "next_due", "contractor", "active")
    list_filter = ("statutory", "category", "active")
    search_fields = ("title", "property__reference", "property__name")
    autocomplete_fields = ("property", "component", "contractor", "contract")

    def view_on_site(self, obj):
        return obj.get_absolute_url()


@admin.register(Job)
class JobAdmin(RoleAdminMixin, admin.ModelAdmin):
    list_display = ("__str__", "property", "priority", "status", "contractor", "target_date")
    list_filter = ("status", "priority", "responsibility")
    search_fields = ("title", "number", "property__reference", "contractor__name")
    autocomplete_fields = ("property", "component", "planned_task", "lease", "case", "contractor")
    readonly_fields = ("approval_status", "approver", "approved_by", "approved_at", "approval_comments")

    def view_on_site(self, obj):
        return obj.get_absolute_url()
