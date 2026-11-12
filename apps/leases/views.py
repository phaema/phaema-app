# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, DecimalField, Exists, IntegerField, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView

from apps.core.tables import sortable
from apps.core import places
from apps.reports.mixins import ExportMixin

from . import events
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

FLAGS = [("essence", _("Time is of the essence (rent review)")), ("on_hold", _("Rent demands on hold")),
         ("referred", _("Arrears passed to debt collectors or legal")), ("billing", _("Has its own billing contact"))]
FLAG_FILTERS = {"essence": {"time_of_essence": True}, "on_hold": {"demands_on_hold": True}}

EXPIRY_WINDOWS = [("6", _("Within 6 months")), ("12", _("Within 12 months")), ("24", _("Within 2 years")),
                  ("past", _("Already passed (holding over or ended)"))]


class LeaseListView(LoginRequiredMixin, ExportMixin, ListView):
    model = Lease
    export_dataset, export_title = "leases", "Leases and licences"
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
        if get.get("live"):  # current or holding over: used by the dashboard's links
            qs = qs.filter(status__in=events.LIVE)
        flag = get.get("flag", "")
        if flag in FLAG_FILTERS:
            qs = qs.filter(**FLAG_FILTERS[flag])
        elif flag == "referred":
            qs = qs.exclude(arrears_referral="")
        elif flag == "billing":
            qs = qs.exclude(billing_contact_name="", billing_email="", billing_phone="", billing_address="")
        qs = places.apply(qs, get, self.request.user, "properties")
        if get.get("event") in events.FILTERS:
            qs = events.filter_leases(qs, get["event"])
        ordering, self.headings = sortable(self.request, COLUMNS, "reference")
        return qs.order_by(*ordering)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        get = self.request.GET
        ctx["q"] = get.get("q", "")
        ctx["filters"] = [
            (f, Lease._meta.get_field(f).verbose_name, Lease._meta.get_field(f).choices, get.get(f, ""))
            for f in self.FILTERS
        ] + [("expiring", _("Expiry"), EXPIRY_WINDOWS, get.get("expiring", "")),
             ("event", _("Lease events"), list(events.FILTERS.items()), get.get("event", "")),
             ("flag", _("Flags"), FLAGS, get.get("flag", ""))] + [row[:4] for row in places.filters(get)]
        ctx["live_only"] = bool(get.get("live"))
        ctx["event_label"] = events.FILTERS.get(get.get("event", ""))
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
        return Lease.objects.select_related("counterparty", "guarantor").prefetch_related(
            "properties", "breaks", "documents")

    def get_context_data(self, **kwargs):
        from . import workflow

        ctx = super().get_context_data(**kwargs)
        lease = self.object
        from .models import LeaseDocument

        ctx["document_types"] = LeaseDocument.DocumentType.choices
        events = list(lease.events.select_related("assigned_to"))
        ctx["open_events"] = [e for e in events if e.is_open]
        ctx["closed_events"] = sorted((e for e in events if not e.is_open),
                                      key=lambda e: e.completed_on or e.due_date, reverse=True)[:10]
        today = date.today()
        schedule = list(lease.rent_schedule.all())
        current = max((e for e in schedule if e.effective_from <= today), key=lambda e: e.effective_from, default=None)
        ctx["schedule"] = [(e, e == current, e.effective_from > today) for e in schedule]
        ctx["payments"] = workflow.payments_preview(lease, today, 4)
        ctx["rent_account"] = _rent_account(lease, self.request.user)
        from apps.documents.views import _can_create, for_lease

        ctx["doc_templates"] = for_lease() if _can_create(self.request.user) else []
        ctx["today"] = today
        ctx["documents"] = list(lease.documents.all())
        if lease.insurance == Lease.Insurance.TENANT and lease.is_let_out:
            ctx["tenant_insures"] = True
            ctx["insurance_certificate"] = lease.insurance_certificate()
            ctx["insurance_case"] = next((c for c in lease.cases.all()
                                          if c.case_type.code == "insurance_certificate" and c.is_open), None)
        return ctx


