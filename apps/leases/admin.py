# SPDX-License-Identifier: AGPL-3.0-or-later
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.urls import reverse
from django.utils.html import format_html, format_html_join

from apps.core.admin_roles import RoleAdminMixin, RoleInlineMixin
from apps.core.roles import is_administrator

from .models import (BreakOption, Dealing, DepositEntry, IndexFigure, IndexSeries, Lease, LeaseDocument, LeaseEvent, LeaseOption, Party,
                     RentScheduleEntry)


class BreakInline(RoleInlineMixin, admin.TabularInline):
    model = BreakOption
    extra = 0


class OptionInline(RoleInlineMixin, admin.StackedInline):
    model = LeaseOption
    extra = 0
    fields = (("option_type", "exercisable_by"), ("exercise_from", "exercise_by", "notice_months"), "terms")


class RentScheduleInline(RoleInlineMixin, admin.TabularInline):
    model = RentScheduleEntry
    extra = 0
    fields = ("effective_from", "annual_rent", "reason", "notes")
    verbose_name_plural = "Rent schedule (the current rent is taken from here)"


class DealingInline(RoleInlineMixin, admin.StackedInline):
    model = Dealing
    fk_name = "lease"
    extra = 0
    autocomplete_fields = ("to_party", "guarantor", "underlease")
    fields = (("kind", "status"), "to_party", "guarantor", "aga", "premises", ("consent_on", "completed_on"),
              ("term_start", "term_end", "annual_rent"), "underlease", "case", "licence", "notes")
    raw_id_fields = ("case",)
    verbose_name_plural = "Dealings (assignments, underleases, sharing and charges)"

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "licence":
            lease_id = request.resolver_match.kwargs.get("object_id") if request.resolver_match else None
            from .models import LeaseDocument

            kwargs["queryset"] = LeaseDocument.objects.filter(lease_id=lease_id) if lease_id else \
                LeaseDocument.objects.none()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class DepositInline(RoleInlineMixin, admin.TabularInline):
    model = DepositEntry
    extra = 0
    fields = ("date", "kind", "amount", "reference", "notes")
    verbose_name_plural = "Rent deposit account (money in and out)"


class DocumentInline(RoleInlineMixin, admin.TabularInline):
    model = LeaseDocument
    extra = 1
    fields = ("document_type", "file", "description", "document_date", "review_date")


@admin.register(Lease)
class LeaseAdmin(RoleAdminMixin, admin.ModelAdmin):
    list_display = ("reference", "counterparty", "agreement_type", "status", "term_start", "term_end",
                    "next_review_date", "annual_rent")
    list_filter = ("direction", "agreement_type", "status", "security_of_tenure", "review_basis", "time_of_essence",
                   "demands_on_hold", "arrears_referral")
    search_fields = ("reference", "counterparty__name", "properties__reference", "properties__name")
    autocomplete_fields = ("counterparty", "guarantor", "properties", "headlease")
    date_hierarchy = "term_end"
    inlines = [BreakInline, OptionInline, RentScheduleInline, DocumentInline, DealingInline, DepositInline]
    fieldsets = (
        (None, {"fields": ("reference", "direction", "agreement_type", "status")}),
        ("Premises and parties", {"fields": ("properties", "premises_description", "counterparty", "guarantor",
                                             "headlease")}),
        ("Term", {"fields": ("lease_date", "term_start", "term_end", "actual_end", "security_of_tenure")}),
        ("Rent", {"fields": ("annual_rent", "rent_frequency", "vat_chargeable", "rates_excluded", "rent_free_until", "incentives",
                             "deposit", "deposit_held", "deposit_deed_date", "deposit_interest")}),
        ("Rent review", {"fields": ("review_basis", "review_interval_years", "next_review_date", "time_of_essence")}),
        ("Index-linked reviews", {
            "fields": ("index_series", "index_base_month", "index_lag_months", ("index_cap_pct", "index_collar_pct"),
                       "index_compounded", "index_upward_only"),
            "classes": ("collapse",),
            "description": "For RPI, CPI or CPIH reviews. PHAEMA works out the new rent at each review from these "
                           "terms and the index figures, for the surveyor to check and record."}),
        ("IFRS 16 (agreements the council holds)", {
            "fields": ("ifrs16_treatment", "ifrs16_lease_end", "ifrs16_notes"),
            "classes": ("collapse",),
            "description": "For finance's lease accounting. The lease term for IFRS 16 includes periods covered by "
                           "options the council is reasonably certain to use. These feed the IFRS 16 data pack under "
                           "Finance, Rents payable."}),
        ("Rent demands and arrears", {
            "fields": ("demands_on_hold", "demands_on_hold_reason", "interest_basis", "interest_margin_pct",
                       "interest_grace_days", "arrears_referral", "arrears_referred_on",
                       "arrears_referral_reference"),
            "description": "Put demands on hold while a dispute or negotiation is sorted out, and record when the "
                           "debt has been passed to debt collectors or legal."}),
        ("Billing contact", {
            "fields": ("billing_contact_name", "billing_email", "billing_phone", "billing_address"),
            "description": "Who rent demands go to. Leave blank to use the tenant's main contact; fill in only "
                           "the details that differ."}),
        ("Terms", {"fields": ("repairing", "insurance", "service_charge_payable", "permitted_use",
                              ("assignment_terms", "underletting_terms"), "dealings_with_part", "aga_on_assignment",
                              "alienation", "alterations", "special_rights")}),
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
        current = [r for r in rows if r["lease"].status in ("current", "holding_over")
                   and not str(r["role"]).startswith(("Guarantor", "Former"))]
        total = sum(r["lease"].annual_rent for r in current)
        return format_html(
            "<table><thead><tr><th>Role</th><th>Agreement</th><th>Type</th><th>Status</th><th>Term</th>"
            "<th>Rent a year</th><th>Properties</th></tr></thead><tbody>{}</tbody></table>"
            "<p><strong>{} current agreement(s), £{} a year.</strong> <a href=\"{}\">Open the full party page</a></p>",
            body, len(current), f"{total:,.0f}", obj.get_absolute_url(),
        )


@admin.register(LeaseEvent)
class LeaseEventAdmin(RoleAdminMixin, admin.ModelAdmin):
    list_display = ("due_date", "event_type", "title", "lease", "assigned_to", "status", "estimated_rental_value")
    list_filter = ("event_type", "status", "assigned_to")
    search_fields = ("lease__reference", "lease__counterparty__name", "title")
    date_hierarchy = "due_date"
    readonly_fields = ("source", "completed_by")
    autocomplete_fields = ("lease",)


class IndexFigureInline(admin.TabularInline):
    model = IndexFigure
    extra = 1
    fields = ("month", "value")
    ordering = ("-month",)


@admin.register(IndexSeries)
class IndexSeriesAdmin(RoleAdminMixin, admin.ModelAdmin):
    list_display = ("code", "name", "ons_series", "latest_figure")
    fields = ("code", "name", "ons_series", "ons_dataset", "notes")
    inlines = [IndexFigureInline]

    @admin.display(description="Latest figure")
    def latest_figure(self, obj):
        latest = obj.latest
        return f"{latest.month:%b %Y}: {latest.value}" if latest else "none"
