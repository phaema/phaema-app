# SPDX-License-Identifier: AGPL-3.0-or-later
"""The kinds of record that can be listed, exported and reported on, and their columns.

Each field has a label, a type (which sets formatting and the filters offered) and, where it
can be filtered and sorted in the database, an ORM path. Fields without a path (for example a
lease's list of premises) can be shown and exported but not filtered or sorted.
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Callable, Optional

from django.db.models import Count, DecimalField, IntegerField, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce

# Field types: text, choice, date, money, area, number, bool, user
NUMERIC = {"money", "area", "number"}


@dataclass
class Field:
    key: str
    label: str
    type: str = "text"
    path: Optional[str] = None          # ORM path for filtering and sorting
    getter: Optional[Callable] = None   # how to read the value from a record
    choices: list = field(default_factory=list)
    default: bool = False               # shown by default in exports and new reports

    @property
    def filterable(self):
        return self.path is not None

    def value(self, obj):
        if self.getter:
            return self.getter(obj)
        value = obj
        for part in self.path.split("__"):
            value = getattr(value, part, None) if value is not None else None
        if self.type == "choice" and value not in (None, ""):
            return dict(self.choices).get(value, value)
        if self.type == "user":
            return (value.get_full_name() or value.username) if value else ""
        return value


@dataclass
class Dataset:
    key: str
    label: str
    description: str
    queryset: Callable
    fields: list

    def field(self, key):
        return next((f for f in self.fields if f.key == key), None)

    @property
    def default_columns(self):
        return [f.key for f in self.fields if f.default]


def _choices(model, name):
    return [(str(v), str(label)) for v, label in model._meta.get_field(name).choices]


def _user_name(user):
    return (user.get_full_name() or user.username) if user else ""


# ------------------------------------------------------------------ properties

def _properties():
    from apps.properties.models import Property

    return Property.objects.select_related("parent", "managing_surveyor").prefetch_related("titles", "leases")


def _property_rent(p):
    return sum((lease.annual_rent for lease in p.leases.all()
                if lease.status in ("current", "holding_over") and lease.direction == "out"), Decimal("0"))


def _property_fields():
    from apps.properties.models import Property as P

    return [
        Field("reference", "Reference", path="reference", default=True),
        Field("name", "Name", path="name", default=True),
        Field("property_type", "Type", "choice", "property_type", choices=_choices(P, "property_type"), default=True),
        Field("parent", "Part of (reference)", path="parent__reference"),
        Field("parent_name", "Part of (name)", path="parent__name"),
        Field("uprn", "UPRN", path="uprn", default=True),
        Field("usrn", "USRN", path="usrn"),
        Field("address_line_1", "Address line 1", path="address_line_1", default=True),
        Field("address_line_2", "Address line 2", path="address_line_2"),
        Field("town", "Town", path="town", default=True),
        Field("postcode", "Postcode", path="postcode", default=True),
        Field("holding_purpose", "Holding purpose", "choice", "holding_purpose",
              choices=_choices(P, "holding_purpose"), default=True),
        Field("tenure", "Tenure", "choice", "tenure", choices=_choices(P, "tenure"), default=True),
        Field("occupation", "Occupation", "choice", "occupation", choices=_choices(P, "occupation"), default=True),
        Field("use_description", "Use", path="use_description", default=True),
        Field("use_class", "Use class", path="use_class"),
        Field("gia_sqm", "GIA m²", "area", "gia_sqm", default=True),
        Field("nia_sqm", "NIA m²", "area", "nia_sqm", default=True),
        Field("site_area_ha", "Site area ha", "area", "site_area_ha"),
        Field("gea_sqm", "GEA m²", "area", "gea_sqm"),
        Field("area_standard", "Areas measured to", "choice", "area_standard", choices=_choices(P, "area_standard")),
        Field("area_source", "Source of areas", "choice", "area_source", choices=_choices(P, "area_source")),
        Field("areas_measured_on", "Areas measured on", "date", "areas_measured_on"),
        Field("easting", "Easting", "number", "easting"),
        Field("northing", "Northing", "number", "northing"),
        Field("managing_surveyor", "Managing surveyor", "user", "managing_surveyor", default=True),
        Field("titles", "Title numbers", getter=lambda p: "; ".join(str(t) for t in p.titles.all())),
        Field("current_rent", "Current rent £ a year (let out)", "money", getter=_property_rent),
        Field("boundary_source", "Boundary source", path="boundary_source"),
        Field("exclude_from_publication", "Excluded from open data", "bool", "exclude_from_publication"),
        Field("notes", "Notes", path="notes"),
        Field("updated_at", "Last changed", "date", "updated_at"),
    ]


# ------------------------------------------------------------------ leases

def _leases():
    from apps.leases.models import Lease

    return Lease.objects.select_related("counterparty", "guarantor").prefetch_related(
        "properties", "properties__managing_surveyor")


def _lease_fields():
    from apps.leases.models import Lease as L

    return [
        Field("reference", "Reference", path="reference", default=True),
        Field("direction", "Direction", "choice", "direction",
              choices=[("out", "Let out"), ("in", "Held by the council")], default=True),
        Field("agreement_type", "Type", "choice", "agreement_type", choices=_choices(L, "agreement_type"), default=True),
        Field("status", "Status", "choice", "status", choices=_choices(L, "status"), default=True),
        Field("premises", "Premises", getter=lambda lease: "; ".join(p.name for p in lease.properties.all()), default=True),
        Field("premises_refs", "Premises references",
              getter=lambda lease: "; ".join(p.reference for p in lease.properties.all())),
        Field("counterparty", "Tenant or landlord", path="counterparty__name", default=True),
        Field("guarantor", "Guarantor", path="guarantor__name"),
        Field("lease_date", "Date of agreement", "date", "lease_date"),
        Field("term_start", "Term start", "date", "term_start", default=True),
        Field("term_end", "Expiry", "date", "term_end", default=True),
        Field("term", "Term", getter=lambda lease: str(lease.term_description)),
        Field("actual_end", "Date ended", "date", "actual_end"),
        Field("security_of_tenure", "Security of tenure", "choice", "security_of_tenure",
              choices=_choices(L, "security_of_tenure"), default=True),
        Field("annual_rent", "Rent £ a year", "money", "annual_rent", default=True),
        Field("rent_frequency", "Rent payable", "choice", "rent_frequency", choices=_choices(L, "rent_frequency")),
        Field("vat_chargeable", "VAT charged", "bool", "vat_chargeable"),
        Field("deposit", "Rent deposit £", "money", "deposit"),
        Field("deposit_held", "Deposit held", path="deposit_held"),
        Field("rates_excluded", "Rent excludes rates", "bool", "rates_excluded"),
        Field("incentives", "Incentives", path="incentives"),
        Field("review_basis", "Review basis", "choice", "review_basis", choices=_choices(L, "review_basis")),
        Field("review_interval_years", "Review every (years)", "number", "review_interval_years"),
        Field("next_review_date", "Next rent review", "date", "next_review_date", default=True),
        Field("repairing", "Repairing", "choice", "repairing", choices=_choices(L, "repairing")),
        Field("insurance", "Insurance", "choice", "insurance", choices=_choices(L, "insurance")),
        Field("service_charge_payable", "Service charge payable", "bool", "service_charge_payable"),
        Field("permitted_use", "Permitted use", path="permitted_use"),
        Field("alterations", "Alterations", path="alterations"),
        Field("special_rights", "Special rights", path="special_rights"),
        Field("surveyor", "Managing surveyor", getter=lambda lease: next(
            (_user_name(p.managing_surveyor) for p in lease.properties.all() if p.managing_surveyor), "")),
        Field("notes", "Notes", path="notes"),
    ]


# ------------------------------------------------------------------ events

def _events():
    from apps.leases.models import LeaseEvent

    return LeaseEvent.objects.select_related("lease", "lease__counterparty", "assigned_to").prefetch_related(
        "lease__properties")


def _event_fields():
    from apps.leases.models import LeaseEvent as E

    return [
        Field("due_date", "Due", "date", "due_date", default=True),
        Field("event_type", "Event", "choice", "event_type", choices=_choices(E, "event_type"), default=True),
        Field("title", "Title", getter=lambda e: e.display_title, default=True),
        Field("status", "Status", "choice", "status", choices=_choices(E, "status"), default=True),
        Field("lease", "Agreement", path="lease__reference", default=True),
        Field("tenant", "Tenant or landlord", path="lease__counterparty__name", default=True),
        Field("premises", "Premises", getter=lambda e: "; ".join(p.name for p in e.lease.properties.all()), default=True),
        Field("assigned_to", "Assigned to", "user", "assigned_to", default=True),
        Field("completed_on", "Completed on", "date", "completed_on"),
        Field("outcome", "Outcome and notes", path="outcome"),
        Field("current_rent", "Current rent £ a year", "money", "lease__annual_rent"),
    ]


# ------------------------------------------------------------------ parties

def _parties():
    from apps.leases.models import Lease, Party

    live = Lease.objects.filter(counterparty=OuterRef("pk"), status__in=["current", "holding_over"]).order_by()
    return Party.objects.annotate(
        n_current=Coalesce(Subquery(live.values("counterparty").annotate(n=Count("pk")).values("n"),
                                    output_field=IntegerField()), Value(0)),
        current_rent=Coalesce(Subquery(live.values("counterparty").annotate(t=Sum("annual_rent")).values("t"),
                                       output_field=DecimalField()), Value(Decimal("0"))),
    )


def _party_fields():
    from apps.leases.models import Party as Pa

    return [
        Field("name", "Name", path="name", default=True),
        Field("party_type", "Type", "choice", "party_type", choices=_choices(Pa, "party_type"), default=True),
        Field("company_number", "Company number", path="company_number"),
        Field("charity_number", "Charity number", path="charity_number"),
        Field("contact_name", "Contact", path="contact_name", default=True),
        Field("email", "Email", path="email", default=True),
        Field("phone", "Phone", path="phone", default=True),
        Field("address", "Address", path="address"),
        Field("finance_customer_ref", "Finance customer number", path="finance_customer_ref", default=True),
        Field("n_current", "Current agreements", "number", "n_current", default=True),
        Field("current_rent", "Current rent £ a year", "money", "current_rent", default=True),
    ]


# ------------------------------------------------------------------ rent schedule and titles

def _rents():
    from apps.leases.models import RentScheduleEntry

    return RentScheduleEntry.objects.select_related("lease", "lease__counterparty")


def _rent_fields():
    from apps.leases.models import RentScheduleEntry as R

    return [
        Field("lease", "Agreement", path="lease__reference", default=True),
        Field("tenant", "Tenant", path="lease__counterparty__name", default=True),
        Field("effective_from", "Effective from", "date", "effective_from", default=True),
        Field("annual_rent", "Rent £ a year", "money", "annual_rent", default=True),
        Field("reason", "Reason", "choice", "reason", choices=_choices(R, "reason"), default=True),
        Field("notes", "Notes", path="notes", default=True),
    ]


# ------------------------------------------------------------------ rent ledger

def _figures(mapping, name, output):
    """Annotate a queryset with a value worked out in Python, per row, so it can be filtered and sorted."""
    from django.db.models import Case, When

    whens = [When(pk=pk, then=Value(v)) for pk, v in mapping.items() if v is not None]
    return {name: Case(*whens, default=Value(None), output_field=output) if whens else
            Value(None, output_field=output)}


def _ledger_state(today=None):
    """Every rent account, worked out once: what is owed on each charge and each agreement's totals."""
    from apps.ledger import billing

    today = today or date.today()
    owed, days, leases = {}, {}, {}
    for acc in billing.accounts(today):
        for line in acc.lines:
            if line.kind == "charge" and line.outstanding > 0:
                owed[line.obj.pk] = line.outstanding
                if line.obj.due_date < today:
                    days[line.obj.pk] = (today - line.obj.due_date).days
        leases[acc.lease.pk] = acc
    return owed, days, leases