DOCUMENT_COLUMNS = {
    "review": (_("Review"), ["review_date", "pk"], False),
    "document": (_("Document"), ["document_type", "description"], False),
    "lease": (_("Agreement"), ["lease__reference", "review_date"], False),
    "dated": (_("Document date"), ["document_date", "pk"], False),
}
DOCUMENT_WINDOWS = [("overdue", _("Review overdue")), ("90", _("Review within 3 months")),
                    ("183", _("Review within 6 months")), ("365", _("Review within 12 months")),
                    ("dated", _("Any review date")), ("none", _("No review date"))]


class DocumentListView(LoginRequiredMixin, ExportMixin, ListView):
    """Lease documents, by default those with a date for review, soonest first."""
    export_dataset, export_title = "lease_documents", "Lease documents"
    paginate_by = 50
    template_name = "leases/document_list.html"

    def get_queryset(self):
        from .models import LeaseDocument

        get = self.request.GET
        qs = LeaseDocument.objects.select_related("lease", "lease__counterparty")
        if get.get("status", "live") == "live":
            qs = qs.filter(lease__status__in=events.LIVE)
        window, today = get.get("window", "dated"), date.today()
        if window == "overdue":
            qs = qs.filter(review_date__lt=today)
        elif window.isdigit():
            qs = qs.filter(review_date__gte=today, review_date__lte=today + timedelta(days=int(window)))
        elif window == "none":
            qs = qs.filter(review_date__isnull=True)
        elif window == "dated":
            qs = qs.filter(review_date__isnull=False)
        if get.get("type"):
            qs = qs.filter(document_type=get["type"])
        q = get.get("q", "").strip()
        if q:
            qs = qs.filter(Q(lease__reference__icontains=q) | Q(lease__counterparty__name__icontains=q)
                           | Q(description__icontains=q))
        qs = places.apply(qs, get, self.request.user, "lease__properties")
        ordering, self.headings = sortable(self.request, DOCUMENT_COLUMNS, "review")
        return qs.order_by(*ordering)

    def get_context_data(self, **kwargs):
        from .models import LeaseDocument

        ctx = super().get_context_data(**kwargs)
        get = self.request.GET
        ctx.update({
            "q": get.get("q", ""),
            "filters": [
                ("window", _("Date for review"), DOCUMENT_WINDOWS + [("all", _("All documents"))],
                 get.get("window", "dated"), False),
                ("type", _("Type"), LeaseDocument.DocumentType.choices, get.get("type", ""), True),
                ("status", _("Agreements"), [("live", _("Current and holding over")), ("all", _("All, including ended"))],
                 get.get("status", "live"), False),
                *places.filters(get),
            ],
            "headings": self.headings, "today": date.today(),
        })
        params = get.copy()
        params.pop("page", None)
        ctx["querystring"] = params.urlencode()
        return ctx


class PartyDetailView(LoginRequiredMixin, DetailView):
    model = Party
    template_name = "leases/party_detail.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        rows = self.object.arrangements()
        ctx["arrangements"] = rows
        ctx["properties"] = self.object.properties_involved()
        current = [r for r in rows if r["lease"].status in ("current", "holding_over") and r["lease"].counterparty_id == self.object.pk]
        ctx["current_count"] = len(current)
        ctx["current_rent"] = sum(r["lease"].annual_rent for r in current)
        if _ledger_on():
            from apps.core.access import ledger_leases
            from apps.ledger import billing

            tenant_leases = ledger_leases(self.request.user, Lease.objects.filter(counterparty=self.object))
            ctx["rent_accounts"] = [a for a in billing.accounts(leases=tenant_leases) if a.lines]
            ctx["rent_balance"] = sum(a.balance for a in ctx["rent_accounts"])
            ctx["rent_overdue"] = sum(a.overdue for a in ctx["rent_accounts"])
        return ctx


