# SPDX-License-Identifier: AGPL-3.0-or-later
"""Rent ledger pages: overview, demand runs, accounts and statements, arrears, receipts, finance exports."""
from collections import namedtuple
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core.models import ModuleSettings
from apps.core.access import can_do_finance, finance_only, lease_in_patch, module_view, patch_leases, require_full
from apps.leases.models import Lease
from apps.reports.export import csv_response, xlsx_response

from . import billing, finance
from .models import Charge, DemandRun, ExportBatch, Receipt

Col = namedtuple("Col", "label type")


ledger_view = module_view("ledger", "ledger/off.html")  # switched on for the council and opened by an access area


def _date(text, default):
    try:
        return date.fromisoformat(text) if text else default
    except ValueError:
        return None


def _patch(request):
    """The leases this person may see in the ledger, or None for all of them."""
    return patch_leases(request.user) if request.access_scope == "patch" else None


@ledger_view
def home(request):
    today = date.today()
    leases = _patch(request)
    full = leases is None
    pending = finance.unexported().aggregate(n=Count("pk"), t=Sum("gross")) if full else None
    return render(request, "ledger/home.html", {
        "arrears": billing.arrears_summary(today, leases), "collection": billing.collection(today, leases=leases),
        "pending": pending, "full": full,
        "runs": DemandRun.objects.annotate(n=Count("charges"), t=Sum("charges__gross"))[:5] if full else [],
        "settings": ModuleSettings.load(), "today": today,
    })


# ------------------------------------------------------------------ demand runs

def _quarter_end(day):
    for m, d in ((3, 24), (6, 23), (9, 28), (12, 24)):
        if date(day.year, m, d) >= day:
            return date(day.year, m, d)
    return date(day.year + 1, 3, 24)


@finance_only
@ledger_view
def run_new(request):
    today = date.today()
    data = request.POST if request.method == "POST" else request.GET
    due_from = _date(data.get("due_from"), today)
    due_to = _date(data.get("due_to"), _quarter_end(today + timedelta(days=1)))
    issue_date = _date(data.get("issue_date"), today)
    errors = []
    settings = ModuleSettings.load()
    include = data.get("include", "all") if settings.service_charges_enabled else "rent"
    rent, service = include in ("all", "rent"), include in ("all", "service")
    if None in (due_from, due_to, issue_date):
        errors.append(_("Enter dates as day, month and year."))
    elif due_to < due_from:
        errors.append(_("The end date must be on or after the start date."))
    elif (due_to - due_from).days > 400:
        errors.append(_("A demand run can cover up to 13 months."))
    if request.method == "POST" and "confirm" in request.POST and not errors:
        run = billing.issue_run(due_from, due_to, issue_date, request.POST.get("notes", "")[:500], rent=rent,
                                service=service)
        if run is None:
            messages.info(request, _("There was nothing new to charge for those dates."))
            return redirect("ledger:home")
        messages.success(request, _("Demand run complete: %(n)s charges raised.") % {"n": run.charges.count()})
        return redirect(run)
    charges = billing.proposed_charges(due_from, due_to, issue_date, rent=rent, service=service) \
        if not errors and "due_from" in data else None
    totals = None
    if charges:
        totals = {k: sum((getattr(c, k) for c in charges), Decimal("0")) for k in ("net", "vat", "gross")}
    return render(request, "ledger/run_new.html", {
        "due_from": due_from or today, "due_to": due_to or today, "issue_date": issue_date or today,
        "errors": errors, "charges": charges, "totals": totals, "settings": settings, "include": include,
        "on_hold": list(billing.held_leases()),
    })


CHARGE_COLUMNS = [Col("Reference", "text"), Col("Lease", "text"), Col("Tenant", "text"), Col("Description", "text"),
                  Col("Due", "date"), Col("Net", "money"), Col("VAT", "money"), Col("Total", "money")]