def _charges():
    from apps.ledger.models import Charge

    owed, days, _accounts = _ledger_state()
    money, whole = DecimalField(max_digits=12, decimal_places=2), IntegerField()
    return Charge.objects.select_related("lease", "lease__counterparty", "export").annotate(
        **_figures(owed, "outstanding", money), **_figures(days, "days_overdue", whole))


def _rent_accounts():
    from django.db.models import Max

    from apps.leases.models import Lease
    from apps.ledger.billing import AGE_BANDS

    _owed, _days, accounts = _ledger_state()
    money = DecimalField(max_digits=12, decimal_places=2)
    figures = {}
    figures.update(_figures({pk: a.balance for pk, a in accounts.items()}, "balance", money))
    figures.update(_figures({pk: a.overdue for pk, a in accounts.items()}, "overdue", money))
    for i, (_limit, label) in enumerate(AGE_BANDS):
        figures.update(_figures({pk: dict(a.aged)[label] for pk, a in accounts.items()}, f"aged_{i}", money))
    return (Lease.objects.filter(pk__in=list(accounts)).select_related("counterparty")
            .prefetch_related("properties", "properties__managing_surveyor")
            .annotate(last_paid=Max("receipts__received_on"), **figures))


def _rent_account_fields():
    from apps.ledger.billing import AGE_BANDS

    return [
        Field("reference", "Agreement", path="reference", default=True),
        Field("tenant", "Tenant", path="counterparty__name", default=True),
        Field("customer_ref", "Customer reference", path="counterparty__finance_customer_ref"),
        Field("contact_name", "Contact", path="counterparty__contact_name"),
        Field("phone", "Phone", path="counterparty__phone"),
        Field("email", "Email", path="counterparty__email"),
        Field("premises", "Premises", getter=lambda lease: "; ".join(p.name for p in lease.properties.all())),
        Field("surveyor", "Managing surveyor", getter=lambda lease: next(
            (_user_name(p.managing_surveyor) for p in lease.properties.all() if p.managing_surveyor), "")),
        Field("status", "Agreement status", "choice", "status", choices=_lease_status_choices()),
        Field("annual_rent", "Rent £ a year", "money", "annual_rent"),
        Field("balance", "Balance", "money", "balance", default=True),
        Field("overdue", "Overdue", "money", "overdue", default=True),
    ] + [Field(f"aged_{i}", f"Overdue {label}", "money", f"aged_{i}", default=True)
         for i, (_l, label) in enumerate(AGE_BANDS)] + [
        Field("last_paid", "Last payment", "date", "last_paid", default=True),
    ]


