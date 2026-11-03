# SPDX-License-Identifier: AGPL-3.0-or-later
"""Case pages: the list, starting a case, and the case page where all the work happens."""
from datetime import date

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.generic import ListView

from apps.core.roles import ADMINISTRATORS, CONTRIBUTORS, SURVEYORS, is_administrator
from apps.core.tables import sortable
from apps.leases.models import Lease, LeaseEvent
from apps.properties.models import Property
from apps.reports.mixins import ExportMixin

from . import emails, workflow
from .models import STAGE_ORDER, Case, CaseDocument, CaseNote, CaseTask, CaseType, Correspondence, Stage

COLUMNS = {
    "ref": ("Case", ["year", "number"], False),
    "type": ("Type", ["case_type__name", "number"], False),
    "stage": ("Stage", ["stage", "number"], False),
    "owner": ("Owner", ["owner__first_name", "owner__username", "number"], False),
    "target": ("Target", ["target_date", "number"], False),
}


def _people(*roles):
    return get_user_model().objects.filter(is_active=True, groups__name__in=roles).distinct().order_by("first_name")


class CaseListView(LoginRequiredMixin, ExportMixin, ListView):
    model = Case
    export_dataset, export_title = "cases", "Cases"
    paginate_by = 50
    template_name = "cases/case_list.html"

    def get_queryset(self):
        get, today = self.request.GET, date.today()
        qs = Case.objects.select_related("case_type", "owner", "lease", "property", "party")
        status = get.get("status", "open")
        if status == "open":
            qs = qs.exclude(status=Case.Status.CLOSED)
        elif status in ("on_hold", "closed"):
            qs = qs.filter(status=status)
        for key, field in (("type", "case_type__code"), ("stage", "stage"), ("group", "case_type__group")):
            if get.get(key):
                qs = qs.filter(**{field: get[key]})
        who = get.get("owner", "")
        if who == "me":
            qs = qs.filter(Q(owner=self.request.user) | Q(contributors=self.request.user)).distinct()
        elif who == "none":
            qs = qs.filter(owner__isnull=True)
        elif who.isdigit():
            qs = qs.filter(owner_id=int(who))
        if get.get("when") == "past":
            qs = qs.exclude(status=Case.Status.CLOSED).filter(target_date__lt=today, decision_on__isnull=True)
        q = get.get("q", "").strip()
        if q:
            number = q.upper().replace("CAS-", "").split("/")[0].split("-")[-1]
            match = Q(title__icontains=q) | Q(lease__reference__icontains=q) | Q(party__name__icontains=q) \
                | Q(property__reference__icontains=q) | Q(property__name__icontains=q)
            if number.isdigit():
                match |= Q(number=int(number))
            qs = qs.filter(match)
        ordering, self.headings = sortable(self.request, COLUMNS, "-ref")
        return qs.order_by(*ordering)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        get = self.request.GET
        people = _people(ADMINISTRATORS, SURVEYORS)
        ctx.update({
            "q": get.get("q", ""), "headings": self.headings, "today": date.today(),
            "filters": [
                ("status", "Status", [("open", "Open or on hold"), ("on_hold", "On hold"), ("closed", "Closed"),
                                     ("all", "All")], get.get("status", "open"), False),
                ("group", "Group", CaseType.Group.choices, get.get("group", ""), True),
                ("stage", "Stage", Stage.choices, get.get("stage", ""), True),
                ("when", "Target", [("past", "Past target")], get.get("when", ""), True),
                ("owner", "Owner", [("me", "Mine"), ("none", "Nobody")]
                 + [(str(u.pk), u.get_full_name() or u.username) for u in people], get.get("owner", ""), True),
            ],
            "can_open": _can_open(self.request.user),
        })
        params = get.copy()
        params.pop("page", None)
        ctx["querystring"] = params.urlencode()
        return ctx


