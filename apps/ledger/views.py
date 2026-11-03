# SPDX-License-Identifier: AGPL-3.0-or-later
"""Rent ledger pages: overview, demand runs, accounts and statements, arrears, receipts, finance exports."""
from collections import namedtuple
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core.models import ModuleSettings
from apps.core.roles import administrators_only, is_administrator
from apps.leases.models import Lease
from apps.reports.export import csv_response, xlsx_response

from . import billing, finance
from .models import Charge, DemandRun, ExportBatch, Receipt

Col = namedtuple("Col", "label type")


def ledger_view(view):
    """Signed-in users only, and only when the council has switched the rent ledger on."""
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not ModuleSettings.load().rent_ledger_enabled:
            return render(request, "ledger/off.html", status=404)
        return view(request, *args, **kwargs)

    return login_required(wrapped)


def _date(text, default):
    try:
        return date.fromisoformat(text) if text else default
    except ValueError:
        return None


@ledger_view
def home(request):
    today = date.today()
    pending = finance.unexported().aggregate(n=Count("pk"), t=Sum("gross"))
    return render(request, "ledger/home.html", {
        "arrears": billing.arrears_summary(today), "collection": billing.collection(today),
        "pending": pending, "runs": DemandRun.objects.annotate(n=Count("charges"), t=Sum("charges__gross"))[:5],
        "settings": ModuleSettings.load(), "today": today,
    })


# ------------------------------------------------------------------ demand runs

def _quarter_end(day):
    for m, d in ((3, 24), (6, 23), (9, 28), (12, 24)):
        if date(day.year, m, d) >= day:
            return date(day.year, m, d)
    return date(day.year + 1, 3, 24)


@administrators_only
@ledger_view
def run_new(request):
    today = date.today()
    data = request.POST if request.method == "POST" else request.GET
    due_from = _date(data.get("due_from"), today)
    due_to = _date(data.get("due_to"), _quarter_end(today + timedelta(days=1)))
    issue_date = _date(data.get("issue_date"), today)
    errors = []
    if None in (due_from, due_to, issue_date):
        errors.append(_("Enter dates as day, month and year."))
    elif due_to < due_from:
        errors.append(_("The end date must be on or after the start date."))
    elif (due_to - due_from).days > 400:
        errors.append(_("A demand run can cover up to 13 months."))
    if request.method == "POST" and "confirm" in request.POST and not errors:
        run = billing.issue_run(due_from, due_to, issue_date, request.POST.get("notes", "")[:500])
        if run is None:
            messages.info(request, _("There was nothing new to charge for those dates."))
            return redirect("ledger:home")
        messages.success(request, _("Demand run complete: %(n)s charges raised.") % {"n": run.charges.count()})
        return redirect(run)
    charges = billing.proposed_charges(due_from, due_to, issue_date) if not errors and "due_from" in data else None
    totals = None
    if charges:
        totals = {k: sum((getattr(c, k) for c in charges), Decimal("0")) for k in ("net", "vat", "gross")}
    return render(request, "ledger/run_new.html", {
        "due_from": due_from or today, "due_to": due_to or today, "issue_date": issue_date or today,
        "errors": errors, "charges": charges, "totals": totals, "settings": ModuleSettings.load(),
    })


CHARGE_COLUMNS = [Col("Reference", "text"), Col("Lease", "text"), Col("Tenant", "text"), Col("Description", "text"),
                  Col("Due", "date"), Col("Net", "money"), Col("VAT", "money"), Col("Total", "money")]


def _charge_rows(charges):
    for c in charges:
        yield [c.reference, c.lease.reference, c.lease.counterparty.name, c.description, c.due_date, c.net, c.vat,
               c.gross]


@ledger_view
def run_detail(request, pk):
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
    acc = billing.account(lease, charges=lease.charges.select_related("credit_for"), receipts=lease.receipts.all())
    fmt = request.GET.get("format")
    title = f"Statement {lease.reference}"
    if fmt == "xlsx":
        return xlsx_response(title, STATEMENT_COLUMNS, _statement_rows(acc))
    if fmt == "csv":
        return csv_response(title, STATEMENT_COLUMNS, _statement_rows(acc))
    return render(request, "ledger/account.html", {
        "lease": lease, "account": acc, "today": date.today(), "can_credit": is_administrator(request.user),
        "statement": request.GET.get("print") == "1",
    })


@administrators_only
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
                  [Col(label, "money") for _l, label in billing.AGE_BANDS]


@ledger_view
def arrears(request):
    summary = billing.arrears_summary()
    rows = ([a.lease.reference, a.lease.counterparty.name, a.lease.counterparty.finance_customer_ref, a.balance,
             a.overdue] + [amount for _label, amount in a.aged] for a in summary["accounts"])
    fmt = request.GET.get("format")
    if fmt == "xlsx":
        return xlsx_response("Rent arrears", ARREARS_COLUMNS, rows, totals=True)
    if fmt == "csv":
        return csv_response("Rent arrears", ARREARS_COLUMNS, rows)
    return render(request, "ledger/arrears.html", {"summary": summary, "bands": billing.AGE_BANDS})


RECEIPT_COLUMNS = [Col("Received", "date"), Col("Payment reference", "text"), Col("Lease", "text"),
                   Col("Tenant", "text"), Col("Reference quoted", "text"), Col("Amount", "money")]


@ledger_view
def receipts(request):
    qs = Receipt.objects.select_related("lease", "lease__counterparty").order_by("-received_on", "-pk")
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
    if request.method == "POST":
        if not is_administrator(request.user):
            raise Http404
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
    batch = get_object_or_404(ExportBatch, pk=pk)
    return finance.download(batch, "csv" if request.GET.get("format") == "csv" else "xlsx", ModuleSettings.load())