def _lease_status_choices():
    from apps.leases.models import Lease

    return _choices(Lease, "status")


def _charge_fields():
    from apps.ledger.models import Charge as C

    return [
        Field("reference", "Reference", getter=lambda c: c.reference, default=True),
        Field("invoice_number", "Invoice number", path="invoice_number"),
        Field("kind", "Type", "choice", "kind", choices=_choices(C, "kind"), default=True),
        Field("lease", "Agreement", path="lease__reference", default=True),
        Field("tenant", "Tenant", path="lease__counterparty__name", default=True),
        Field("customer_ref", "Customer reference", path="lease__counterparty__finance_customer_ref"),
        Field("description", "Description", path="description", default=True),
        Field("period_start", "Period from", "date", "period_start"),
        Field("period_end", "Period to", "date", "period_end"),
        Field("issue_date", "Issued", "date", "issue_date"),
        Field("due_date", "Due", "date", "due_date", default=True),
        Field("net", "Net", "money", "net", default=True),
        Field("vat", "VAT", "money", "vat", default=True),
        Field("gross", "Total", "money", "gross", default=True),
        Field("waiting", "Waiting to go to finance", "bool", "export__isnull",
              getter=lambda c: c.export_id is None),
        Field("outstanding", "Still owed", "money", "outstanding", default=True),
        Field("days_overdue", "Days overdue", "number", "days_overdue"),
    ]


def _receipts():
    from apps.ledger.models import Receipt

    return Receipt.objects.select_related("lease", "lease__counterparty")


def _receipt_fields():
    return [
        Field("received_on", "Received", "date", "received_on", default=True),
        Field("payment_reference", "Payment reference", path="payment_reference", default=True),
        Field("lease", "Agreement", path="lease__reference", default=True),
        Field("tenant", "Tenant", path="lease__counterparty__name", default=True),
        Field("quoted_reference", "Reference quoted", path="quoted_reference", default=True),
        Field("amount", "Amount", "money", "amount", default=True),
        Field("notes", "Notes", path="notes"),
    ]


def _cases():
    from apps.cases.models import Case

    return Case.objects.select_related("case_type", "owner", "lease", "property", "party").prefetch_related(
        "lease__properties")


def _days_to_decision(case):
    start = case.application_complete_on or case.received_on
    return (case.decision_on - start).days if case.decision_on and start else None


