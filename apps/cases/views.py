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
from django.utils.translation import gettext_lazy
from django.views.generic import ListView

from apps.core.roles import ADMINISTRATORS, CONTRIBUTORS, SURVEYORS, is_administrator
from apps.core.tables import sortable
from apps.leases.models import Lease, LeaseEvent
from apps.properties.models import Property
from apps.reports.mixins import ExportMixin

from . import emails, leasing, standards, workflow
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
        from apps.core import places

        qs = places.apply(qs, get, self.request.user, "property", "lease__properties")
        if get.get("approval") == "mine":
            qs = qs.filter(approvals__status="pending", approvals__approver=self.request.user).distinct()
        elif get.get("approval") == "waiting":
            qs = qs.filter(approvals__status="pending").distinct()
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
                ("approval", "Approval", [("mine", "Waiting for my approval"), ("waiting", "Waiting for approval")],
                 get.get("approval", ""), True),
                ("owner", "Owner", [("me", "Mine"), ("none", "Nobody")]
                 + [(str(u.pk), u.get_full_name() or u.username) for u in people], get.get("owner", ""), True),
                *_place_filters(get),
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


def _place_filters(get):
    from apps.core import places

    return places.filters(get)


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
    wanted = CaseType.objects.filter(code=request.GET.get("type", ""), active=True).first()
    if wanted:  # e.g. the lease page's "get the tenant's insurance certificate" link
        initial.update({"case_type": wanted.pk, "title": wanted.name})
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
                "add_task", "task_done", "assign", "raise_fee", "links", "request_approval", "withdraw_approval",
                "save_heads", "save_notice", "save_dilaps", "save_conflict"}
ACTIONS_APPROVER = {"approve", "return", "reassign_approval"}
ACTIONS_CONTRIBUTE = {"add_note", "add_correspondence", "add_document", "file_email"}


@login_required
def case_detail(request, pk):
    case = get_object_or_404(Case.objects.select_related("case_type", "owner", "lease", "lease__counterparty",
                                                         "property", "party", "event", "fee_charge"), pk=pk)
    can_work = workflow.can_work(request.user, case)
    can_contribute = workflow.can_contribute(request.user, case)
    if request.method == "POST":
        action = request.POST.get("action", "")
        if action in ACTIONS_APPROVER:
            _approval_action(request, case, action)
            return redirect(case)
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
    timeline += [("approval", a.created_at.date(), a)
                 for a in case.approvals.select_related("requested_by", "approver", "decided_by")]
    timeline.sort(key=lambda item: (item[1], getattr(item[2], "created_at", None) or today), reverse=True)
    tasks = list(case.tasks.select_related("owner", "done_by"))
    stages = [(s, label, [t for t in tasks if t.stage == s]) for s, label in Stage.choices]
    from apps.projects.rules import project_for

    return render(request, "cases/case_detail.html", {
        "case": case, "project": project_for(request.user, case), "can_work": can_work, "can_contribute": can_contribute, "today": today,
        "stages": stages, "stage_index": STAGE_ORDER.index(case.stage), "timeline": timeline,
        "rag": case.rag(today), "decisions": Case.Decision.choices,
        "people": _people(ADMINISTRATORS, SURVEYORS), "contributors": _people(CONTRIBUTORS),
        "lease": case.lease, "show_confidential": show_confidential,
        "doc_templates": _templates_for(case) if can_contribute else [],
        "hidden_notes": case.notes.filter(confidential=True).count() if not show_confidential else 0,
        "is_administrator": is_administrator(request.user),
        "valuation_report_property": case.main_property if case.case_type.group == "valuation" else None,
        **_approval_context(request.user, case),
        **_leasing_context(case),
        **_standards_context(case),
    })


DILAPS_FIELDS = [
    ("dilaps_schedule_value", gettext_lazy("Schedule of dilapidations (£)"), "money"),
    ("dilaps_served_on", gettext_lazy("Date the schedule was served"), "date"),
    ("dilaps_response_value", gettext_lazy("Tenant's response (£)"), "money"),
    ("dilaps_response_on", gettext_lazy("Date the response was received"), "date"),
    ("dilaps_settlement_value", gettext_lazy("Settlement (£)"), "money"),
    ("dilaps_settled_on", gettext_lazy("Date settled"), "date"),
    ("dilaps_costs", gettext_lazy("Council's costs (£)"), "money"),
    ("dilaps_notes", gettext_lazy("Notes"), "text"),
]