class NewCaseForm(forms.Form):
    case_type = forms.ModelChoiceField(CaseType.objects.filter(active=True), label="Type of case")
    title = forms.CharField(max_length=200, label="Short description",
                            help_text="For example: Consent to assign to Example Trading Ltd")
    lease = forms.ModelChoiceField(Lease.objects.select_related("counterparty").order_by("reference"),
                                   required=False, label="Agreement")
    property = forms.ModelChoiceField(Property.objects.order_by("reference"), required=False, label="Property",
                                      help_text="If there is no agreement, or to name one property of several.")
    how_received = forms.ChoiceField(choices=Case.Received.choices, label="Received by")
    received_on = forms.DateField(initial=date.today, label="Date received",
                                  widget=forms.DateInput(attrs={"type": "date"}),
                                  help_text="For consents, the date the written application arrived: it starts the clock.")
    applicant_reference = forms.CharField(max_length=60, required=False, label="Applicant's reference")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["case_type"].label_from_instance = lambda t: f"{t.get_group_display()}: {t.name}"
        self.fields["lease"].label_from_instance = lambda lease: f"{lease.reference} – {lease.counterparty.name}"
        self.fields["property"].label_from_instance = lambda p: f"{p.reference} – {p.name}"


def _can_open(user):
    return is_administrator(user) or user.groups.filter(name=SURVEYORS).exists()


@login_required
def case_new(request):
    if not _can_open(request.user):
        raise PermissionDenied
    event_id = request.GET.get("event") or request.POST.get("event")
    if event_id:  # Start a case from a lease event
        event = get_object_or_404(LeaseEvent, pk=event_id)
        case, created = workflow.case_for_event(event, request.user)
        if created:
            messages.success(request, _("Case %(ref)s opened.") % {"ref": case.display_reference})
        return redirect(case)
    initial = {k: request.GET[k] for k in ("lease", "property") if request.GET.get(k)}
    form = NewCaseForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        case = workflow.open_case(d["case_type"], title=d["title"], lease=d["lease"], property=d["property"],
                                  how_received=d["how_received"], received_on=d["received_on"],
                                  applicant_reference=d["applicant_reference"])
        if not case.owner_id:
            case.owner = request.user
            case.save(update_fields=["owner"])
        messages.success(request, _("Case %(ref)s opened.") % {"ref": case.display_reference})
        return redirect(case)
    return render(request, "cases/case_new.html", {"form": form})


# ------------------------------------------------------------------ the case page

def _date(value):
    try:
        return date.fromisoformat(value) if value else date.today()
    except ValueError:
        return date.today()


def _store_upload(case, upload, description, correspondence=None):
    from django.core.exceptions import ValidationError

    from .models import validate_case_file

    try:
        validate_case_file(upload)
    except ValidationError as exc:
        return exc.messages[0]
    doc = CaseDocument(case=case, description=description[:200] or upload.name, correspondence=correspondence,
                       original_filename=upload.name[:255])
    doc.file.save(upload.name, upload, save=False)
    doc.save()
    return None


def _file_email(case, upload, direction):
    """File a saved email: read its details, keep the email, and keep its attachments as documents."""
    from django.core.exceptions import ValidationError

    from .models import validate_case_file

    try:
        validate_case_file(upload)
    except ValidationError as exc:
        return None, exc.messages[0]
    upload.seek(0)
    data = upload.read()
    parsed = emails.parse(upload.name, data)
    item = Correspondence(case=case, direction=direction, method=Correspondence.Method.EMAIL,
                          original_filename=upload.name[:255])
    if parsed:
        item.on = parsed.sent or date.today()
        item.correspondent = (parsed.sender if direction == "in" else parsed.recipients)[:250]
        item.subject = parsed.subject[:250]
        item.summary = parsed.text.strip()[:20000]
    item.file.save(upload.name, ContentFile(data), save=False)
    item.save()
    problems = []
    for name, payload in (parsed.attachments if parsed else []):
        problem = _store_upload(case, ContentFile(payload, name=name), f"Attachment: {name}", correspondence=item)
        if problem:
            problems.append(f"{name}: {problem}")
    return item, "; ".join(problems)


ACTIONS_WORK = {"next_stage", "hold", "resume", "acknowledge", "complete_application", "decide", "close", "reopen",
                "add_task", "task_done", "assign", "raise_fee", "links"}
ACTIONS_CONTRIBUTE = {"add_note", "add_correspondence", "add_document", "file_email"}


