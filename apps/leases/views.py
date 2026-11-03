# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import date, timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q, Sum
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView, ListView

from apps.core.tables import sortable

from .models import Lease, Party

COLUMNS = {
    "reference": (_("Reference"), ["reference"], False),
    "party": (_("Tenant or landlord"), ["counterparty__name", "reference"], False),
    "type": (_("Type"), ["agreement_type", "reference"], False),
    "status": (_("Status"), ["status", "reference"], False),
    "start": (_("Start"), ["term_start", "reference"], False),
    "expiry": (_("Expiry"), ["term_end", "reference"], False),
    "review": (_("Next review"), ["next_review_date", "reference"], False),
    "rent": (_("Rent £ a year"), ["annual_rent", "reference"], True),
}

EXPIRY_WINDOWS = [("6", _("Within 6 months")), ("12", _("Within 12 months")), ("24", _("Within 2 years")),
                  ("past", _("Already passed (holding over or ended)"))]


class LeaseListView(LoginRequiredMixin, ListView):
    model = Lease
    paginate_by = 50
    template_name = "leases/lease_list.html"
    FILTERS = ("direction", "agreement_type", "status", "security_of_tenure")

    def get_queryset(self):
        qs = Lease.objects.select_related("counterparty").prefetch_related("properties")
        get = self.request.GET
        q = get.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(reference__icontains=q) | Q(counterparty__name__icontains=q)
                | Q(properties__name__icontains=q) | Q(properties__reference__icontains=q)
                | Q(premises_description__icontains=q)
            ).distinct()
        for f in self.FILTERS:
            if get.get(f):
                qs = qs.filter(**{f: get[f]})
        window = get.get("expiring")
        today = date.today()
        if window == "past":
            qs = qs.filter(term_end__lt=today)
        elif window in {"6", "12", "24"}:
            qs = qs.filter(term_end__gte=today, term_end__lte=today + timedelta(days=int(window) * 30.44))
        if get.get("property"):
            qs = qs.filter(properties__pk=get["property"])
        ordering, self.headings = sortable(self.request, COLUMNS, "reference")
        return qs.order_by(*ordering)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        get = self.request.GET
        ctx["q"] = get.get("q", "")
        ctx["filters"] = [
            (f, Lease._meta.get_field(f).verbose_name, Lease._meta.get_field(f).choices, get.get(f, ""))
            for f in self.FILTERS
        ] + [("expiring", _("Expiry"), EXPIRY_WINDOWS, get.get("expiring", ""))]
        ctx["headings"] = self.headings
        ctx["rent_total"] = self.object_list.order_by().aggregate(t=Sum("annual_rent"))["t"]
        params = get.copy()
        params.pop("page", None)
        ctx["querystring"] = params.urlencode()
        ctx["today"] = date.today()
        return ctx


class LeaseDetailView(LoginRequiredMixin, DetailView):
    model = Lease
    template_name = "leases/lease_detail.html"

    def get_queryset(self):
        return Lease.objects.select_related("counterparty", "guarantor").prefetch_related("properties", "breaks")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = date.today()
        rows = []
        for when, label, kind in self.object.key_dates():
            days = (when - today).days
            if days < 0:
                rag = ("grey", _("Passed"))
            elif days <= 183:
                rag = ("red", _("Within 6 months"))
            elif days <= 365:
                rag = ("orange", _("Within 12 months"))
            else:
                rag = ("green", _("More than 12 months"))
            rows.append({"date": when, "label": label, "kind": kind, "days": days, "rag": rag})
        ctx["key_dates"] = rows
        return ctx


class PartyDetailView(LoginRequiredMixin, DetailView):
    model = Party
    template_name = "leases/party_detail.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["leases"] = self.object.leases.prefetch_related("properties")
        ctx["guarantees"] = self.object.guarantees.select_related("counterparty")
        return ctx