def _case_fields():
    from apps.cases.models import Case as K, CaseType as T

    return [
        Field("reference", "Case", getter=lambda c: c.display_reference, default=True),
        Field("case_type", "Type", path="case_type__name", default=True),
        Field("group", "Group", "choice", "case_type__group", choices=_choices(T, "group")),
        Field("title", "Title", path="title", default=True),
        Field("stage", "Stage", "choice", "stage", choices=_choices(K, "stage"), default=True),
        Field("status", "Status", "choice", "status", choices=_choices(K, "status"), default=True),
        Field("owner", "Owner", "user", "owner", default=True),
        Field("received_on", "Received", "date", "received_on", default=True),
        Field("acknowledged_on", "Acknowledged", "date", "acknowledged_on"),
        Field("application_complete_on", "Application complete", "date", "application_complete_on"),
        Field("target_date", "Target", "date", "target_date", default=True),
        Field("decision", "Decision", "choice", "decision", choices=_choices(K, "decision")),
        Field("decision_on", "Decision sent", "date", "decision_on"),
        Field("days_to_decision", "Days to decision", "number", getter=_days_to_decision),
        Field("closed_on", "Closed", "date", "closed_on"),
        Field("lease", "Agreement", path="lease__reference"),
        Field("property", "Property", path="property__reference"),
        Field("applicant", "Applicant", path="party__name"),
        Field("how_received", "Received by", "choice", "how_received", choices=_choices(K, "how_received")),
        Field("iken_matter", "Iken matter", path="iken_matter"),
        Field("case_type_code", "Case type (code)", "choice", "case_type__code", choices=_case_type_codes()),
        Field("notice_kind", "1954 Act notice", "choice", "notice_kind", choices=_choices(K, "notice_kind")),
        Field("notice_served_on", "Notice given", "date", "notice_served_on"),
        Field("notice_date", "Date in the notice", "date", "notice_date"),
        Field("court_deadline", "Last day to apply to court", "date", getter=_court_deadline),
        Field("heads_covered", "Heads of terms covered", "number",
              getter=lambda c: len([v for v in (c.heads_of_terms or {}).values() if str(v).strip()])),
    ]


def _case_type_codes():
    from apps.cases.seed import TYPES

    return [(t[0], t[1]) for t in TYPES]


def _court_deadline(case):
    from apps.cases.leasing import notice_dates

    return notice_dates(case).court_deadline


def _approvals():
    from apps.cases.models import Approval

    return Approval.objects.select_related("case", "case__case_type", "requested_by", "approver", "decided_by")


def _approval_fields():
    from apps.cases.models import Approval

    return [
        Field("case", "Case", getter=lambda a: a.case.display_reference, default=True),
        Field("case_title", "Title", path="case__title", default=True),
        Field("case_type", "Type", path="case__case_type__name", default=True),
        Field("stage", "To move to", "choice", "stage", choices=_choices(Approval, "stage")),
        Field("requested_by", "Asked by", "user", "requested_by", default=True),
        Field("approver", "Approver", "user", "approver", default=True),
        Field("created_at", "Asked", "date", getter=lambda a: a.created_at.date(), default=True),
        Field("status", "Status", "choice", "status", choices=_choices(Approval, "status"), default=True),
        Field("decided_by", "Decided by", "user", "decided_by", default=True),
        Field("decided_at", "Decided", "date", getter=lambda a: a.decided_at.date() if a.decided_at else None,
              default=True),
        Field("recommendation", "Recommendation", path="recommendation"),
        Field("comments", "Approver's comments", path="comments"),
    ]


def _valuations():
    from apps.valuations.models import Valuation

    return Valuation.objects.select_related("property", "asset_class", "valuer", "case", "accepted_by")


def _valuation_change(v):
    previous = v.previous()
    if previous is None or previous.value is None or v.value is None:
        return None
    return v.value - previous.value


def _valuation_fields():
    from apps.valuations.models import Valuation, Valuer

    return [
        Field("property", "Asset reference", path="property__reference", default=True),
        Field("property_name", "Asset", path="property__name", default=True),
        Field("asset_class", "Asset class", path="asset_class__name", default=True),
        Field("basis", "Basis", "choice", "basis", choices=_choices(Valuation, "basis")),
        Field("purpose", "Purpose", path="purpose"),
        Field("valuation_date", "Valuation date", "date", "valuation_date", default=True),
        Field("valuer", "Valuer", path="valuer__name", default=True),
        Field("valuer_firm", "Firm", path="valuer__firm"),
        Field("valuer_status", "Internal or external", "choice", "valuer__status",
              choices=_choices(Valuer, "status"), default=True),
        Field("status", "Status", "choice", "status", choices=_choices(Valuation, "status"), default=True),
        Field("value", "Value £", "money", "value", default=True),
        Field("land_value", "Land £", "money", "land_value"),
        Field("building_value", "Buildings £", "money", "building_value"),
        Field("change", "Change since last £", "money", getter=_valuation_change),
        Field("remaining_life", "Remaining life (years)", "number", "remaining_life"),
        Field("material_uncertainty", "Material uncertainty", "bool", "material_uncertainty"),
        Field("inspection", "Inspection", "choice", "inspection", choices=_choices(Valuation, "inspection")),
        Field("terms_agreed_on", "Terms agreed", "date", "terms_agreed_on"),
        Field("report_date", "Report date", "date", "report_date"),
        Field("accepted_on", "Accepted", "date", "accepted_on"),
        Field("case", "Case", getter=lambda v: v.case.display_reference if v.case else ""),
    ]


def _audit_reviews():
    from apps.valuations.models import AuditReview

    return AuditReview.objects.select_related("valuation__property", "valuation__valuer", "assigned_to")


def _valuation_audit_fields():
    from apps.valuations.models import AuditReview

    return [
        Field("accounts_year", "Accounts", path="accounts_year", default=True),
        Field("property", "Asset reference", path="valuation__property__reference", default=True),
        Field("property_name", "Asset", path="valuation__property__name", default=True),
        Field("value", "Value £", "money", "valuation__value"),
        Field("reason", "Why flagged", "choice", "reason", choices=_choices(AuditReview, "reason"), default=True),
        Field("auditor", "Auditor", path="auditor"),
        Field("query", "Query", path="query", default=True),
        Field("due_on", "Response due", "date", "due_on", default=True),
        Field("assigned_to", "Preparing the response", "user", "assigned_to", default=True),
        Field("status", "Status", "choice", "status", choices=_choices(AuditReview, "status"), default=True),
        Field("reported_on", "Reported", "date", "reported_on"),
        Field("outcome", "Outcome", "choice", "outcome", choices=_choices(AuditReview, "outcome")),
        Field("closed_on", "Closed", "date", "closed_on"),
    ]