@login_required
def case_detail(request, pk):
    case = get_object_or_404(Case.objects.select_related("case_type", "owner", "lease", "lease__counterparty",
                                                         "property", "party", "event", "fee_charge"), pk=pk)
    can_work = workflow.can_work(request.user, case)
    can_contribute = workflow.can_contribute(request.user, case)
    if request.method == "POST":
        action = request.POST.get("action", "")
        if (action in ACTIONS_WORK and not can_work) or (action in ACTIONS_CONTRIBUTE and not can_contribute) \
                or action not in ACTIONS_WORK | ACTIONS_CONTRIBUTE:
            raise PermissionDenied
        _do(request, case, action)
        return redirect(case)
    today = date.today()
    show_confidential = workflow.sees_confidential(request.user, case)
    notes = case.notes.select_related("created_by")
    if not show_confidential:
        notes = notes.filter(confidential=False)
    timeline = [("note", n.created_at.date(), n) for n in notes]
    timeline += [("correspondence", c.on, c) for c in case.correspondence.all()]
    timeline += [("document", d.created_at.date(), d) for d in case.documents.filter(correspondence__isnull=True)]
    timeline.sort(key=lambda item: (item[1], getattr(item[2], "created_at", None) or today), reverse=True)
    tasks = list(case.tasks.select_related("owner", "done_by"))
    stages = [(s, label, [t for t in tasks if t.stage == s]) for s, label in Stage.choices]
    return render(request, "cases/case_detail.html", {
        "case": case, "can_work": can_work, "can_contribute": can_contribute, "today": today,
        "stages": stages, "stage_index": STAGE_ORDER.index(case.stage), "timeline": timeline,
        "rag": case.rag(today), "decisions": Case.Decision.choices,
        "people": _people(ADMINISTRATORS, SURVEYORS), "contributors": _people(CONTRIBUTORS),
        "lease": case.lease, "show_confidential": show_confidential,
        "hidden_notes": case.notes.filter(confidential=True).count() if not show_confidential else 0,
        "is_administrator": is_administrator(request.user),
    })


