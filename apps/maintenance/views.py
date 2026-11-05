# SPDX-License-Identifier: AGPL-3.0-or-later
"""Maintenance pages: overview, jobs and works orders, planned maintenance, components, contractors."""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from apps.core import places
from apps.core.models import ModuleSettings, supervisor_of
from apps.core.access import module_view
from apps.core.roles import SURVEYORS, can_edit, is_administrator
from apps.core.tables import sortable
from apps.properties.models import Property
from apps.reports.export import csv_response, xlsx_response
from apps.reports.mixins import ExportMixin

from . import library, responsibility, workflow
from .models import Category, Component, Contract, Contractor, Job, JobDocument, PlannedTask, Responsibility


maintenance_view = module_view("maintenance", "maintenance/off.html")  # switched on for the council and opened by an access area


def _can_raise(user):
    return is_administrator(user) or user.groups.filter(name=SURVEYORS).exists()


def _money(text):
    try:
        return Decimal(str(text).replace(",", "").replace("£", "").strip()).quantize(Decimal("0.01")) \
            if str(text).strip() else None
    except InvalidOperation:
        return None


def _date(text, default=None):
    try:
        return date.fromisoformat(text or "")
    except ValueError:
        return default


# ------------------------------------------------------------------ overview

@maintenance_view
def home(request):
    today = date.today()
    open_jobs = Job.objects.filter(status__in=Job.OPEN).select_related("property", "contractor", "owner")
    urgent = open_jobs.filter(Q(priority="emergency") | Q(target_date__lt=today)).order_by("target_date")[:15]
    tasks = PlannedTask.objects.filter(active=True).select_related("property", "contractor")
    overdue = tasks.filter(next_due__lt=today).order_by("-statutory", "next_due")[:15]
    soon = tasks.filter(next_due__gte=today, next_due__lte=today + timedelta(days=30)).order_by("next_due")[:15]
    contracts = [c for c in Contract.objects.select_related("contractor")
                 if c.retender_due <= today + timedelta(days=183) and (not c.ends or c.ends >= today)]
    insurance = Contractor.objects.filter(active=True, approved=True).filter(
        Q(insurance_expires__isnull=True) | Q(insurance_expires__lte=today + timedelta(days=30)))
    summary = workflow.summary(request.user, today)
    stats = [(summary["open"], _("open jobs"), reverse("maintenance:jobs"), False),
             (summary["past_target"], _("jobs past target"), reverse("maintenance:jobs") + "?when=past", True),
             (summary["statutory_overdue"], _("statutory tasks overdue"),
              reverse("maintenance:planned") + "?when=overdue&statutory=1", True),
             (summary["tasks_due_30"], _("planned tasks due in 30 days"), reverse("maintenance:planned") + "?when=30",
              False)]
    if summary["to_recharge"]:
        stats.append((summary["to_recharge"], _("completed jobs to recharge"),
                      reverse("maintenance:jobs") + "?status=completed&recharge=due", False))
    return render(request, "maintenance/home.html", {
        "section": "home", "summary": summary, "stats": stats, "urgent": urgent, "overdue": overdue,
        "soon": soon, "contracts": sorted(contracts, key=lambda c: c.retender_due), "insurance": insurance,
        "today": today, "can_raise": _can_raise(request.user),
        "to_approve": Job.objects.filter(approval_status="pending", approver=request.user),
    })


# ------------------------------------------------------------------ jobs

COLUMNS = {
    "ref": ("Job", ["year", "number"], False),
    "property": ("Property", ["property__reference", "number"], False),
    "priority": ("Priority", ["priority", "number"], False),
    "status": ("Status", ["status", "number"], False),
    "target": ("Target", ["target_date", "number"], False),
}