def _service_years():
    from django.db.models import BooleanField, ExpressionWrapper, Q as DQ

    from apps.servicecharges.models import ScheduleYear

    return ScheduleYear.objects.select_related("schedule").annotate(
        budget_outstanding=ExpressionWrapper(DQ(budget_issued_on__isnull=True), output_field=BooleanField()),
        statements_outstanding=ExpressionWrapper(DQ(statements_issued_on__isnull=True), output_field=BooleanField()))


def _service_year_fields():
    from apps.core.dates import add_months
    from apps.servicecharges.models import ScheduleYear

    return [
        Field("schedule", "Schedule", path="schedule__name", default=True),
        Field("label", "Year", getter=lambda y: y.label, default=True),
        Field("start", "Year start", "date", "start", default=True),
        Field("end", "Year end", "date", "end", default=True),
        Field("status", "Status", "choice", "status", choices=_choices(ScheduleYear, "status"), default=True),
        Field("budget_due", "Budget due to tenants", "date", getter=lambda y: add_months(y.start, -1), default=True),
        Field("budget_issued_on", "Budget issued", "date", "budget_issued_on", default=True),
        Field("budget_outstanding", "Budget not yet issued", "bool", "budget_outstanding"),
        Field("statements_due", "Statements due", "date", getter=lambda y: add_months(y.end, 4), default=True),
        Field("statements_issued_on", "Statements issued", "date", "statements_issued_on", default=True),
        Field("statements_outstanding", "Statements not yet issued", "bool", "statements_outstanding"),
        Field("certified_by", "Certified by", path="certified_by"),
    ]


def _expenditure():
    from apps.servicecharges.models import Expenditure

    return Expenditure.objects.select_related("year__schedule", "heading")


def _expenditure_fields():
    from apps.servicecharges.models import Expenditure

    return [
        Field("schedule", "Schedule", path="year__schedule__name", default=True),
        Field("year", "Year", getter=lambda e: e.year.label, default=True),
        Field("spent_on", "Date", "date", "spent_on", default=True),
        Field("heading", "Heading", path="heading__name", default=True),
        Field("supplier", "Supplier", path="supplier", default=True),
        Field("description", "Description", path="description", default=True),
        Field("invoice_reference", "Invoice", path="invoice_reference"),
        Field("kind", "Type", "choice", "kind", choices=_choices(Expenditure, "kind")),
        Field("recoverable", "Recoverable", "bool", "recoverable", default=True),
        Field("amount", "Amount £", "money", "amount", default=True),
    ]


def _jobs():
    from apps.maintenance.models import Job

    return Job.objects.select_related("property", "contractor", "owner", "lease", "recharge")


def _job_fields():
    from apps.maintenance.models import Job as J

    return [
        Field("reference", "Job", getter=lambda j: j.reference, default=True),
        Field("title", "What needs doing", path="title", default=True),
        Field("property", "Property", path="property__reference", default=True),
        Field("property_name", "Property name", path="property__name"),
        Field("category", "Category", "choice", "category", choices=_choices(J, "category")),
        Field("priority", "Priority", "choice", "priority", choices=_choices(J, "priority"), default=True),
        Field("status", "Status", "choice", "status", choices=_choices(J, "status"), default=True),
        Field("reported_on", "Reported", "date", "reported_on", default=True),
        Field("target_date", "Target", "date", "target_date", default=True),
        Field("contractor", "Contractor", path="contractor__name", default=True),
        Field("responsibility", "Who pays", "choice", "responsibility", choices=_choices(J, "responsibility")),
        Field("estimate", "Estimate £", "money", "estimate"),
        Field("ordered_on", "Order issued", "date", "ordered_on"),
        Field("po_number", "Purchase order", path="po_number"),
        Field("completed_on", "Completed", "date", "completed_on"),
        Field("actual_cost", "Final cost £", "money", "actual_cost"),
        Field("invoice_reference", "Contractor's invoice", path="invoice_reference"),
        Field("lease", "Agreement", path="lease__reference"),
        Field("recharged", "Recharge invoice", getter=lambda j: j.recharge.reference if j.recharge else ""),
        Field("owner", "Owner", "user", "owner"),
    ]


def _components():
    from apps.maintenance.models import Component

    return Component.objects.select_related("property")


def _component_fields():
    from apps.maintenance.models import Component as C

    return [
        Field("property", "Property", path="property__reference", default=True),
        Field("property_name", "Property name", path="property__name"),
        Field("name", "Component", path="name", default=True),
        Field("category", "Category", "choice", "category", choices=_choices(C, "category"), default=True),
        Field("location", "Location", path="location"),
        Field("uniclass", "Uniclass 2015", path="uniclass"),
        Field("nrm3", "NRM3 element", path="nrm3"),
        Field("quantity", "Quantity", "number", "quantity"),
        Field("unit", "Unit", path="unit"),
        Field("installed_year", "Installed", "number", "installed_year"),
        Field("life_years", "Expected life (years)", "number", "life_years"),
        Field("replace_year", "Replace in", "number", getter=lambda c: c.replace_year, default=True),
        Field("condition", "Condition", "choice", "condition", choices=_choices(C, "condition"), default=True),
        Field("condition_on", "Condition assessed", "date", "condition_on"),
        Field("replacement_cost", "Replacement cost £", "money", "replacement_cost", default=True),
        Field("capital", "Capital", "bool", "capital"),
    ]


def _planned():
    from apps.maintenance.models import PlannedTask

    return PlannedTask.objects.filter(active=True).select_related("property", "contractor")