def _standards_context(case):
    from apps.compliance.safety import info

    return {
        "mees_warnings": standards.mees(case) if case.is_open else [],
        "dilaps": standards.dilaps(case),
        "dilaps_fields": [(n, label, getattr(case, n), kind) for n, label, kind in DILAPS_FIELDS],
        "safety": info(case.property or (case.lease.property if case.lease_id else None)),
    }


def _money(text):
    from decimal import Decimal, InvalidOperation

    text = (text or "").replace(",", "").replace("£", "").strip()
    if not text:
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError(text)
    if value < 0:
        raise ValueError(text)
    return value.quantize(Decimal("0.01"))


def _templates_for(case):
    from apps.documents.views import for_case

    return for_case(case)


def _optional_date(text):
    try:
        return date.fromisoformat(text or "")
    except ValueError:
        return None


def _blocked_by_terms(request, case, stage):
    if stage != "decision":
        return False
    problems = leasing.problems(case)
    for problem in problems:
        messages.error(request, problem)
    return bool(problems)


def _leasing_context(case):
    if not (case.case_type.heads_of_terms or case.case_type.code == "renewal"):
        return {}
    terms, current = case.heads_of_terms or {}, leasing.from_lease(case.lease)
    return {
        "heads": [(k, label, hint, terms.get(k, ""), current.get(k, "")) for k, label, hint in leasing.ITEMS],
        "heads_answered": len(leasing.answered(case)), "heads_total": len(leasing.KEYS),
        "terms_problems": leasing.problems(case),
        "notice": leasing.notice_dates(case) if case.case_type.code == "renewal" else None,
        "notice_kinds": Case._meta.get_field("notice_kind").choices,
    }


def _next_stage(case):
    i = STAGE_ORDER.index(case.stage)
    return STAGE_ORDER[i + 1] if i + 1 < len(STAGE_ORDER) else None


def _approval_context(user, case):
    pending = workflow.pending_approval(case)
    upcoming = _next_stage(case)
    gate = upcoming if upcoming and workflow.needs_approval(case, upcoming) else None
    return {
        "pending_approval": pending,
        "can_decide_approval": bool(pending and workflow.can_decide_approval(user, pending)),
        "approval_gate": gate, "approval_gate_label": dict(Stage.choices).get(gate, ""),
        "decision_needs_approval": workflow.needs_approval(case, "decision"),
        "my_approver": workflow.approver_for(user),
        "approvals": case.approvals.select_related("requested_by", "approver", "decided_by"),
        "approvers": _people(ADMINISTRATORS, SURVEYORS),
    }


def _approval_action(request, case, action):
    approval = workflow.pending_approval(case)
    if approval is None:
        messages.error(request, _("There is no approval waiting on this case."))
        return
    if action == "reassign_approval":
        if not is_administrator(request.user):
            raise PermissionDenied
        new = get_user_model().objects.filter(pk=request.POST.get("approver") or 0, is_active=True).first()
        if new is None or new.pk == approval.requested_by_id:
            messages.error(request, _("Choose someone other than the person who asked."))
            return
        workflow.reassign_approval(approval, new)
        messages.success(request, _("Approval sent to %(name)s.") % {"name": new.get_full_name() or new.username})
        return
    if not workflow.can_decide_approval(request.user, approval):
        raise PermissionDenied
    comments = request.POST.get("comments", "")
    if action == "return" and not comments.strip():
        messages.error(request, _("Say why you are returning it."))
        return
    workflow.decide_approval(approval, request.user, action == "approve", comments)
    messages.success(request, _("Approved: the case has moved to %(stage)s.") % {"stage": case.get_stage_display()}
                     if action == "approve" else _("Returned to %(name)s with your comments.")
                     % {"name": approval.requested_by.get_full_name() or approval.requested_by.username})