@method_decorator(maintenance_view, name="dispatch")
class JobListView(LoginRequiredMixin, ExportMixin, ListView):
    model = Job
    export_dataset, export_title = "jobs", "Maintenance jobs"
    paginate_by = 50
    template_name = "maintenance/job_list.html"

    def get_queryset(self):
        get, today = self.request.GET, date.today()
        qs = Job.objects.select_related("property", "contractor", "owner")
        status = get.get("status", "open")
        if status == "open":
            qs = qs.filter(status__in=Job.OPEN)
        elif status in Job.Status.values:
            qs = qs.filter(status=status)
        for key in ("priority", "responsibility", "category"):
            if get.get(key):
                qs = qs.filter(**{key: get[key]})
        if get.get("contractor", "").isdigit():
            qs = qs.filter(contractor_id=int(get["contractor"]))
        if get.get("owner") == "me":
            qs = qs.filter(owner=self.request.user)
        if get.get("when") == "past":
            qs = qs.filter(status__in=Job.OPEN, target_date__lt=today)
        if get.get("approval") == "mine":
            qs = qs.filter(approval_status="pending", approver=self.request.user)
        qs = places.apply(qs, get, self.request.user, "property")
        if get.get("recharge") == "due":
            qs = qs.filter(status="completed", responsibility=Responsibility.RECHARGE, recharge__isnull=True)
        q = get.get("q", "").strip()
        if q:
            number = q.upper().replace("JOB-", "").split("-")[-1]
            match = Q(title__icontains=q) | Q(property__reference__icontains=q) | Q(property__name__icontains=q) \
                | Q(contractor__name__icontains=q) | Q(po_number__icontains=q)
            if number.isdigit():
                match |= Q(number=int(number))
            qs = qs.filter(match)
        ordering, self.headings = sortable(self.request, COLUMNS, "-ref")
        return qs.order_by(*ordering)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        get = self.request.GET
        ctx.update({
            "section": "jobs", "q": get.get("q", ""), "headings": self.headings, "today": date.today(),
            "can_raise": _can_raise(self.request.user),
            "filters": [
                ("status", "Status", [("open", "Open"), *Job.Status.choices, ("all", "All")],
                 get.get("status", "open"), False),
                ("priority", "Priority", Job.Priority.choices, get.get("priority", ""), True),
                ("responsibility", "Who pays", Responsibility.choices, get.get("responsibility", ""), True),
                ("category", "Category", Category.choices, get.get("category", ""), True),
                ("contractor", "Contractor", [(str(c.pk), c.name) for c in Contractor.objects.all()],
                 get.get("contractor", ""), True),
                ("when", "Target", [("past", "Past target")], get.get("when", ""), True),
                ("owner", "Owner", [("me", "Mine")], get.get("owner", ""), True),
                ("approval", "Approval", [("mine", "Waiting for my approval")], get.get("approval", ""), True),
                ("recharge", "Recharge", [("due", "Completed, not yet recharged")], get.get("recharge", ""), True),
                *places.filters(get),
            ],
        })
        params = get.copy()
        params.pop("page", None)
        ctx["querystring"] = params.urlencode()
        return ctx