def _planned_fields():
    from apps.maintenance.models import PlannedTask as P

    return [
        Field("title", "Task", path="title", default=True),
        Field("property", "Property", path="property__reference", default=True),
        Field("property_name", "Property name", path="property__name"),
        Field("category", "Category", "choice", "category", choices=_choices(P, "category")),
        Field("statutory", "Statutory", "bool", "statutory", default=True),
        Field("regulation", "Law or standard", path="regulation"),
        Field("frequency_months", "Every (months)", "number", "frequency_months", default=True),
        Field("last_done", "Last done", "date", "last_done", default=True),
        Field("next_due", "Next due", "date", "next_due", default=True),
        Field("contractor", "Contractor", path="contractor__name", default=True),
        Field("estimated_cost", "Estimated cost £", "money", "estimated_cost"),
    ]


def _contracts():
    from apps.maintenance.models import Contract

    return Contract.objects.select_related("contractor").prefetch_related("properties")


def _contract_fields():
    return [
        Field("title", "Contract", path="title", default=True),
        Field("contractor", "Contractor", path="contractor__name", default=True),
        Field("reference", "Reference", path="reference"),
        Field("starts", "Starts", "date", "starts", default=True),
        Field("ends", "Ends", "date", "ends", default=True),
        Field("annual_value", "A year £", "money", "annual_value", default=True),
        Field("last_tested", "Last tendered or benchmarked", "date", "last_tested"),
        Field("retender_due", "Re-tender or benchmark by", "date", "retender_due", default=True),
        Field("service_charge", "Service charge", "bool", "service_charge"),
        Field("properties", "Properties", getter=lambda c: ", ".join(p.reference for p in c.properties.all())),
    ]


def _contractors():
    from apps.maintenance.models import Contractor

    return Contractor.objects.all()


def _contractor_fields():
    return [
        Field("name", "Contractor", path="name", default=True),
        Field("trades", "Trades", path="trades", default=True),
        Field("approved", "Approved list", "bool", "approved", default=True),
        Field("email", "Email", path="email"),
        Field("phone", "Phone", path="phone"),
        Field("insurer", "Insurer", path="insurer"),
        Field("public_liability", "Public liability £", "money", "public_liability"),
        Field("insurance_expires", "Insurance expires", "date", "insurance_expires", default=True),
        Field("accreditations", "Accreditations", path="accreditations"),
        Field("active", "Active", "bool", "active"),
    ]


def _requirements():
    from django.db.models import OuterRef, Subquery

    from apps.compliance.models import Certificate, Requirement

    latest = Certificate.objects.filter(requirement=OuterRef("pk")).order_by("-issued_on", "-pk")
    return (Requirement.objects.filter(active=True).select_related("property", "kind")
            .annotate(latest_issued=Subquery(latest.values("issued_on")[:1]),
                      latest_expiry=Subquery(latest.values("expires_on")[:1]),
                      latest_result=Subquery(latest.values("result")[:1]),
                      latest_rating=Subquery(latest.values("rating")[:1])))


def _compliance_status(req):
    if req.latest_expiry is None:
        return "Missing"
    if req.latest_expiry < date.today():
        return "Expired"
    if req.latest_result == "fail":
        return "Unsatisfactory"
    return "Expires within 60 days" if (req.latest_expiry - date.today()).days <= 60 else "Valid"


def _requirement_fields():
    from apps.compliance.models import Certificate, Requirement

    return [
        Field("property", "Property", path="property__reference", default=True),
        Field("property_name", "Property name", path="property__name", default=True),
        Field("kind", "Certificate", path="kind__name", default=True),
        Field("statutory", "Statutory", "bool", "kind__statutory"),
        Field("responsible", "Held by", "choice", "responsible", choices=_choices(Requirement, "responsible"),
              default=True),
        Field("latest_issued", "Latest", "date", "latest_issued", default=True),
        Field("latest_expiry", "Valid until", "date", "latest_expiry", default=True),
        Field("latest_result", "Result", "choice", "latest_result", choices=_choices(Certificate, "result")),
        Field("latest_rating", "Rating", path="latest_rating"),
        Field("status", "Status", getter=_compliance_status, default=True),
    ]


def _certificates():
    from apps.compliance.models import Certificate

    return Certificate.objects.select_related("requirement__property", "requirement__kind", "contractor")


def _certificate_fields():
    from apps.compliance.models import Certificate
    from apps.properties.models import Property

    bands = [(b, b) for b in "ABCDEFG"]
    return [
        Field("property", "Property", path="requirement__property__reference", default=True),
        Field("property_name", "Property name", path="requirement__property__name", default=True),
        Field("occupation", "Occupation", "choice", "requirement__property__occupation",
              choices=_choices(Property, "occupation")),
        Field("kind", "Certificate", "choice", "requirement__kind__code",
              choices=_compliance_kinds(), default=True),
        Field("issued_on", "Date", "date", "issued_on", default=True),
        Field("expires_on", "Valid until", "date", "expires_on", default=True),
        Field("result", "Result", "choice", "result", choices=_choices(Certificate, "result"), default=True),
        Field("rating", "Rating", "choice", "rating", choices=bands),
        Field("carried_out_by", "Carried out by", getter=lambda c: c.carried_out_by or str(c.contractor or "")),
        Field("reference", "Certificate number", path="reference"),
    ]


def _compliance_kinds():
    from apps.compliance.seed import TYPES

    return [(code, name) for code, name, *_rest in TYPES]


def _actions():
    from django.db.models import BooleanField, ExpressionWrapper, Q as DQ

    from apps.compliance.models import Action

    return (Action.objects.select_related("certificate__requirement__property", "certificate__requirement__kind", "job")
            .annotate(is_open=ExpressionWrapper(DQ(done_on__isnull=True), output_field=BooleanField())))