def _do(request, case, action):  # noqa: C901 - one branch per action keeps each one short
    post, today = request.POST, date.today()
    if action == "next_stage":
        upcoming = _next_stage(case)
        if _blocked_by_terms(request, case, upcoming):
            return
        if upcoming and workflow.needs_approval(case, upcoming):
            messages.error(request, _("This stage needs your supervisor's approval first. Ask for approval below."))
            return
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
        if decision != Case.Decision.WITHDRAWN and workflow.needs_approval(case, "decision"):
            messages.error(request, _("The decision needs your supervisor's approval first. Ask for approval, "
                                      "with your recommendation."))
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
        if workflow.needs_approval(case, "decision") and case.decision != Case.Decision.WITHDRAWN:
            messages.error(request, _("This case needs approval before a decision. If the request was withdrawn, "
                                      "record the decision as Withdrawn first."))
            return
        if case.event_id and case.event.status in workflow.OPEN_EVENT:
            messages.error(request, _("Record the outcome on the lease event first; the case then closes itself."))
            return
        workflow.close(case, post.get("outcome", "").strip())
        messages.success(request, _("Case closed."))
    elif action == "reopen":
        case.status, case.closed_on = Case.Status.OPEN, None
        case.save(update_fields=["status", "closed_on", "updated_at"])
    elif action == "request_approval":
        stage = post.get("stage", "")
        if stage not in STAGE_ORDER or not workflow.needs_approval(case, stage):
            messages.error(request, _("No approval is needed for that stage."))
            return
        if _blocked_by_terms(request, case, stage):
            return
        if standards.conflict_missing(case):
            messages.error(request, _("Confirm whether there is a conflict of interest before asking for approval."))
            return
        if not post.get("recommendation", "").strip():
            messages.error(request, _("Write your recommendation for the approver."))
            return
        try:
            approval = workflow.request_approval(case, request.user, stage, post["recommendation"])
        except ValueError as exc:
            messages.error(request, str(exc))
            return
        messages.success(request, _("Sent to %(name)s for approval.")
                         % {"name": approval.approver.get_full_name() or approval.approver.username})
    elif action == "save_heads":
        case.heads_of_terms = {k: post.get(f"hot_{k}", "").strip() for k in leasing.KEYS
                               if post.get(f"hot_{k}", "").strip()}
        case.tenant_represented = post.get("tenant_represented", "") if post.get("tenant_represented") in ("yes", "no") \
            else ""
        case.code_given_on = _optional_date(post.get("code_given_on"))
        case.save(update_fields=["heads_of_terms", "tenant_represented", "code_given_on", "updated_at"])
        messages.success(request, _("Heads of terms saved: %(n)s of %(t)s items covered.")
                         % {"n": len(leasing.answered(case)), "t": len(leasing.KEYS)})
    elif action == "save_notice":
        kind = post.get("notice_kind", "")
        case.notice_kind = kind if kind in ("s25", "s26") else ""
        case.notice_served_on = _optional_date(post.get("notice_served_on"))
        case.notice_date = _optional_date(post.get("notice_date"))
        case.landlord_opposes = post.get("landlord_opposes") == "1"
        case.opposition_grounds = post.get("opposition_grounds", "").strip()[:100]
        deadline = leasing.notice_dates(case).court_deadline
        if deadline and not case.case_type.target_days:
            case.target_date = deadline
        case.save()
        messages.success(request, _("Notice dates saved."))
        for warning in leasing.notice_dates(case).warnings:
            messages.warning(request, warning)
    elif action == "save_dilaps":
        changed = []
        for name, label, kind in DILAPS_FIELDS:
            raw = post.get(name, "")
            if kind == "money":
                try:
                    value = _money(raw)
                except ValueError:
                    messages.error(request, _("%(label)s must be an amount in pounds.") % {"label": label})
                    return
            elif kind == "date":
                value = _optional_date(raw)
            else:
                value = raw.strip()
            setattr(case, name, value)
            changed.append(name)
        case.save(update_fields=[*changed, "updated_at"])
        messages.success(request, _("Dilapidations saved."))
    elif action == "save_conflict":
        choice = post.get("conflict", "")
        details = post.get("conflict_details", "").strip()
        if choice not in ("none", "declared"):
            messages.error(request, _("Choose whether there is a conflict of interest."))
            return
        if choice == "declared" and not details:
            messages.error(request, _("Describe the conflict and how it is managed."))
            return
        case.conflict, case.conflict_details = choice, details if choice == "declared" else ""
        case.conflict_by, case.conflict_on = request.user, date.today()
        case.save(update_fields=["conflict", "conflict_details", "conflict_by", "conflict_on", "updated_at"])
        messages.success(request, _("Conflict of interest declaration saved."))
    elif action == "withdraw_approval":
        approval = workflow.pending_approval(case)
        if approval and approval.requested_by_id == request.user.pk:
            approval.status = "withdrawn"
            approval.save(update_fields=["status", "updated_at"])
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
        "to_approve": Case.objects.filter(approvals__status="pending", approvals__approver=user).distinct().count(),
        "no_supervisor": _without_supervisor() if is_administrator(user) else [],
    }


def _without_supervisor():
    """Surveyors with no supervisor to approve their work."""
    from apps.core.models import StaffProfile

    have = StaffProfile.objects.filter(supervisor__isnull=False).values_list("user_id", flat=True)
    return list(_people(SURVEYORS).exclude(pk__in=have))
