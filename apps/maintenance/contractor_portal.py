# SPDX-License-Identifier: AGPL-3.0-or-later
"""Contractor portal at /contractor/: people at contractors the council invites sign in with a code emailed each time,
see the works orders sent to their firm, accept or decline them, add progress notes and photos, and report the work
done with the cost, invoice reference and certificates.

Every page gets its jobs from `jobs_for`, so a contractor can never reach another firm's jobs, or a job before its
order is issued. Changes are logged as made through the contractor portal."""
import time
from datetime import date
from functools import wraps

from django import forms
from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.core import notify
from apps.core.files import validate_image
from apps.core.middleware import set_api_user
from apps.core.models import ModuleSettings, OutgoingEmail
from apps.core.throttle import client_ip
from apps.portal.access import portal_headers

from . import workflow
from .models import ContractorAccount, ContractorSignInCode, Job, JobDocument, JobUpdate

SESSION_KEY = "phaema_contractor_account"
SEEN_KEY = "phaema_contractor_seen"
PENDING_KEY = "phaema_contractor_pending"
SHOWN_KEY = "phaema_contractor_shown_code"
VIA = "Contractor portal"
CODES_PER_HOUR, REQUESTS_PER_HOUR = 5, 20
VISIBLE = (Job.Status.ORDERED, Job.Status.COMPLETED, Job.Status.CLOSED, Job.Status.CANCELLED)


# ------------------------------------------------------------------ who is signed in

def enabled():
    settings_row = ModuleSettings.load()
    return settings_row.contractor_portal_enabled and settings_row.maintenance_enabled


def jobs_for(account):
    """The jobs a contractor account may see: its firm's, once the order has been issued."""
    if account is None or not account.active:
        return Job.objects.none()
    return (Job.objects.filter(contractor_id=account.contractor_id, status__in=VISIBLE, ordered_on__isnull=False)
            .select_related("property", "owner"))


def may_sign_in(account):
    return account is not None and account.active and account.contractor.active and enabled()


def current(request):
    pk = request.session.get(SESSION_KEY)
    if not pk:
        return None
    now, limit = int(time.time()), settings.PHAEMA_PORTAL_IDLE_MINUTES * 60
    if limit and now - request.session.get(SEEN_KEY, 0) > limit:
        _sign_out(request)
        return None
    account = ContractorAccount.objects.select_related("contractor").filter(pk=pk).first()
    if not may_sign_in(account):
        _sign_out(request)
        return None
    request.session[SEEN_KEY] = now
    return account


def _sign_out(request):
    request.session.pop(SESSION_KEY, None)
    request.session.pop(SEEN_KEY, None)
    request.session.cycle_key()