def _action_fields():
    from apps.compliance.models import Action

    return [
        Field("description", "Action", path="description", default=True),
        Field("property", "Property", path="certificate__requirement__property__reference", default=True),
        Field("kind", "From", path="certificate__requirement__kind__name", default=True),
        Field("priority", "Priority", "choice", "priority", choices=_choices(Action, "priority"), default=True),
        Field("due_on", "Due", "date", "due_on", default=True),
        Field("is_open", "Open", "bool", "is_open"),
        Field("done_on", "Done", "date", "done_on", default=True),
        Field("job", "Job", getter=lambda a: a.job.reference if a.job else ""),
    ]


def _titles():
    from apps.properties.models import Title

    return Title.objects.prefetch_related("properties", "documents")


def _title_fields():
    from apps.properties.models import Title as T

    return [
        Field("title_number", "Title number", getter=lambda t: str(t), path="title_number", default=True),
        Field("tenure", "Tenure", "choice", "tenure", choices=_choices(T, "tenure"), default=True),
        Field("title_class", "Class of title", "choice", "title_class", choices=_choices(T, "title_class"), default=True),
        Field("properties", "Properties", getter=lambda t: "; ".join(f"{p.reference} {p.name}" for p in t.properties.all()),
              default=True),
        Field("deeds_location", "Deeds location", path="deeds_location", default=True),
        Field("restrictions_and_covenants", "Restrictions, covenants and rights", path="restrictions_and_covenants"),
        Field("documents", "Documents held", "number", getter=lambda t: len(t.documents.all())),
    ]


def _audit():
    from apps.core.models import AuditEntry

    return AuditEntry.objects.select_related("user", "content_type")


def _audit_fields():
    return [
        Field("timestamp", "When", "date", "timestamp", default=True),
        Field("user", "Who", "user", "user", default=True),
        Field("action", "What", "choice", "action",
              choices=[("create", "Created"), ("update", "Changed"), ("delete", "Deleted")], default=True),
        Field("record_type", "Record type", getter=lambda e: e.content_type.name, default=True),
        Field("object_repr", "Record", path="object_repr", default=True),
        Field("fields", "Fields changed", getter=lambda e: ", ".join(e.changes or {}) if e.action == "update" else "",
              default=True),
    ]


# ------------------------------------------------------------------ projects

def _projects():
    from apps.projects.models import Project

    return Project.objects.select_related("project_type", "lead").prefetch_related(
        "property_links__property", "milestones", "budget_lines__years")


def _budget_total(project, kind, income=False):
    return sum((getattr(y, kind) for line in project.budget_lines.all() if line.is_income == income
                for y in line.years.all()), Decimal("0"))


def _project_fields():
    from apps.projects.models import Phase, Project as P

    return [
        Field("reference", "Project", getter=lambda p: p.display_reference, default=True),
        Field("name", "Name", path="name", default=True),
        Field("type", "Type", path="project_type__name", default=True),
        Field("phase", "Phase", "choice", "phase", choices=[(str(v), str(label)) for v, label in Phase.choices],
              default=True),
        Field("status", "Status", "choice", "status", choices=_choices(P, "status"), default=True),
        Field("rag", "On track?", getter=lambda p: str(p.rag()[1]), default=True),
        Field("lead", "Lead", "user", "lead", default=True),
        Field("sponsor", "Sponsor", path="sponsor"),
        Field("start_date", "Started", "date", "start_date"),
        Field("target_date", "Target completion", "date", "target_date", default=True),
        Field("confidential", "Confidential", "bool", "confidential"),
        Field("properties", "Properties", getter=lambda p: "; ".join(
            f"{link.property.reference} {link.property.name}" for link in p.property_links.all())),
        Field("site_address", "Proposed site", path="site_address"),
        Field("budget_approved", "Budget approved (costs)", "money", getter=lambda p: _budget_total(p, "approved"),
              default=True),
        Field("budget_forecast", "Forecast (costs)", "money", getter=lambda p: _budget_total(p, "forecast"),
              default=True),
        Field("budget_actual", "Spent", "money", getter=lambda p: _budget_total(p, "actual"), default=True),
        Field("income_forecast", "Income forecast", "money", getter=lambda p: _budget_total(p, "forecast", True)),
    ]


def _project_budget():
    from apps.projects.models import BudgetYear

    return BudgetYear.objects.select_related("line", "line__project", "line__project__project_type")


def _project_budget_fields():
    from apps.projects.models import BudgetLine as B

    return [
        Field("project", "Project", getter=lambda y: y.line.project.display_reference, default=True),
        Field("project_name", "Project name", path="line__project__name", default=True),
        Field("line", "Budget line", path="line__description", default=True),
        Field("category", "Category", "choice", "line__category", choices=_choices(B, "category"), default=True),
        Field("funding", "Capital or revenue", "choice", "line__funding", choices=_choices(B, "funding"), default=True),
        Field("year", "Financial year", getter=lambda y: y.label, default=True),
        Field("year_start", "Financial year starting", "number", "year"),
        Field("approved", "Approved", "money", "approved", default=True),
        Field("forecast", "Forecast", "money", "forecast", default=True),
        Field("actual", "Actual", "money", "actual", default=True),
        Field("variance", "Forecast over approved", "money", getter=lambda y: y.forecast - y.approved),
    ]


_REGISTRY = None


