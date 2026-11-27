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
    from apps.cases import requests as asks

    ctx["can_ask"] = asks.tenant_types().exists()
    ctx["requests"] = list(asks.tenant_cases(account).filter(lease=lease)[:20])
    ctx["request_url"] = "portal:request"
    if account.facilities and settings_row.service_charges_enabled:
        from apps.servicecharges.tenant import published_years

        ctx["sc_years"] = published_years(lease)
    if account.facilities and settings_row.compliance_enabled:
        from apps.compliance.workflow import statuses

        ctx["certificates"] = statuses(_tenant_requirements(lease), today)
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
def request_new(request, pk):
    """Ask the council for something that opens a case, such as consent to assign or a licence for alterations."""
    from apps.cases import requests as asks

    account = request.portal_account
    lease = _lease(request, pk)
    types = asks.tenant_types()
    if not types.exists():
        raise Http404
    form = asks.RequestForm(request.POST or None, request.FILES or None, types=types)
    if request.method == "POST" and form.is_valid():
        case = asks.submit(form, received="portal", who=f"{account.name} ({account.party.name})", lease=lease,
                           account=account)
        return render(request, "portal/request_sent.html", {"lease": lease, "case": case})
    return render(request, "portal/request_new.html", {"lease": lease, "form": form})


@tenant_required
def request_detail(request, pk):
    from apps.cases import requests as asks

    case = get_object_or_404(asks.tenant_cases(request.portal_account), pk=pk)
    return render(request, "portal/request_detail.html", {
        "case": case, "progress": asks.progress(case), "documents": asks.shared_documents(case),
        "doc_url": "portal:request-document"})


@tenant_required
def request_document(request, pk, doc):
    from apps.cases import requests as asks

    case = get_object_or_404(asks.tenant_cases(request.portal_account), pk=pk)
    item = get_object_or_404(asks.shared_documents(case), pk=doc)
    return FileResponse(item.file.open("rb"), as_attachment=True,
                        filename=item.original_filename or item.file.name.rsplit("/", 1)[-1])


def _facilities(request, flag):
    account = request.portal_account
    if not (account.facilities and getattr(ModuleSettings.load(), flag)):
        raise Http404


def _member_year(lease, year_pk):
    from apps.servicecharges.tenant import published_years

    found = next(((m, y, b, st) for m, y, b, st in published_years(lease) if y.pk == year_pk), None)
    if found is None:
        raise Http404
    return found


@tenant_required
def sc_budget(request, pk, year_pk):
    from apps.servicecharges.tenant import budget_context

    _facilities(request, "service_charges_enabled")
    lease = _lease(request, pk)
    member, year, budget, _statement = _member_year(lease, year_pk)
    if not budget:
        raise Http404
    return render(request, "portal/sc_budget.html", {"lease": lease, **budget_context(year, member)})


@tenant_required
def sc_statement(request, pk, year_pk):
    from apps.servicecharges.tenant import statement_context

    _facilities(request, "service_charges_enabled")
    lease = _lease(request, pk)
    member, year, _budget, statement = _member_year(lease, year_pk)
    if not statement:
        raise Http404
    return render(request, "portal/sc_statement.html", {"lease": lease, **statement_context(year, member)})


@tenant_required
def sc_query(request, pk, year_pk):
    """Query a line of the service charge: opens a service charge query case, which the tenant can follow."""
    from django import forms

    from apps.cases import workflow
    from apps.cases.models import CaseType, Correspondence
    from apps.servicecharges import apportion

    _facilities(request, "service_charges_enabled")
    account = request.portal_account
    lease = _lease(request, pk)
    _member, year, _budget, _statement = _member_year(lease, year_pk)
    case_type = CaseType.objects.filter(code="sc_dispute", active=True).first()
    if case_type is None:
        raise Http404
    headings = [h for h, _b, _a in apportion.by_heading(year)]

    class QueryForm(forms.Form):
        heading = forms.ChoiceField(choices=[("", _("The whole statement"))] + [(str(h.pk), h.name) for h in headings],
                                    required=False, label=_("Which line"))
        question = forms.CharField(widget=forms.Textarea(attrs={"rows": 5}), max_length=4000,
                                   label=_("Your question"))

    form = QueryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        line = next((h.name for h in headings if str(h.pk) == form.cleaned_data["heading"]), _("The whole statement"))
        title = _("Query: %(line)s, %(year)s") % {"line": line, "year": f"{year.schedule.name} {year.label}"}
        case = workflow.open_case(case_type, title=title[:200], lease=lease, how_received="portal",
                                  portal_account=account)
        Correspondence.objects.create(case=case, direction=Correspondence.Direction.IN,
                                      method=Correspondence.Method.ONLINE,
                                      correspondent=f"{account.name} ({account.party.name})"[:250],
                                      subject=title[:250], summary=form.cleaned_data["question"])
        return render(request, "portal/request_sent.html", {"lease": lease, "case": case})
    return render(request, "portal/sc_query.html", {"lease": lease, "year": year, "form": form})


def _tenant_requirements(lease):
    from apps.compliance.models import Requirement

    return (Requirement.objects.filter(property__in=lease.properties.all(), responsible="tenant", active=True)
            .select_related("kind", "property").order_by("property__reference", "kind__order"))


@tenant_required
def certificate(request, pk, req_pk):
    """Upload a certificate the tenant must provide, such as a gas safety record. Estates check it afterwards."""
    from django import forms

    from apps.cases.models import validate_case_file
    from apps.compliance import workflow
    from apps.compliance.models import Certificate

    _facilities(request, "compliance_enabled")
    account = request.portal_account
    lease = _lease(request, pk)
    req = get_object_or_404(_tenant_requirements(lease), pk=req_pk)

    class CertificateForm(forms.Form):
        issued_on = forms.DateField(label=_("Date of the inspection or certificate"),
                                    widget=forms.DateInput(attrs={"type": "date"}))
        result = forms.ChoiceField(choices=Certificate.Result.choices, initial=Certificate.Result.SATISFACTORY,
                                   label=_("Result"), widget=forms.RadioSelect)
        carried_out_by = forms.CharField(max_length=200, label=_("Carried out by"),
                                         help_text=_("The engineer or company, with their registration number if "
                                                     "they have one"))
        reference = forms.CharField(max_length=60, required=False, label=_("Certificate number"))
        file = forms.FileField(label=_("The certificate"), validators=[validate_case_file],
                               help_text=_("PDF or a photo, up to 25 MB"))

        def clean_issued_on(self):
            day = self.cleaned_data["issued_on"]
            if day > date.today():
                raise forms.ValidationError(_("The date cannot be in the future."))
            return day

    form = CertificateForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        cert = workflow.record(req, d["issued_on"], None, d["file"], result=d["result"],
                               carried_out_by=d["carried_out_by"], reference=d["reference"],
                               portal_account=account,
                               notes=_("Uploaded in the tenant portal by %(name)s.") % {"name": account.name})
        return render(request, "portal/certificate_sent.html", {"lease": lease, "cert": cert})
    return render(request, "portal/certificate.html", {"lease": lease, "req": req, "form": form})


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
