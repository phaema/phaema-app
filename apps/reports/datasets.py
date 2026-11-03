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
        Field("review_basis", "Review basis", "choice", "review_basis", choices=_choices(L, "review_basis")),
        Field("review_interval_years", "Review every (years)", "number", "review_interval_years"),
        Field("next_review_date", "Next rent review", "date", "next_review_date", default=True),
        Field("repairing", "Repairing", "choice", "repairing", choices=_choices(L, "repairing")),
        Field("insurance", "Insurance", "choice", "insurance", choices=_choices(L, "insurance")),
        Field("service_charge_payable", "Service charge payable", "bool", "service_charge_payable"),
        Field("permitted_use", "Permitted use", path="permitted_use"),
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
            Dataset("titles", "Titles", "Registered and unregistered titles.", _titles, _title_fields()),
            Dataset("changes", "Change log", "Every change made in PHAEMA.", _audit, _audit_fields()),
        ]}
    return _REGISTRY


def get(key):
    return registry().get(key)


# ------------------------------------------------------------------ filters

def apply_filters(dataset, qs, filters, today=None):
    """filters: {field_key: spec}. Specs by type:
    choice/user: {"in": [values]}; text: {"contains": "..."}; bool: {"is": true|false};
    number/money/area: {"min": x, "max": y}; date: {"from": "YYYY-MM-DD", "to": "...",
    "next_days": n, "last_days": n, "before_today": true}.
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
            if spec.get("last_days") not in (None, ""):
                qs = qs.filter(**{f"{lookup}__lte": today,
                                  f"{lookup}__gte": today - timedelta(days=int(spec["last_days"]))})
            if spec.get("before_today"):
                qs = qs.filter(**{f"{lookup}__lt": today})
    return qs


def rows(dataset, qs, columns):
    fields = [dataset.field(c) for c in columns if dataset.field(c)]
    return fields, ([f.value(obj) for f in fields] for obj in qs)