def open_page(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not enabled():
            raise Http404
        request.contractor_account = None
        return portal_headers(view(request, *args, **kwargs), request)
    return wrapped


def contractor_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not enabled():
            raise Http404
        account = current(request)
        if account is None:
            return portal_headers(redirect("contractor:sign-in"), request)
        request.contractor_account = account
        set_api_user(None, f"{VIA}: {account.name} <{account.email}>")
        return portal_headers(view(request, *args, **kwargs), request)
    return wrapped


def _limited(key, limit):
    count = cache.get(key, 0)
    if count >= limit:
        return True
    cache.set(key, count + 1, 3600)
    return False


# ------------------------------------------------------------------ emails

def _council():
    return ModuleSettings.load().organisation_name or settings.PHAEMA_ORGANISATION_NAME or _("The council")


def portal_url():
    return settings.PHAEMA_BASE_URL.rstrip("/") + reverse("contractor:sign-in")


def invite(account, user):
    with translation.override(settings.LANGUAGE_CODE):
        council = _council()
        subject = _("%(council)s: your contractor portal account") % {"council": council}
        body = "\n".join([
            _("Dear %(name)s,") % {"name": account.name}, "",
            _("%(council)s has given you an account on its contractor portal for %(firm)s. You can see the works "
              "orders sent to your firm, accept or decline them, add progress notes and photos, and tell us when "
              "the work is done.") % {"council": council, "firm": account.contractor.name}, "",
            _("To sign in, go to %(url)s and enter this email address. We will email you a code each time.") % {
                "url": portal_url()}, "",
            _("If you were not expecting this, you can ignore this email."), "", council])
    email = OutgoingEmail.objects.create(kind="contractor_invite", to=account.email, subject=subject, body=body,
                                         created_by=user)
    notify.send(email)
    account.invited_by, account.invited_at = user, timezone.now()
    account.save(update_fields=["invited_by", "invited_at", "updated_at"])
    return email


def send_code(account):
    _row, code = ContractorSignInCode.issue(account)
    with translation.override(settings.LANGUAGE_CODE):
        council = _council()
        subject = _("%(council)s contractor portal: your sign-in code") % {"council": council}
        template = "\n".join([_("Your sign-in code is %(code)s"), "",
                              _("It works once, for %(minutes)s minutes.") % {"minutes": ContractorSignInCode.MINUTES},
                              "", _("If you did not try to sign in, you can ignore this email."), "", council])
    email = OutgoingEmail.objects.create(kind="contractor_code", to=account.email, subject=subject,
                                         body=template.replace("%(code)s", "••••••"))
    notify.send(email, body=template.replace("%(code)s", code))
    return email, code


def _tell_owner(job, subject, text):
    """Email the job's owner (the council officer) about something the contractor did."""
    if job.owner and job.owner.email:
        link = settings.PHAEMA_BASE_URL.rstrip("/") + job.get_absolute_url()
        send_mail(f"{subject}: {job.reference}", f"{text}\n\n{job.reference} {job.title}\n{link}",
                  settings.DEFAULT_FROM_EMAIL, [job.owner.email], fail_silently=True)


# ------------------------------------------------------------------ forms

class EmailForm(forms.Form):
    email = forms.EmailField(label=gettext_lazy("Email address"), max_length=254)


class CodeForm(forms.Form):
    code = forms.CharField(label=gettext_lazy("Sign-in code"), max_length=6, min_length=6)


class AcceptForm(forms.Form):
    attend_on = forms.DateField(label=gettext_lazy("When you expect to attend (optional)"), required=False,
                                widget=forms.DateInput(attrs={"type": "date"}))
    note = forms.CharField(label=gettext_lazy("Note (optional)"), required=False, max_length=1000,
                           widget=forms.Textarea(attrs={"rows": 2}))


class DeclineForm(forms.Form):
    reason = forms.CharField(label=gettext_lazy("Why you cannot take this job"), max_length=1000,
                             widget=forms.Textarea(attrs={"rows": 3}))


class NoteForm(forms.Form):
    text = forms.CharField(label=gettext_lazy("Progress note"), max_length=2000,
                           widget=forms.Textarea(attrs={"rows": 3}))
    photo = forms.ImageField(label=gettext_lazy("Photo (optional)"), required=False, validators=[validate_image])


class CompleteForm(forms.Form):
    completed_on = forms.DateField(label=gettext_lazy("Date the work was finished"),
                                   widget=forms.DateInput(attrs={"type": "date"}))
    notes = forms.CharField(label=gettext_lazy("Work done"), max_length=4000, widget=forms.Textarea(attrs={"rows": 4}))
    cost = forms.DecimalField(label=gettext_lazy("Cost (£, before VAT)"), min_value=0, max_digits=12,
                              decimal_places=2)
    invoice = forms.CharField(label=gettext_lazy("Your invoice reference"), max_length=60, required=False)

    def clean_completed_on(self):
        value = self.cleaned_data["completed_on"]
        if value > date.today():
            raise forms.ValidationError(_("The date cannot be in the future."))
        return value


# ------------------------------------------------------------------ pages

@never_cache
@open_page
def sign_in(request):
    if current(request) is not None:
        return redirect("contractor:home")
    form = EmailForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if _limited(f"contractor-ip:{client_ip(request)}", REQUESTS_PER_HOUR):
            form.add_error(None, _("Too many tries from this connection. Please try again in an hour."))
        else:
            email = form.cleaned_data["email"].strip().lower()
            account = ContractorAccount.objects.select_related("contractor").filter(email=email).first()
            request.session.pop(SHOWN_KEY, None)
            # The same answer whether or not there is an account, so the page does not reveal who has one.
            request.session[PENDING_KEY] = account.pk if may_sign_in(account) else 0
            if request.session[PENDING_KEY] and not _limited(f"contractor-codes:{email}", CODES_PER_HOUR):
                _email, code = send_code(account)
                if settings.PHAEMA_PORTAL_SHOW_CODES and not notify.configured():
                    request.session[SHOWN_KEY] = code
            return redirect("contractor:code")
    return render(request, "contractor/sign_in.html", {"form": form})


@never_cache
@open_page
def code(request):
    if PENDING_KEY not in request.session:
        return redirect("contractor:sign-in")
    form = CodeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if _limited(f"contractor-ip:{client_ip(request)}", REQUESTS_PER_HOUR):
            form.add_error(None, _("Too many tries from this connection. Please try again in an hour."))
        else:
            row = (ContractorSignInCode.objects.filter(account_id=request.session[PENDING_KEY], used_at__isnull=True)
                   .select_related("account__contractor").order_by("-created_at").first())
            if row is not None and row.matches(form.cleaned_data["code"]) and may_sign_in(row.account):
                request.session.pop(PENDING_KEY, None)
                request.session.pop(SHOWN_KEY, None)
                request.session.cycle_key()
                request.session[SESSION_KEY] = row.account_id
                request.session[SEEN_KEY] = int(time.time())
                # Not audited on purpose: see core.audit._EXCLUDED.
                ContractorAccount.objects.filter(pk=row.account_id).update(last_sign_in=timezone.now())
                return redirect("contractor:home")
            form.add_error("code", _("That code is not right, has been used or has run out. Check the latest email, "
                                     "or ask for a new code."))
    return render(request, "contractor/code.html", {"form": form, "shown_code": request.session.get(SHOWN_KEY),
                                                     "minutes": ContractorSignInCode.MINUTES})


@require_POST
def sign_out(request):
    _sign_out(request)
    return redirect("contractor:sign-in")


@never_cache
@contractor_required
def home(request):
    jobs = jobs_for(request.contractor_account).order_by("-ordered_on", "-number")
    waiting = [j for j in jobs if j.status == Job.Status.ORDERED and not j.contractor_response]
    in_hand = [j for j in jobs if j.status == Job.Status.ORDERED and j.contractor_response == "accepted"]
    done = [j for j in jobs if j.status in (Job.Status.COMPLETED, Job.Status.CLOSED)][:30]
    return render(request, "contractor/home.html", {"waiting": waiting, "in_hand": in_hand, "done": done})


def _job(request, pk):
    return get_object_or_404(jobs_for(request.contractor_account), pk=pk)


@never_cache
@contractor_required
def job_page(request, pk):
    from .views import _safety

    job = _job(request, pk)
    account = request.contractor_account
    action = request.POST.get("action") if request.method == "POST" else ""
    forms_ = {"accept": AcceptForm(), "decline": DeclineForm(), "note": NoteForm(),
              "complete": CompleteForm(initial={"completed_on": date.today(), "cost": job.estimate})}
    is_open = job.status == Job.Status.ORDERED and job.contractor_response != "declined"
    if action and not is_open:
        raise Http404
    if action == "accept" and not job.contractor_response:
        form = forms_["accept"] = AcceptForm(request.POST)
        if form.is_valid():
            job.contractor_response, job.contractor_response_at = "accepted", timezone.now()
            job.attend_on = form.cleaned_data["attend_on"]
            job.save(update_fields=["contractor_response", "contractor_response_at", "attend_on", "updated_at"])
            JobUpdate.objects.create(job=job, account=account, kind=JobUpdate.Kind.ACCEPTED,
                                     text=form.cleaned_data["note"])
            return redirect("contractor:job", pk=job.pk)
    elif action == "decline" and not job.contractor_response:
        form = forms_["decline"] = DeclineForm(request.POST)
        if form.is_valid():
            job.contractor_response, job.contractor_response_at = "declined", timezone.now()
            job.save(update_fields=["contractor_response", "contractor_response_at", "updated_at"])
            JobUpdate.objects.create(job=job, account=account, kind=JobUpdate.Kind.DECLINED,
                                     text=form.cleaned_data["reason"])
            _tell_owner(job, "Works order declined", f"{account.contractor} declined the order: "
                                                     f"{form.cleaned_data['reason']}")
            return redirect("contractor:home")
    elif action == "note" and job.contractor_response == "accepted":
        form = forms_["note"] = NoteForm(request.POST, request.FILES)
        if form.is_valid():
            JobUpdate.objects.create(job=job, account=account, kind=JobUpdate.Kind.NOTE,
                                     text=form.cleaned_data["text"], photo=form.cleaned_data.get("photo"))
            return redirect(reverse("contractor:job", args=[job.pk]) + "#updates")
    elif action == "complete" and job.contractor_response == "accepted":
        form = forms_["complete"] = CompleteForm(request.POST)
        files, refused = _checked_files(request.FILES.getlist("certificates"))
        if refused:
            form.add_error(None, _("These files could not be added: %(f)s") % {"f": ", ".join(refused)})
        if form.is_valid():
            data = form.cleaned_data
            with transaction.atomic():
                workflow.complete(job, data["completed_on"], data["cost"], data["notes"], data["invoice"])
                for f in files:
                    JobDocument.objects.create(job=job, description=f"From {account.contractor}: {f.name}"[:200],
                                               file=f, original_filename=f.name[:255], from_contractor=True)
                JobUpdate.objects.create(job=job, account=account, kind=JobUpdate.Kind.COMPLETED,
                                         text=data["notes"])
            _tell_owner(job, "Work reported done", f"{account.contractor} reported the work done on "
                                                   f"{data['completed_on']:%d %B %Y}, cost £{data['cost']:,.2f}.")
            return redirect("contractor:home")
    return render(request, "contractor/job.html", {
        "job": job, "safety": _safety(job.property), "updates": job.updates.select_related("account"),
        "documents": job.documents.filter(from_contractor=True), "is_open": is_open, **{f"{k}_form": v for k, v in forms_.items()}})


def _checked_files(uploads):
    """The certificates and other files sent with a completion that PHAEMA accepts, and the names of those it
    refuses, at most ten."""
    from django.core.exceptions import ValidationError

    from apps.cases.models import validate_case_file

    good, refused = [], []
    for upload in uploads[:10]:
        try:
            validate_case_file(upload)
        except ValidationError as exc:
            refused.append(f"{upload.name} ({exc.messages[0]})")
        else:
            good.append(upload)
    if len(uploads) > 10:
        refused.append(_("more than ten files"))
    return good, refused


@contractor_required
def update_photo(request, pk, update_pk):
    job = _job(request, pk)
    update = get_object_or_404(JobUpdate, pk=update_pk, job=job)
    if not update.photo:
        raise Http404
    return FileResponse(update.photo.open("rb"), content_type="image/jpeg")


@contractor_required
def document(request, pk, doc_pk):
    job = _job(request, pk)
    doc = get_object_or_404(JobDocument, pk=doc_pk, job=job, from_contractor=True)
    return FileResponse(doc.file.open("rb"), as_attachment=True, filename=doc.original_filename or "document")
