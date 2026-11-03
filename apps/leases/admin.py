# SPDX-License-Identifier: AGPL-3.0-or-later
from django.contrib import admin

from .models import BreakOption, Lease, Party


class BreakInline(admin.TabularInline):
    model = BreakOption
    extra = 0


@admin.register(Lease)
class LeaseAdmin(admin.ModelAdmin):
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


@admin.register(Party)
class PartyAdmin(admin.ModelAdmin):
    list_display = ("name", "party_type", "contact_name", "email", "phone", "finance_customer_ref")
    list_filter = ("party_type",)
    search_fields = ("name", "company_number", "charity_number", "contact_name", "email", "finance_customer_ref")