def _ledger_on():
    from apps.core.models import ModuleSettings

    return ModuleSettings.load().rent_ledger_enabled


def _rent_account(lease, user):
    """The lease's rent account summary, if the council uses the rent ledger and this person may see it (their access
    areas: the whole ledger, or rent for their own patch)."""
    from apps.core.access import can_see_rent

    if not _ledger_on() or lease.direction != Lease.Direction.OUT or not can_see_rent(user, lease):
        return None
    from apps.ledger import billing

    return billing.account(lease)


PARTY_COLUMNS = {
    "name": (_("Name"), ["name"], False),
    "type": (_("Type"), ["party_type", "name"], False),
    "agreements": (_("Current agreements"), ["n_current", "name"], True),
    "rent": (_("Rent £ a year"), ["current_rent", "name"], True),
}


class PartyListView(LoginRequiredMixin, ExportMixin, ListView):
    model = Party
    export_dataset, export_title = "parties", "Tenants and other parties"
    paginate_by = 50
    template_name = "leases/party_list.html"

    def get_queryset(self):
        # Separate subqueries, so a party who is both tenant and guarantor is not counted twice.
        live = Lease.objects.filter(counterparty=OuterRef("pk"), status__in=["current", "holding_over"]).order_by()
        count = live.values("counterparty").annotate(n=Count("pk")).values("n")
        rent = live.values("counterparty").annotate(t=Sum("annual_rent")).values("t")
        qs = Party.objects.annotate(
            n_current=Coalesce(Subquery(count, output_field=IntegerField()), Value(0)),
            current_rent=Coalesce(Subquery(rent, output_field=DecimalField()), Value(Decimal("0"))),
            n_guarantees=Exists(Lease.objects.filter(guarantor=OuterRef("pk"))),
        )
        get = self.request.GET
        q = get.get("q", "").strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(contact_name__icontains=q) | Q(email__icontains=q)
                           | Q(company_number__iexact=q) | Q(finance_customer_ref__iexact=q))
        if get.get("party_type"):
            qs = qs.filter(party_type=get["party_type"])
        ordering, self.headings = sortable(self.request, PARTY_COLUMNS, "name")
        return qs.order_by(*ordering)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        get = self.request.GET
        ctx["q"] = get.get("q", "")
        ctx["types"] = Party.PartyType.choices
        ctx["type_selected"] = get.get("party_type", "")
        ctx["headings"] = self.headings
        params = get.copy()
        params.pop("page", None)
        ctx["querystring"] = params.urlencode()
        return ctx


@login_required
@require_POST
def lease_files(request, pk):
    """File several PDFs on an agreement at once (dragged in or chosen), each named after its file."""
    from django.contrib import messages
    from django.core.exceptions import PermissionDenied
    from django.shortcuts import get_object_or_404, redirect
    from django.utils.translation import gettext as _
    from django.utils.translation import ngettext

    from apps.core.files import file_each, title_from_filename
    from apps.core.roles import can_edit

    from .models import LeaseDocument

    lease = get_object_or_404(Lease, pk=pk)
    if not can_edit(request.user, lease):
        raise PermissionDenied
    kind = request.POST.get("document_type", "")
    if kind not in LeaseDocument.DocumentType.values:
        kind = LeaseDocument.DocumentType.OTHER
    uploads = request.FILES.getlist("files")

    def file_one(upload):
        doc = LeaseDocument(lease=lease, document_type=kind, description=title_from_filename(upload.name), file=upload)
        doc.full_clean()
        doc.save()

    filed, problems = file_each(uploads, file_one)
    if filed:
        messages.success(request, ngettext("%(n)s document filed on this agreement.",
                                           "%(n)s documents filed on this agreement.", filed) % {"n": filed})
    if problems:
        messages.error(request, _("Not filed: %(p)s") % {"p": "; ".join(problems)})
    if not uploads:
        messages.error(request, _("Choose or drop at least one file."))
    return redirect(lease.get_absolute_url() + "#documents")