def _charge_rows(charges):
    for c in charges:
        yield [c.reference, c.lease.reference, c.lease.counterparty.name, c.description, c.due_date, c.net, c.vat,
               c.gross]


@ledger_view
def run_detail(request, pk):
    require_full(request)
    run = get_object_or_404(DemandRun, pk=pk)
    charges = run.charges.select_related("lease", "lease__counterparty").order_by("due_date", "lease__reference")
    fmt = request.GET.get("format")
    if fmt == "xlsx":
        return xlsx_response(str(run), CHARGE_COLUMNS, _charge_rows(charges), totals=True)
    if fmt == "csv":
        return csv_response(str(run), CHARGE_COLUMNS, _charge_rows(charges))
    return render(request, "ledger/run_detail.html", {
        "run": run, "charges": charges, "totals": charges.aggregate(net=Sum("net"), vat=Sum("vat"), gross=Sum("gross")),
    })


# ------------------------------------------------------------------ accounts

STATEMENT_COLUMNS = [Col("Date", "date"), Col("Reference", "text"), Col("Details", "text"), Col("Charged", "money"),
                     Col("Paid or credited", "money"), Col("Balance", "money"), Col("Still owed", "money")]


def _statement_rows(acc):
    for line in acc.lines:
        o = line.obj
        if line.kind == "receipt":
            yield [line.when, o.payment_reference, f"Payment received{': ' + o.quoted_reference if o.quoted_reference else ''}",
                   None, line.credit, line.balance, None]
        else:
            charged, credited = (line.debit, None) if line.debit >= 0 else (None, -line.debit)
            yield [line.when, o.reference, o.description, charged, credited, line.balance,
                   line.outstanding if line.outstanding else None]


@ledger_view
def account(request, lease_pk):
    lease = get_object_or_404(Lease.objects.select_related("counterparty"), pk=lease_pk)
    if request.access_scope == "patch" and not lease_in_patch(request.user, lease):
        raise PermissionDenied
    acc = billing.account(lease, charges=lease.charges.select_related("credit_for"), receipts=lease.receipts.all())
    fmt = request.GET.get("format")
    title = f"Statement {lease.reference}"
    if fmt == "xlsx":
        return xlsx_response(title, STATEMENT_COLUMNS, _statement_rows(acc))
    if fmt == "csv":
        return csv_response(title, STATEMENT_COLUMNS, _statement_rows(acc))
    return render(request, "ledger/account.html", {
        "lease": lease, "account": acc, "today": date.today(), "can_credit": can_do_finance(request.user),
        "statement": request.GET.get("print") == "1",
    })


@finance_only
@ledger_view
@require_POST
def credit(request, charge_pk):
    charge = get_object_or_404(Charge, pk=charge_pk, gross__gt=0)
    reason = request.POST.get("reason", "").strip()
    raw = request.POST.get("amount", "").replace(",", "").replace("£", "").strip()
    try:
        amount = Decimal(raw) if raw else None
        if not reason:
            raise ValueError(_("Give a reason for the credit."))
        note = billing.credit(charge, reason, amount)
    except (ValueError, InvalidOperation) as exc:
        messages.error(request, str(exc) if not isinstance(exc, InvalidOperation) else _("Enter the amount in pounds."))
    else:
        messages.success(request, _("Credit note %(ref)s for £%(amount)s issued.")
                         % {"ref": note.reference, "amount": f"{-note.gross:,.2f}"})
    return redirect("ledger:account", charge.lease_id)


ARREARS_COLUMNS = [Col("Lease", "text"), Col("Tenant", "text"), Col("Customer reference", "text"),
                   Col("Balance", "money"), Col("Overdue", "money")] + \
                  [Col(label, "money") for _l, label in billing.AGE_BANDS] + \
                  [Col("Passed to", "text"), Col("Date passed over", "date"), Col("Demands on hold", "text")]