def _do(request, case, action):  # noqa: C901 - one branch per action keeps each one short
    post, today = request.POST, date.today()
    if action == "next_stage":
        if workflow.next_stage(case):
            messages.success(request, _("Moved to %(stage)s.") % {"stage": case.get_stage_display()})
    elif action == "hold":
        case.status, case.on_hold_reason = Case.Status.ON_HOLD, post.get("reason", "")[:200]
        case.save(update_fields=["status", "on_hold_reason", "updated_at"])
    elif action == "resume":
        case.status, case.on_hold_reason = Case.Status.OPEN, ""
        case.save(update_fields=["status", "on_hold_reason", "updated_at"])
    elif action == "acknowledge":
        case.acknowledged_on = _date(post.get("date"))
        case.save(update_fields=["acknowledged_on", "updated_at"])
        case.tasks.filter(description__startswith="Acknowledge", done_on__isnull=True).update(
            done_on=case.acknowledged_on, done_by=request.user)
    elif action == "complete_application":
        case.application_complete_on = _date(post.get("date"))
        case.refresh_target()
        case.save(update_fields=["application_complete_on", "target_date", "updated_at"])
        messages.success(request, _("Application recorded as complete. Target date: %(d)s.")
                         % {"d": case.target_date.strftime("%d %b %Y") if case.target_date else "none"})
    elif action == "decide":
        decision = post.get("decision", "")
        reasons = post.get("reasons", "").strip()
        if decision not in Case.Decision.values:
            messages.error(request, _("Choose a decision."))
            return
        if case.case_type.statutory_1988 and decision in (Case.Decision.CONDITIONS, Case.Decision.REFUSED) \
                and not reasons:
            messages.error(request, _("The Landlord and Tenant Act 1988 requires written reasons for conditions or "
                                      "a refusal."))
            return
        case.decision, case.reasons, case.decision_on = decision, reasons, _date(post.get("date"))
        if case.stage in (Stage.RECEIVED, Stage.INFORMATION, Stage.ASSESSING):
            case.stage = Stage.DECISION
        case.save(update_fields=["decision", "reasons", "decision_on", "stage", "updated_at"])
        messages.success(request, _("Decision recorded."))
    elif action == "close":
        if case.event_id and case.event.status in workflow.OPEN_EVENT:
            messages.error(request, _("Record the outcome on the lease event first; the case then closes itself."))
            return
        workflow.close(case, post.get("outcome", "").strip())
        messages.success(request, _("Case closed."))
    elif action == "reopen":
        case.status, case.closed_on = Case.Status.OPEN, None
        case.save(update_fields=["status", "closed_on", "updated_at"])
    elif action == "add_task":
        if post.get("description", "").strip():
            CaseTask.objects.create(case=case, stage=post.get("stage") if post.get("stage") in STAGE_ORDER
                                    else case.stage, description=post["description"].strip()[:200],
                                    due_date=_date(post["due"]) if post.get("due") else None, owner=case.owner,
                                    order=999)
    elif action == "task_done":
        task = get_object_or_404(CaseTask, pk=post.get("task"), case=case)
        task.done_on, task.done_by = (None, None) if task.done_on else (today, request.user)
        task.save(update_fields=["done_on", "done_by"])
    elif action == "assign":
        owner = get_user_model().objects.filter(pk=post.get("owner") or 0).first()
        case.owner = owner
        case.save(update_fields=["owner", "updated_at"])
        case.contributors.set(get_user_model().objects.filter(pk__in=post.getlist("contributors")))
        messages.success(request, _("People updated."))
    elif action == "links":
        for field in ("iken_matter", "crm_reference", "applicant_reference"):
            setattr(case, field, post.get(field, "").strip()[:60])
        case.save(update_fields=["iken_matter", "crm_reference", "applicant_reference", "updated_at"])
    elif action == "raise_fee":
        charge = workflow.raise_fee(case)
        if charge:
            messages.success(request, _("Fee %(ref)s of £%(amount)s charged to the tenant's rent account.")
                             % {"ref": charge.reference, "amount": f"{charge.gross:,.2f}"})
        else:
            messages.error(request, _("No fee to raise: the case needs an agreement and its type a fee."))
    elif action == "add_note":
        if post.get("text", "").strip():
            CaseNote.objects.create(case=case, text=post["text"].strip(), confidential=post.get("confidential") == "1")
    elif action == "add_correspondence":
        upload = request.FILES.get("file")
        item = Correspondence(case=case, direction=post.get("direction", "in")[:3], method=post.get("method", "email"),
                              on=_date(post.get("date")), correspondent=post.get("correspondent", "")[:250],
                              subject=post.get("subject", "")[:250], summary=post.get("summary", ""))
        if upload:
            problem = _validate(upload)
            if problem:
                messages.error(request, problem)
                return
            item.original_filename = upload.name[:255]
            item.file.save(upload.name, upload, save=False)
        item.save()
    elif action == "file_email":
        upload = request.FILES.get("file")
        if not upload or upload.name.rsplit(".", 1)[-1].lower() not in ("eml", "msg"):
            messages.error(request, _("Choose a saved email: an .eml file, or an .msg file from Outlook."))
            return
        item, problems = _file_email(case, upload, post.get("direction", "in"))
        if item is None:
            messages.error(request, problems)
            return
        messages.success(request, _("Email filed: %(s)s") % {"s": item.subject or upload.name})
        if problems:
            messages.error(request, _("Some attachments were not kept: %(p)s") % {"p": problems})
    elif action == "add_document":
        upload = request.FILES.get("file")
        if not upload:
            messages.error(request, _("Choose a file."))
            return
        problem = _store_upload(case, upload, post.get("description", ""))
        if problem:
            messages.error(request, problem)


def _validate(upload):
    from django.core.exceptions import ValidationError

    from .models import validate_case_file

    try:
        validate_case_file(upload)
    except ValidationError as exc:
        return exc.messages[0]
    return None


def cases_summary(user):
    """Figures for the dashboard."""
    today = date.today()
    open_cases = Case.objects.exclude(status=Case.Status.CLOSED)
    return {
        "open": open_cases.count(),
        "past_target": open_cases.filter(target_date__lt=today, decision_on__isnull=True).count(),
        "mine": open_cases.filter(owner=user).count(),
        "by_stage": dict(open_cases.values_list("stage").annotate(n=Count("pk"))),
        "tasks_overdue": CaseTask.objects.filter(case__in=open_cases, done_on__isnull=True, due_date__lt=today).count(),
    }