def registry():
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = {d.key: d for d in [
            Dataset("properties", "Properties", "The property register: estates, sites, buildings, units and land.",
                    _properties, _property_fields()),
            Dataset("leases", "Leases and licences", "Agreements let out and held by the council.", _leases, _lease_fields()),
            Dataset("events", "Lease events", "Rent reviews, breaks, expiries and other events.", _events, _event_fields()),
            Dataset("parties", "Tenants and other parties", "Tenants, landlords, guarantors and other contacts.",
                    _parties, _party_fields()),
            Dataset("rents", "Rent schedule", "Every rent: initial rents, reviews, steps and concessions.",
                    _rents, _rent_fields()),
            Dataset("charges", "Rent charges", "Rent invoices and credit notes raised by the rent ledger.",
                    _charges, _charge_fields()),
            Dataset("receipts", "Rent receipts", "Payments received, from the finance system.",
                    _receipts, _receipt_fields()),
            Dataset("rent_accounts", "Rent accounts", "Each agreement's rent balance, overdue rent by age and "
                    "last payment.", _rent_accounts, _rent_account_fields()),
            Dataset("cases", "Cases", "Consents, lease events, enquiries and other estate work.", _cases, _case_fields()),
            Dataset("jobs", "Maintenance jobs", "Reactive and planned repairs, works orders and their costs.",
                    _jobs, _job_fields()),
            Dataset("components", "Components", "The component register: building elements, plant and systems.",
                    _components, _component_fields()),
            Dataset("planned", "Planned maintenance", "Planned and statutory maintenance tasks and when they are due.",
                    _planned, _planned_fields()),
            Dataset("contracts", "Maintenance contracts", "Service contracts and their re-tender dates.",
                    _contracts, _contract_fields()),
            Dataset("contractors", "Contractors", "Contractors, their insurance and accreditations.",
                    _contractors, _contractor_fields()),
            Dataset("compliance", "Compliance register", "Each certificate a property needs, and whether it is in "
                    "date.", _requirements, _requirement_fields()),
            Dataset("certificates", "Compliance certificates", "Every certificate recorded, with results and ratings.",
                    _certificates, _certificate_fields()),
            Dataset("compliance_actions", "Remedial actions", "Actions from compliance certificates and assessments.",
                    _actions, _action_fields()),
            Dataset("approvals", "Approvals", "Requests for a supervisor's approval on cases, and the decisions.",
                    _approvals, _approval_fields()),
            Dataset("valuations", "Valuations", "Asset valuations for the accounts and other purposes.",
                    _valuations, _valuation_fields()),
            Dataset("valuation_audit", "Valuation audit", "Valuations flagged for audit, the responses and outcomes.",
                    _audit_reviews, _valuation_audit_fields()),
            Dataset("service_years", "Service charge years", "Each schedule's years, with the RICS deadlines.",
                    _service_years, _service_year_fields()),
            Dataset("expenditure", "Service charge spending", "Costs and income charged to service charges.",
                    _expenditure, _expenditure_fields()),
            Dataset("titles", "Titles", "Registered and unregistered titles.", _titles, _title_fields()),
            Dataset("changes", "Change log", "Every change made in PHAEMA.", _audit, _audit_fields()),
            Dataset("projects", "Projects", "Developments, acquisitions, disposals, programmes and reviews.",
                    _projects, _project_fields()),
            Dataset("project_budget", "Project budgets", "Each project budget line's approved, forecast and actual "
                    "figures by financial year.", _project_budget, _project_budget_fields()),
        ]}
    return _REGISTRY


def get(key):
    return registry().get(key)


# ------------------------------------------------------------------ filters

def apply_filters(dataset, qs, filters, today=None):
    """filters: {field_key: spec}. Specs by type:
    choice/user: {"in": [values]}; text: {"contains": "..."} or {"blank": true}; bool: {"is": true|false};
    number/money/area: {"min": x, "max": y}; date: {"from": "YYYY-MM-DD", "to": "...",
    "next_days": n, "last_days": n, "upto_days": n (on or before n days ahead, past included),
    "before_today": true}.
    """
    from datetime import timedelta

    today = today or date.today()
    for key, spec in (filters or {}).items():
        f = dataset.field(key)
        if not f or not f.filterable or not spec:
            continue
        path = f.path
        if f.type in ("choice",) and spec.get("in"):
            qs = qs.filter(**{f"{path}__in": spec["in"]})
        elif f.type == "user" and spec.get("in"):
            values = [v for v in spec["in"] if v != "none"]
            cond = Q(**{f"{path}_id__in": [int(v) for v in values if str(v).isdigit()]})
            if "none" in spec["in"]:
                cond |= Q(**{f"{path}__isnull": True})
            qs = qs.filter(cond)
        elif f.type == "text" and spec.get("blank"):
            qs = qs.filter(Q(**{path: ""}) | Q(**{f"{path}__isnull": True}))
        elif f.type == "text" and spec.get("contains"):
            qs = qs.filter(**{f"{path}__icontains": spec["contains"]})
        elif f.type == "bool" and spec.get("is") in (True, False):
            qs = qs.filter(**{path: spec["is"]})
        elif f.type in NUMERIC:
            if spec.get("min") not in (None, ""):
                qs = qs.filter(**{f"{path}__gte": Decimal(str(spec["min"]))})
            if spec.get("max") not in (None, ""):
                qs = qs.filter(**{f"{path}__lte": Decimal(str(spec["max"]))})
        elif f.type == "date":
            lookup = f"{path}__date" if key in ("updated_at", "timestamp") else path
            if spec.get("from"):
                qs = qs.filter(**{f"{lookup}__gte": spec["from"]})
            if spec.get("to"):
                qs = qs.filter(**{f"{lookup}__lte": spec["to"]})
            if spec.get("next_days") not in (None, ""):
                qs = qs.filter(**{f"{lookup}__gte": today,
                                  f"{lookup}__lte": today + timedelta(days=int(spec["next_days"]))})
            if spec.get("upto_days") not in (None, ""):
                qs = qs.filter(**{f"{lookup}__lte": today + timedelta(days=int(spec["upto_days"]))})
            if spec.get("last_days") not in (None, ""):
                qs = qs.filter(**{f"{lookup}__lte": today,
                                  f"{lookup}__gte": today - timedelta(days=int(spec["last_days"]))})
            if spec.get("before_today"):
                qs = qs.filter(**{f"{lookup}__lt": today})
    return qs


def rows(dataset, qs, columns):
    fields = [dataset.field(c) for c in columns if dataset.field(c)]
    return fields, ([f.value(obj) for f in fields] for obj in qs)