@ledger_view
def arrears(request):
    summary = billing.arrears_summary(leases=_patch(request))
    referred = request.GET.get("referred", "")
    if referred:  # "any", "none", or one of the referral kinds
        keep = {"any": lambda r: bool(r), "none": lambda r: not r}.get(referred, lambda r: r == referred)
        from decimal import Decimal as D

        summary["accounts"] = [a for a in summary["accounts"] if keep(a.lease.arrears_referral)]
        summary["total"] = sum((a.overdue for a in summary["accounts"]), D("0"))
        summary["count"] = len(summary["accounts"])
        summary["bands"] = [(label, sum((dict(a.aged)[label] for a in summary["accounts"]), D("0")))
                            for _l, label in billing.AGE_BANDS]
    rows = ([a.lease.reference, a.lease.counterparty.name, a.lease.counterparty.finance_customer_ref, a.balance,
             a.overdue] + [amount for _label, amount in a.aged]
            + [a.lease.get_arrears_referral_display(), a.lease.arrears_referred_on,
               "Yes" if a.lease.demands_on_hold else ""] for a in summary["accounts"])
    fmt = request.GET.get("format")
    if fmt == "xlsx":
        return xlsx_response("Rent arrears", ARREARS_COLUMNS, rows, totals=True)
    if fmt == "csv":
        return csv_response("Rent arrears", ARREARS_COLUMNS, rows)
    return render(request, "ledger/arrears.html", {
        "summary": summary, "bands": billing.AGE_BANDS, "referred": referred,
        "referral_choices": [("any", _("Passed to debt collectors or legal")), ("none", _("Not passed over"))]
        + list(Lease.ArrearsReferral.choices)})


RECEIPT_COLUMNS = [Col("Received", "date"), Col("Payment reference", "text"), Col("Lease", "text"),
                   Col("Tenant", "text"), Col("Reference quoted", "text"), Col("Amount", "money")]


@ledger_view
def receipts(request):
    qs = Receipt.objects.select_related("lease", "lease__counterparty").order_by("-received_on", "-pk")
    if _patch(request) is not None:
        qs = qs.filter(lease__in=_patch(request))
    since, until = _date(request.GET.get("from"), None), _date(request.GET.get("to"), None)
    if since:
        qs = qs.filter(received_on__gte=since)
    if until:
        qs = qs.filter(received_on__lte=until)
    rows = ([r.received_on, r.payment_reference, r.lease.reference, r.lease.counterparty.name, r.quoted_reference,
             r.amount] for r in qs)
    fmt = request.GET.get("format")
    if fmt == "xlsx":
        return xlsx_response("Rent receipts", RECEIPT_COLUMNS, rows, totals=True)
    if fmt == "csv":
        return csv_response("Rent receipts", RECEIPT_COLUMNS, rows)
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "ledger/receipts.html", {
        "page_obj": Paginator(qs, 100).get_page(request.GET.get("page")), "total": qs.aggregate(t=Sum("amount"))["t"],
        "since": since, "until": until, "querystring": params.urlencode(),
    })


# ------------------------------------------------------------------ finance exports

@ledger_view
def exports(request):
    require_full(request)
    if request.method == "POST":
        if not can_do_finance(request.user):
            raise PermissionDenied
        batch = finance.create_batch()
        if batch is None:
            messages.info(request, _("There are no new charges to export."))
        else:
            messages.success(request, _("Finance export %(n)s created with %(c)s charges. Download it below.")
                             % {"n": batch.pk, "c": batch.charges.count()})
        return redirect("ledger:exports")
    return render(request, "ledger/exports.html", {
        "pending": finance.unexported().aggregate(n=Count("pk"), t=Sum("gross")),
        "batches": ExportBatch.objects.select_related("created_by").annotate(n=Count("charges"),
                                                                             t=Sum("charges__gross")),
    })


@ledger_view
def export_download(request, pk):
    require_full(request)
    batch = get_object_or_404(ExportBatch, pk=pk)
    return finance.download(batch, "csv" if request.GET.get("format") == "csv" else "xlsx", ModuleSettings.load())
