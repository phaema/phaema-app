# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tenant portal pages at /tenant/: sign-in by emailed code, then the tenant's agreements, account, demands, key
dates, shared documents and requests to change contact details for demands."""
from datetime import date

from django.conf import settings
from django.core.cache import cache
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.core import notify
from apps.core.models import ModuleSettings
from apps.core.throttle import client_ip
from apps.leases.models import LeaseDocument

from . import access
from .access import portal_page, tenant_required
from .emails import send_code
from .forms import CodeForm, ContactChangeForm, EmailForm
from .models import ContactChange, PortalAccount, SignInCode

PENDING_KEY = "phaema_portal_pending"
SHOWN_KEY = "phaema_portal_shown_code"
CODES_PER_HOUR = 5  # to one address
REQUESTS_PER_HOUR = 20  # from one connection, sign-in requests and code tries together


def _limited(key, limit):
    count = cache.get(key, 0)
    if count >= limit:
        return True
    cache.set(key, count + 1, 3600)
    return False


@never_cache
@portal_page
def sign_in(request):
    if access.current(request) is not None:
        return redirect("portal:home")
    form = EmailForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if _limited(f"portal-ip:{client_ip(request)}", REQUESTS_PER_HOUR):
            form.add_error(None, _("Too many tries from this connection. Please try again in an hour."))
        else:
            email = form.cleaned_data["email"].strip().lower()
            account = PortalAccount.objects.filter(email=email).first()
            request.session.pop(SHOWN_KEY, None)
            # The same answer whether or not there is an account, so the page does not reveal who has one.
            request.session[PENDING_KEY] = account.pk if access.may_sign_in(account) else 0
            if request.session[PENDING_KEY] and not _limited(f"portal-codes:{email}", CODES_PER_HOUR):
                _email, code = send_code(account)
                if settings.PHAEMA_PORTAL_SHOW_CODES and not notify.configured():
                    request.session[SHOWN_KEY] = code
            return redirect("portal:code")
    return render(request, "portal/sign_in.html", {"form": form, "welcome": ModuleSettings.load()})


@never_cache
@portal_page
def code(request):
    if PENDING_KEY not in request.session:
        return redirect("portal:sign-in")
    form = CodeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if _limited(f"portal-ip:{client_ip(request)}", REQUESTS_PER_HOUR):
            form.add_error(None, _("Too many tries from this connection. Please try again in an hour."))
        else:
            row = (SignInCode.objects.filter(account_id=request.session[PENDING_KEY], used_at__isnull=True)
                   .select_related("account").order_by("-created_at").first())
            if row is not None and row.matches(form.cleaned_data["code"]) and access.may_sign_in(row.account):
                request.session.pop(PENDING_KEY, None)
                request.session.pop(SHOWN_KEY, None)
                access.sign_in(request, row.account)
                PortalAccount.objects.filter(pk=row.account_id).update(last_sign_in=timezone.now())
                return redirect("portal:home")
            form.add_error("code", _("That code is not right, has been used or has run out. Check the latest "
                                     "email, or ask for a new code."))
    return render(request, "portal/code.html", {"form": form, "shown_code": request.session.get(SHOWN_KEY),
                                                "minutes": SignInCode.MINUTES})


@require_POST
@portal_page
def sign_out(request):
    access.sign_out(request)
    return render(request, "portal/signed_out.html")


@tenant_required
def home(request):
    account = request.portal_account
    leases = list(access.agreements_for(account).prefetch_related("properties"))
    rows = []
    if account.finance and ModuleSettings.load().rent_ledger_enabled:
        from apps.ledger import billing

        for lease in leases:
            acc = billing.account(lease)
            rows.append((lease, acc.balance, acc.overdue))
    else:
        rows = [(lease, None, None) for lease in leases]
    return render(request, "portal/home.html", {"rows": rows, "settings": ModuleSettings.load()})


def _lease(request, pk):
    return get_object_or_404(access.agreements_for(request.portal_account), pk=pk)


def _statement_line(line):
    if line.kind == "receipt":
        return {"when": line.when, "receipt": True, "credited": line.credit, "balance": line.balance}
    c = line.obj
    charged, credited = (line.debit, None) if line.debit >= 0 else (None, -line.debit)
    return {"when": line.when, "details": f"{c.reference} {c.description}", "charged": charged, "credited": credited,
            "balance": line.balance}


def _money_view(lease, settings, today):
    """What a tenant with finance rights sees about their account."""
    from apps.ledger import billing, creditcontrol
    from apps.ledger.emails import payment_url

    acc = billing.account(lease, today)
    demands = []
    for line in acc.lines:
        if line.kind == "charge" and line.outstanding > 0:
            c = line.obj
            demands.append({"charge": c, "outstanding": line.outstanding, "overdue": c.due_date < today,
                            "pay": payment_url(settings, c.reference, line.outstanding, lease.reference)})
    out = {"account": acc, "demands": demands, "aged": [(label, amount) for label, amount in acc.aged if amount],
           "lines": [_statement_line(line) for line in reversed(acc.lines)]}
    if creditcontrol.active_plan(lease) is not None:
        out["plan"] = True
    elif acc.overdue > 0:
        due = creditcontrol.due_actions(today, type(lease).objects.filter(pk=lease.pk))
        out["next_step"] = due[0].stage if due else None
    if lease.interest_basis and acc.overdue > 0:
        from apps.ledger import interest

        result = interest.calculate(lease, today)
        if result.ok and result.total > 0:
            out["interest"] = result
    if acc.balance > 0:
        out["pay_all"] = payment_url(settings, lease.reference, acc.balance, lease.reference)
    return out


@tenant_required
def agreement(request, pk):
    account = request.portal_account
    lease = _lease(request, pk)
    settings_row = ModuleSettings.load()
    today = date.today()
    ctx = {"lease": lease, "today": today, "settings": settings_row,
           "key_dates": [d for d in lease.key_dates(today) if d[0] >= today],
           "documents": lease.documents.filter(shared_with_tenant=True),
           "waiting_change": lease.contact_changes.filter(status=ContactChange.Status.WAITING).first()}
    if account.finance and settings_row.rent_ledger_enabled:
        ctx.update(_money_view(lease, settings_row, today))
    if account.facilities and settings_row.maintenance_enabled:
        ctx["can_report"] = True
        ctx["repairs"] = list(lease.repair_reports.select_related("job").order_by("-created_at")[:20])
    return render(request, "portal/agreement.html", ctx)


def _repairs_on():
    from apps.maintenance.reports import enabled

    return enabled()


@tenant_required
def repair(request, pk):
    """Report a repair: the shared form, into the estates team's triage queue."""
    from apps.maintenance import reports

    account = request.portal_account
    if not (account.facilities and _repairs_on()):
        raise Http404
    lease = _lease(request, pk)
    form = reports.RepairForm(request.POST or None, request.FILES or None, properties=lease.properties.all())
    if request.method == "POST" and form.is_valid():
        report = reports.submit(form, source="tenant", reporter_name=account.name, lease=lease, account=account)
        return render(request, "portal/repair_sent.html", {"lease": lease, "report": report})
    return render(request, "portal/repair.html", {"lease": lease, "form": form})


@tenant_required
def contact(request, pk):
    account = request.portal_account
    if not account.finance:
        raise Http404
    lease = _lease(request, pk)
    billing = lease.billing
    initial = {"contact_name": billing["name"], "email": billing["email"], "phone": billing["phone"],
               "address": billing["address"]}
    form = ContactChangeForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        change = form.save(commit=False)
        change.lease, change.account = lease, account
        change.save()
        return render(request, "portal/contact_sent.html", {"lease": lease})
    return render(request, "portal/contact.html", {"lease": lease, "form": form})


@tenant_required
def document(request, pk):
    doc = get_object_or_404(LeaseDocument, pk=pk, shared_with_tenant=True,
                            lease__in=access.agreements_for(request.portal_account))
    name = doc.original_filename or f"{doc.get_document_type_display()}.pdf"
    return FileResponse(doc.file.open("rb"), content_type="application/pdf", filename=name)
