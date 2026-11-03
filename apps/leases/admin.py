# SPDX-License-Identifier: AGPL-3.0-or-later
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.urls import reverse
from django.utils.html import format_html, format_html_join

from apps.core.admin_roles import RoleAdminMixin, RoleInlineMixin
from apps.core.roles import is_administrator

from .models import BreakOption, Lease, LeaseDocument, LeaseEvent, Party, RentScheduleEntry


class BreakInline(RoleInlineMixin, admin.TabularInline):
    model = BreakOption
    extra = 0


class RentScheduleInline(RoleInlineMixin, admin.TabularInline):
    model = RentScheduleEntry
    extra = 0
    fields = ("effective_from", "annual_rent", "reason", "notes")
    verbose_name_plural = "Rent schedule (the current rent is taken from here)"


class DocumentInline(RoleInlineMixin, admin.TabularInline):
    model = LeaseDocument
    extra = 1
    fields = ("document_type", "file", "description", "document_date")


@admin.register(Lease)
class LeaseAdmin(RoleAdminMixin, admin.ModelAdmin):
    list_display = ("reference", "counterparty", "agreement_type", "status", "term_start", "term_end",
                    "next_review_date", "annual_rent")
    list_filter = ("direction", "agreement_type", "status", "security_of_tenure", "review_basis")
    search_fields = ("reference", "counterparty__name", "properties__reference", "properties__name")
    autocomplete_fields = ("counterparty", "guarantor", "properties")
    date_hierarchy = "term_end"
    inlines = [BreakInline, RentScheduleInline, DocumentInline]
    fieldsets = (
        (None, {"fields": ("reference", "direction", "agreement_type", "status")}),
        ("Premises and parties", {"fields": ("properties", "premises_description", "counterparty", "guarantor")}),
        ("Term", {"fields": ("lease_date", "term_start", "term_end", "actual_end", "security_of_tenure")}),
        ("Rent", {"fields": ("annual_rent", "rent_frequency", "vat_chargeable", "deposit")}),
        ("Rent review", {"fields": ("review_basis", "review_interval_years", "next_review_date")}),
        ("Terms", {"fields": ("repairing", "insurance", "service_charge_payable", "permitted_use", "alienation")}),
        ("Notes", {"fields": ("notes",)}),
    )

    def get_readonly_fields(self, request, obj=None):
        # Once a lease has a rent schedule, the current rent comes from it.
        return ("annual_rent",) if obj is not None and obj.rent_schedule.exists() else ()

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
    list_display = ("name", "party_type", "agreement_count", "contact_name", "email", "phone", "finance_customer_ref")
    list_filter = ("party_type",)
    search_fields = ("name", "company_number", "charity_number", "contact_name", "email", "finance_customer_ref")
    readonly_fields = ("arrangements_summary",)
    fieldsets = (
        (None, {"fields": ("name", "party_type", "company_number", "charity_number")}),
        ("Properties and agreements", {"fields": ("arrangements_summary",)}),
        ("Contact", {"fields": ("contact_name", "email", "phone", "address", "finance_customer_ref")}),
        ("Notes", {"fields": ("notes",)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            n_agreements=Count("leases", distinct=True) + Count("guarantees", distinct=True))  # distinct: no double counting

    @admin.display(description="Agreements", ordering="n_agreements")
    def agreement_count(self, obj):
        return obj.n_agreements

    @admin.display(description="All agreements and properties")
    def arrangements_summary(self, obj):
        if obj is None or obj.pk is None:
            return "Save this party first."
        rows = obj.arrangements()
        if not rows:
            return "No agreements yet."

        def premises(props):
            return format_html_join(
                "<br>", '<a href="{}">{} {}</a>',
                ((reverse("admin:properties_property_change", args=[p.pk]), p.reference, p.name) for p in props),
            )

        body = format_html_join("", (
            "<tr><td>{}</td><td><a href=\"{}\">{}</a></td><td>{}</td><td>{}</td><td>{} to {}</td>"
            "<td style=\"text-align:right\">£{}</td><td>{}</td></tr>"
        ), ((r["role"], reverse("admin:leases_lease_change", args=[r["lease"].pk]), r["lease"].reference,
             r["lease"].get_agreement_type_display(), r["lease"].get_status_display(),
             r["lease"].term_start.strftime("%d %b %Y"),
             r["lease"].term_end.strftime("%d %b %Y") if r["lease"].term_end else "periodic",
             f"{r['lease'].annual_rent:,.0f}", premises(r["properties"])) for r in rows))
        current = [r for r in rows if r["lease"].status in ("current", "holding_over") and str(r["role"]) != "Guarantor"]
        total = sum(r["lease"].annual_rent for r in current)
        return format_html(
            "<table><thead><tr><th>Role</th><th>Agreement</th><th>Type</th><th>Status</th><th>Term</th>"
            "<th>Rent a year</th><th>Properties</th></tr></thead><tbody>{}</tbody></table>"
            "<p><strong>{} current agreement(s), £{} a year.</strong> <a href=\"{}\">Open the full party page</a></p>",
            body, len(current), f"{total:,.0f}", obj.get_absolute_url(),
        )


@admin.register(LeaseEvent)
class LeaseEventAdmin(RoleAdminMixin, admin.ModelAdmin):
    list_display = ("due_date", "event_type", "title", "lease", "assigned_to", "status")
    list_filter = ("event_type", "status", "assigned_to")
    search_fields = ("lease__reference", "lease__counterparty__name", "title")
    date_hierarchy = "due_date"
    readonly_fields = ("source", "completed_by")
    autocomplete_fields = ("lease",)
