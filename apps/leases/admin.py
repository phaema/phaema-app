# SPDX-License-Identifier: AGPL-3.0-or-later
from django.contrib import admin
from django.core.exceptions import ValidationError

from apps.core.admin_roles import RoleAdminMixin, RoleInlineMixin
from apps.core.roles import is_administrator

from .models import BreakOption, Lease, Party


class BreakInline(RoleInlineMixin, admin.TabularInline):
    model = BreakOption
    extra = 0


@admin.register(Lease)
class LeaseAdmin(RoleAdminMixin, admin.ModelAdmin):
    list_display = ("reference", "counterparty", "agreement_type", "status", "term_start", "term_end",
                    "next_review_date", "annual_rent")
    list_filter = ("direction", "agreement_type", "status", "security_of_tenure", "review_basis")
    search_fields = ("reference", "counterparty__name", "properties__reference", "properties__name")
    autocomplete_fields = ("counterparty", "guarantor", "properties")
    date_hierarchy = "term_end"
    inlines = [BreakInline]
    fieldsets = (
        (None, {"fields": ("reference", "direction", "agreement_type", "status")}),
        ("Premises and parties", {"fields": ("properties", "premises_description", "counterparty", "guarantor")}),
        ("Term", {"fields": ("lease_date", "term_start", "term_end", "actual_end", "security_of_tenure")}),
        ("Rent", {"fields": ("annual_rent", "rent_frequency", "vat_chargeable", "deposit")}),
        ("Rent review", {"fields": ("review_basis", "review_interval_years", "next_review_date")}),
        ("Terms", {"fields": ("repairing", "insurance", "service_charge_payable", "permitted_use", "alienation")}),
        ("Notes", {"fields": ("notes",)}),
    )

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if is_administrator(request.user):
            return form
        user = request.user
        existing = set(obj.properties.values_list("pk", flat=True)) if obj else set()

        class SurveyorLeaseForm(form):
            def clean_properties(self):
                props = self.cleaned_data.get("properties")
                others = [p for p in props if p.managing_surveyor_id != user.pk and p.pk not in existing]
                if others:
                    raise ValidationError("You can only add leases on properties you manage: "
                                          + ", ".join(str(p) for p in others))
                return props

        return SurveyorLeaseForm


@admin.register(Party)
class PartyAdmin(RoleAdminMixin, admin.ModelAdmin):
    list_display = ("name", "party_type", "contact_name", "email", "phone", "finance_customer_ref")
    list_filter = ("party_type",)
    search_fields = ("name", "company_number", "charity_number", "contact_name", "email", "finance_customer_ref")