class JobForm(forms.Form):
    property = forms.ModelChoiceField(Property.objects.order_by("reference"), label="Property")
    title = forms.CharField(max_length=200, label="What needs doing",
                            help_text="For example: Roof leak above the reception desk")
    description = forms.CharField(widget=forms.Textarea(attrs={"rows": 4}), required=False, label="Details")
    category = forms.ChoiceField(choices=Category.choices, label="Category",
                                 help_text="Decides who pays, from the lease repairing terms.")
    priority = forms.ChoiceField(choices=Job.Priority.choices, initial=Job.Priority.ROUTINE, label="Priority")
    reported_by = forms.CharField(max_length=150, required=False, label="Reported by")
    how_reported = forms.ChoiceField(choices=Job.Reported.choices, label="How reported")
    reported_on = forms.DateField(initial=date.today, label="Date reported",
                                  widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["property"].label_from_instance = lambda p: f"{p.reference} – {p.name}"


@maintenance_view
def job_new(request):
    if not _can_raise(request.user):
        raise PermissionDenied
    initial = {"property": request.GET.get("property")}
    form = JobForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        job = workflow.open_job(d.pop("property"), d.pop("title"), user=request.user, **d)
        messages.success(request, _("Job %(ref)s raised. Who pays: %(who)s.")
                         % {"ref": job.reference, "who": job.get_responsibility_display()})
        return redirect(job)
    return render(request, "maintenance/job_new.html", {"form": form, "section": "jobs"})


ACTIONS = {"order_details", "request_approval", "issue_order", "complete", "close", "cancel", "reopen",
           "responsibility", "recharge", "service_charge", "add_document"}


@maintenance_view
def job_detail(request, pk):
    job = get_object_or_404(Job.objects.select_related("property", "contractor", "owner", "lease", "component",
                                                       "planned_task", "case", "recharge", "expenditure"), pk=pk)
    work = workflow.can_work(request.user, job)
    if request.method == "POST":
        action = request.POST.get("action", "")
        if action in ("approve", "return"):
            if not workflow.can_approve(request.user, job):
                raise PermissionDenied
            if action == "return" and not request.POST.get("comments", "").strip():
                messages.error(request, _("Say why you are returning it."))
            else:
                workflow.decide_order(job, request.user, action == "approve", request.POST.get("comments", ""))
                messages.success(request, _("Order approved.") if action == "approve" else _("Order returned."))
            return redirect(job)
        if action not in ACTIONS or not work:
            raise PermissionDenied
        _do(request, job, action)
        return redirect(job)
    years = list(workflow.service_charge_years(job)) if job.responsibility == Responsibility.SERVICE_CHARGE else []
    from apps.servicecharges.models import CostHeading

    modules = ModuleSettings.load()
    from apps.projects.rules import project_for

    return render(request, "maintenance/job_detail.html", {
        "job": job, "project": project_for(request.user, job), "can_work": work, "today": date.today(), "rag": job.rag(), "section": "jobs",
        "contractors": Contractor.objects.filter(active=True),
        "needs_approval": workflow.needs_order_approval(job), "limit": workflow.approval_limit(),
        "approver": supervisor_of(request.user), "can_approve": workflow.can_approve(request.user, job),
        "responsibilities": Responsibility.choices, "sc_years": years,
        "headings": CostHeading.objects.all() if years else [],
        "ledger_on": modules.rent_ledger_enabled, "sc_on": modules.service_charges_enabled,
        "suggested": responsibility.decide(job.property, job.category), "safety": _safety(job.property),
    })


def _do(request, job, action):
    post = request.POST
    if action == "order_details":
        contractor = Contractor.objects.filter(pk=post.get("contractor") or 0).first()
        estimate = _money(post.get("estimate", ""))
        if estimate != job.estimate and job.approval_status == "approved":
            job.approval_status = ""  # a changed estimate needs approving again
        job.contractor, job.estimate = contractor, estimate
        job.po_number = post.get("po_number", "").strip()[:40]
        job.save()
        if contractor and not contractor.insurance_ok():
            messages.warning(request, _("%(name)s's insurance has expired or is not recorded.") % {"name": contractor})
        messages.success(request, _("Order details saved."))
    elif action == "request_approval":
        try:
            workflow.request_order_approval(job, request.user)
            messages.success(request, _("Sent to %(name)s for approval.")
                             % {"name": job.approver.get_full_name() or job.approver.username})
        except ValueError as exc:
            messages.error(request, str(exc))
    elif action == "issue_order":
        try:
            emailed = workflow.issue_order(job, email_contractor=post.get("email") == "1")
            messages.success(request, _("Works order issued and emailed to the contractor.") if emailed
                             else _("Works order issued."))
        except ValueError as exc:
            messages.error(request, str(exc))
    elif action == "complete":
        workflow.complete(job, _date(post.get("date"), date.today()), _money(post.get("cost", "")),
                          post.get("notes", ""), post.get("invoice", ""))
        messages.success(request, _("Job completed."))
    elif action == "responsibility":
        if post.get("responsibility") in Responsibility.values:
            job.responsibility = post["responsibility"]
            job.responsibility_reason = post.get("reason", "").strip()[:200] or _("Changed by hand")
            job.save(update_fields=["responsibility", "responsibility_reason", "updated_at"])
    elif action == "recharge":
        if not ModuleSettings.load().rent_ledger_enabled:
            messages.error(request, _("Switch on the rent ledger to recharge tenants."))
        elif workflow.raise_recharge(job):
            messages.success(request, _("Recharge %(n)s added to the rent account.") % {"n": job.recharge.reference})
        else:
            messages.error(request, _("Record the final cost, and link the agreement, first."))
    elif action == "service_charge":
        from apps.servicecharges.models import CostHeading, ScheduleYear

        year = ScheduleYear.objects.filter(pk=post.get("year") or 0).first()
        heading = CostHeading.objects.filter(pk=post.get("heading") or 0).first()
        if year and heading and workflow.add_to_service_charge(job, year, heading):
            messages.success(request, _("Added to the %(year)s service charge.") % {"year": year})
        else:
            messages.error(request, _("Record the final cost and choose the year and heading."))
    elif action == "close":
        job.status = Job.Status.CLOSED
        job.save(update_fields=["status", "updated_at"])
    elif action == "cancel":
        job.status = Job.Status.CANCELLED
        job.save(update_fields=["status", "updated_at"])
    elif action == "reopen":
        job.status = Job.Status.ORDERED if job.ordered_on else Job.Status.REPORTED
        job.save(update_fields=["status", "updated_at"])
    elif action == "add_document":
        from django.core.exceptions import ValidationError

        from apps.cases.models import validate_case_file

        upload = request.FILES.get("file")
        if not upload:
            messages.error(request, _("Choose a file."))
            return
        try:
            validate_case_file(upload)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
            return
        JobDocument.objects.create(job=job, file=upload, original_filename=upload.name[:255],
                                   description=post.get("description", "").strip()[:200] or upload.name[:200])
        messages.success(request, _("Document added."))


def _safety(prop):
    from apps.compliance.safety import info

    return info(prop)


@maintenance_view
def works_order(request, pk):
    job = get_object_or_404(Job.objects.select_related("property", "contractor", "owner", "component"), pk=pk)
    return render(request, "maintenance/works_order.html", {"job": job, "settings": ModuleSettings.load()})


# ------------------------------------------------------------------ planned maintenance

@maintenance_view
def planned(request):
    today, get = date.today(), request.GET
    qs = PlannedTask.objects.filter(active=True).select_related("property", "contractor", "component")
    when = get.get("when", "")
    if when == "overdue":
        qs = qs.filter(next_due__lt=today)
    elif when.isdigit():
        qs = qs.filter(next_due__lte=today + timedelta(days=int(when)))
    if get.get("statutory") == "1":
        qs = qs.filter(statutory=True)
    if get.get("category"):
        qs = qs.filter(category=get["category"])
    qs = places.apply(qs, get, request.user, "property")
    fmt = get.get("format")
    if fmt in ("xlsx", "csv"):
        from apps.reports import datasets, export

        return export.download(request, "Planned maintenance", datasets.get("planned"), qs)
    return render(request, "maintenance/planned.html", {
        "section": "planned", "tasks": qs[:500], "today": today, "when": when, "statutory": get.get("statutory"),
        "category": get.get("category", ""), "categories": Category.choices, "can_act": _can_raise(request.user),
        "place_filters": places.filters(get), "count": qs.count(),
        "whens": [("overdue", _("Overdue")), ("30", _("Within 30 days")), ("90", _("Within 90 days")),
                  ("365", _("Within a year"))],
    })


@maintenance_view
@require_POST
def planned_action(request, pk):
    task = get_object_or_404(PlannedTask, pk=pk)
    if not can_edit(request.user, task):
        raise PermissionDenied
    action = request.POST.get("action")
    if action == "done":
        task.record_done(_date(request.POST.get("date"), date.today()))
        messages.success(request, _("Recorded. Next due %(d)s.") % {"d": task.next_due.strftime("%-d %b %Y")})
    elif action == "raise":
        job = workflow.raise_for_task(task, request.user)
        messages.success(request, _("Job %(ref)s raised.") % {"ref": job.reference})
        return redirect(job)
    return redirect(request.POST.get("next") or task.get_absolute_url())


# ------------------------------------------------------------------ a property's maintenance

@maintenance_view
def property_maintenance(request, pk):
    prop = get_object_or_404(Property, pk=pk)
    editable = can_edit(request.user, prop)
    if request.method == "POST":
        if not editable:
            raise PermissionDenied
        codes = request.POST.getlist("task")
        start = _date(request.POST.get("first_due"), date.today() + timedelta(days=30))
        contractor = Contractor.objects.filter(pk=request.POST.get("contractor") or 0).first()
        made = 0
        for code in codes:
            if code in library.BY_CODE and not prop.planned_tasks.filter(title=library.BY_CODE[code][1]).exists():
                _c, title, category, months, statutory, regulation = library.BY_CODE[code]
                PlannedTask.objects.create(property=prop, title=title, category=category, frequency_months=months,
                                           statutory=statutory, regulation=regulation, next_due=start,
                                           contractor=contractor)
                made += 1
        messages.success(request, _("%(n)s planned tasks added.") % {"n": made})
        return redirect("maintenance:property", pk=prop.pk)
    today = date.today()
    components = list(prop.components.all())
    have = set(prop.planned_tasks.values_list("title", flat=True))
    return render(request, "maintenance/property.html", {
        "property": prop, "editable": editable, "today": today, "components": components,
        "tasks": prop.planned_tasks.select_related("contractor").filter(active=True),
        "jobs": prop.jobs.select_related("contractor").order_by("-year", "-number")[:30],
        "matrix": responsibility.matrix(prop), "leases": responsibility.leases_for(prop),
        "library": [t for t in library.TASKS if t[1] not in have], "contractors": Contractor.objects.filter(active=True),
        "replace_soon": [c for c in components if c.replace_year and c.replace_year <= today.year + 5],
        "can_raise": _can_raise(request.user), "safety": _safety(prop),
    })


# ------------------------------------------------------------------ components and lifecycle

@maintenance_view
def components(request):
    qs = Component.objects.select_related("property")
    get = request.GET
    if get.get("category"):
        qs = qs.filter(category=get["category"])
    if get.get("condition"):
        qs = qs.filter(condition=get["condition"])
    qs = places.apply(qs, get, request.user, "property")
    if get.get("format") in ("xlsx", "csv"):
        from apps.reports import datasets, export

        return export.download(request, "Components", datasets.get("components"), qs)
    return render(request, "maintenance/components.html", {
        "section": "components", "components": qs[:1000], "count": qs.count(), "categories": Category.choices,
        "conditions": Component.Condition.choices, "category": get.get("category", ""),
        "condition": get.get("condition", ""), "year": date.today().year, "place_filters": places.filters(get),
    })



@maintenance_view
def forecast(request):
    """Lifecycle replacement forecast: when components fall due, and the cost by year."""
    this_year = date.today().year
    span = int(request.GET.get("years", "10")) if request.GET.get("years", "10") in ("5", "10", "20", "30") else 10
    years = list(range(this_year, this_year + span))
    by_year = defaultdict(lambda: {"capital": Decimal("0"), "revenue": Decimal("0"), "items": []})
    by_category = defaultdict(lambda: defaultdict(Decimal))
    for c in places.apply(Component.objects.select_related("property").exclude(replacement_cost__isnull=True),
                          request.GET, request.user, "property"):
        due = c.replace_year
        if due is None:
            continue
        due = max(due, this_year)  # overdue replacements fall in this year
        if due not in years:
            continue
        cost = Decimal(c.replacement_cost)
        by_year[due]["capital" if c.capital else "revenue"] += cost
        by_year[due]["items"].append(c)
        by_category[c.get_category_display()][due] += cost
    rows = [(y, by_year[y]["capital"], by_year[y]["revenue"], by_year[y]["items"]) for y in years]
    fmt = request.GET.get("format")
    if fmt in ("xlsx", "csv"):
        from collections import namedtuple

        Col = namedtuple("Col", "label type")
        cols = [Col("Category", "text")] + [Col(str(y), "money") for y in years] + [Col("Total", "money")]
        data = ([cat] + [vals[y] for y in years] + [sum(vals.values(), Decimal("0"))]
                for cat, vals in sorted(by_category.items()))
        title = f"Lifecycle forecast {years[0]} to {years[-1]}"
        return xlsx_response(title, cols, data, totals=True) if fmt == "xlsx" else csv_response(title, cols, data)
    return render(request, "maintenance/forecast.html", {
        "section": "forecast", "rows": rows, "span": span, "years": years, "place_filters": places.filters(request.GET),
        "query": request.GET.urlencode(),
        "total": sum((r[1] + r[2] for r in rows), Decimal("0")),
        "categories": [(cat, [vals[y] for y in years], sum(vals.values(), Decimal("0")))
                       for cat, vals in sorted(by_category.items())],
    })


# ------------------------------------------------------------------ contractors and contracts

@maintenance_view
def contractors(request):
    today = date.today()
    rows = Contractor.objects.filter(active=True).annotate(
        open_jobs=Sum("jobs__estimate", filter=Q(jobs__status__in=Job.OPEN)))
    return render(request, "maintenance/contractors.html", {"section": "contractors", "contractors": rows,
                                                             "today": today, "soon": today + timedelta(days=30)})


@maintenance_view
def contractor_detail(request, pk):
    contractor = get_object_or_404(Contractor, pk=pk)
    return render(request, "maintenance/contractor_detail.html", {
        "section": "contractors", "contractor": contractor, "today": date.today(),
        "jobs": contractor.jobs.select_related("property").order_by("-year", "-number")[:50],
        "contracts": contractor.contracts.all(),
        "spend": contractor.jobs.filter(completed_on__gte=date.today() - timedelta(days=365))
        .aggregate(t=Sum("actual_cost"))["t"],
    })


@maintenance_view
def contracts(request):
    today = date.today()
    rows = sorted(places.apply(Contract.objects.select_related("contractor").prefetch_related("properties"),
                               request.GET, request.user, "properties"), key=lambda c: c.retender_due)
    return render(request, "maintenance/contracts.html", {
        "section": "contracts", "contracts": rows, "today": today, "soon": today + timedelta(days=183),
        "place_filters": places.filters(request.GET)})
