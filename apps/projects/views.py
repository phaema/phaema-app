# SPDX-License-Identifier: AGPL-3.0-or-later
"""Project pages: the list, starting and editing a project, and the project page where the work happens."""
import mimetypes
from datetime import date
from decimal import Decimal, InvalidOperation

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.generic import ListView

from apps.core.access import can_use
from apps.core.roles import ADMINISTRATORS, CONTRIBUTORS, SURVEYORS, is_administrator
from apps.core.tables import sortable
from apps.leases.forms import GovukMixin
from apps.leases.models import Party
from apps.properties.models import Property
from apps.properties.views import map_config
from apps.reports.mixins import ExportMixin

from . import budget, completion, rules, workflow
from .models import (GATEWAYS, PHASE_ORDER, BudgetLine, BudgetYear, CompletionStep, GatewayDecision, Milestone,
                     Phase, Project, ProjectAccess, ProjectDocument, ProjectMember, ProjectNote, ProjectParty, ProjectProperty,
                     ProjectTask, ProjectType, Risk, financial_year_label, financial_year_of)

User = get_user_model()

COLUMNS = {
    "ref": ("Project", ["year", "number"], False),
    "type": ("Type", ["project_type__name", "number"], False),
    "phase": ("Phase", ["phase", "number"], False),
    "lead": ("Lead", ["lead__first_name", "lead__username", "number"], False),
    "target": ("Target", ["target_date", "number"], False),
}


def _people(*roles):
    return (User.objects.filter(is_active=True).filter(Q(groups__name__in=roles) | Q(is_superuser=True))
            .distinct().order_by("first_name", "last_name", "username"))


def _date(text):
    try:
        return date.fromisoformat(text) if text else None
    except ValueError:
        return None


class ProjectListView(LoginRequiredMixin, ExportMixin, ListView):
    model = Project
    export_dataset, export_title = "projects", "Projects"
    paginate_by = 50
    template_name = "projects/project_list.html"

    def get_queryset(self):
        get = self.request.GET
        qs = rules.visible(self.request.user, Project.objects.select_related("project_type", "lead"))
        status = get.get("status", "open")
        if status == "open":
            qs = qs.filter(status__in=(Project.Status.ACTIVE, Project.Status.PAUSED))
        elif status in Project.Status.values:
            qs = qs.filter(status=status)
        if get.get("type"):
            qs = qs.filter(project_type__code=get["type"])
        if get.get("phase") in PHASE_ORDER:
            qs = qs.filter(phase=get["phase"])
        who = get.get("lead", "")
        if who == "me":
            qs = qs.filter(Q(lead=self.request.user) | Q(members__user=self.request.user)).distinct()
        elif who.isdigit():
            qs = qs.filter(lead_id=int(who))
        building = get.get("building", "")
        if building.isdigit():
            from apps.core import places

            qs = qs.filter(property_links__property__in=places.subtree(int(building))).distinct()
        q = get.get("q", "").strip()
        if q:
            number = q.upper().replace("PRJ-", "").split("-")[-1]
            match = Q(name__icontains=q) | Q(description__icontains=q) | Q(site_address__icontains=q)
            if number.isdigit():
                match |= Q(number=int(number))
            qs = qs.filter(match)
        ordering, self.headings = sortable(self.request, COLUMNS, "-ref")
        return qs.order_by(*ordering).prefetch_related("milestones")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        get = self.request.GET
        from apps.core import places

        ctx.update({
            "q": get.get("q", ""), "headings": self.headings, "today": date.today(),
            "filters": [
                ("status", _("Status"), [("open", _("Active or paused")), ("closed", _("Closed")),
                                         ("stopped", _("Stopped")), ("all", _("All"))], get.get("status", "open"), False),
                ("type", _("Type"), [(t.code, t.name) for t in ProjectType.objects.filter(active=True)],
                 get.get("type", ""), True),
                ("phase", _("Phase"), Phase.choices, get.get("phase", ""), True),
                ("lead", _("Lead"), [("me", _("Mine"))] + [(str(u.pk), u.get_full_name() or u.username)
                                                           for u in _people(ADMINISTRATORS, SURVEYORS)],
                 get.get("lead", ""), True),
                ("building", _("Estate, site or building"), [(str(b.pk), f"{b.reference} {b.name}")
                                                             for b in places.buildings()], get.get("building", ""), True),
            ],
            "can_create": rules.can_create(self.request.user),
        })
        params = get.copy()
        params.pop("page", None)
        ctx["querystring"] = params.urlencode()
        return ctx


class ProjectForm(GovukMixin, forms.ModelForm):
    class Meta:
        model = Project
        fields = ["name", "project_type", "description", "lead", "sponsor", "start_date", "target_date",
                  "confidential", "parent", "site_address", "site_title_number", "vendor"]
        widgets = {"start_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
                   "target_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
                   "description": forms.Textarea(attrs={"rows": 4}), "site_address": forms.Textarea(attrs={"rows": 3})}
        help_texts = {"site_address": _("For an acquisition, or a site not yet in the property register."),
                      "lead": _("Usually a surveyor. The lead and the team can work on the project.")}

    def __init__(self, *args, user=None, new=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["project_type"].queryset = ProjectType.objects.filter(active=True)
        self.fields["lead"].queryset = _people(ADMINISTRATORS, SURVEYORS)
        self.fields["lead"].label_from_instance = lambda u: u.get_full_name() or u.username
        parents = rules.visible(user, Project.objects.all()) if user else Project.objects.none()
        if self.instance.pk:
            parents = parents.exclude(pk=self.instance.pk)
        self.fields["parent"].queryset = parents
        self.fields["vendor"].queryset = Party.objects.order_by("name")
        for name in ("name", "sponsor", "site_title_number"):
            self.fields[name].widget.attrs["class"] = "govuk-input"
        self.fields["confidential"] = forms.TypedChoiceField(
            label=_("Confidential"), choices=[(True, _("Yes: only the team and administrators")), (False, _("No"))],
            coerce=lambda v: v in (True, "True"), widget=forms.RadioSelect, initial=self.instance.confidential,
            help_text=_("Acquisitions always start confidential.") if new else
            _("A confidential project, its site and its papers are hidden from everyone outside the team."))


def _form_page(request, form, project=None):
    return render(request, "projects/project_form.html", {"form": form, "project": project})


@login_required
def project_new(request):
    if not rules.can_create(request.user):
        raise PermissionDenied
    if request.method == "POST":
        form = ProjectForm(request.POST, user=request.user, new=True)
        if form.is_valid():
            project = form.save(commit=False)
            if project.project_type.confidential_by_default:
                project.confidential = True
            if project.lead is None:
                project.lead = request.user
            workflow.start(project, request.user)
            messages.success(request, _("Project %(ref)s started.") % {"ref": project.display_reference})
            return redirect(project)
    else:
        form = ProjectForm(user=request.user, new=True, initial={"lead": request.user, "start_date": date.today()})
    return _form_page(request, form)


@login_required
def project_edit(request, pk):
    project = _project(request, pk)
    if not rules.can_manage(request.user, project):
        raise PermissionDenied
    form = ProjectForm(request.POST or None, instance=project, user=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Project details saved."))
        return redirect(project)
    return _form_page(request, form, project)


def _project(request, pk, what=None):
    project = get_object_or_404(Project.objects.select_related("project_type", "lead", "parent", "vendor"), pk=pk)
    if not rules.can_see(request.user, project):
        raise Http404  # a confidential project's existence is not revealed
    if project.confidential and what:
        ProjectAccess.objects.create(project=project, user=request.user, what=what[:100])
    return project


@login_required
def project_detail(request, pk):
    project = _project(request, pk, what="project page" if request.method == "GET" else None)
    can_manage = rules.can_manage(request.user, project)
    can_contribute = rules.can_contribute(request.user, project)
    can_budget = rules.can_edit_budget(request.user, project)
    if request.method == "POST":
        return _act(request, project, can_manage, can_contribute, can_budget)
    today = date.today()
    tasks = list(project.tasks.select_related("owner", "done_by"))
    phases = [(p, project.phase_label(p), [t for t in tasks if t.phase == p]) for p in PHASE_ORDER]
    gateway = project.next_gateway()
    return render(request, "projects/project_detail.html", {
        "project": project, "today": today, "rag": project.rag(today), "phases": phases,
        "can_manage": can_manage, "can_contribute": can_contribute,
        "decisions": project.gateway_decisions.all(),
        "next_gateway": (gateway, GATEWAYS[gateway][2], GATEWAYS[gateway][3]) if gateway and project.is_open else None,
        "gateways": [(n, g[2]) for n, g in GATEWAYS.items()],
        "makers": GatewayDecision.Maker.choices, "outcomes": GatewayDecision.Outcome.choices,
        "milestones": project.milestones.all(),
        "property_links": project.property_links.select_related("property"),
        "parts": ProjectProperty.Part.choices,
        "members": project.members.select_related("user"), "member_roles": ProjectMember.Role.choices,
        "party_links": project.party_links.select_related("party"),
        "notes": project.notes.select_related("created_by")[:50],
        "documents": project.documents.select_related("created_by"),
        "phase_choices": [(p, project.phase_label(p)) for p in PHASE_ORDER],
        "people": _people(ADMINISTRATORS, SURVEYORS, CONTRIBUTORS) if can_manage else [],
        "properties": Property.objects.order_by("reference").only("pk", "reference", "name") if can_manage else [],
        "parties": Party.objects.order_by("name").only("pk", "name") if can_manage else [],
        "children": rules.visible(request.user, project.phases.all()),
        "statuses": [(Project.Status.ACTIVE, _("Active")), (Project.Status.PAUSED, _("Paused")),
                     (Project.Status.STOPPED, _("Stopped"))],
        "budget": budget.summary(project) if rules.can_see_budget(request.user, project) else None,
        "can_budget": can_budget, "categories": BudgetLine.Category.choices, "fundings": BudgetLine.Funding.choices,
        "budget_years": _year_choices(project),
        "risks": sorted(project.risks.select_related("owner"), key=lambda r: (r.status != "open", -r.score, r.pk)),
        "scale": Risk.SCALE,
        "linked_cases": project.cases.select_related("case_type").order_by("-year", "-number"),
        "linked_jobs": project.jobs.select_related("property").order_by("-pk") if can_use(request.user, "maintenance") else None,
        "linked_valuations": project.valuations.select_related("property").order_by("-valuation_date")
        if can_use(request.user, "valuations") else None,
        "valuation_choices": _valuation_choices(project) if can_manage and can_use(request.user, "valuations") else [],
        "completion": completion.steps(project, request.user) if completion.shown(project) else None,
        "has_map": bool(project.site_boundary) or project.property_links.filter(
            Q(property__boundary__isnull=False) | Q(property__easting__isnull=False)).exists(),
        "map_config": map_config(),
        "access_log": project.access_log.select_related("user")[:20]
        if project.confidential and (is_administrator(request.user) or project.lead_id == request.user.pk) else None,
    })


def _valuation_choices(project):
    from apps.valuations.models import Valuation

    ids = set()
    for link in project.property_links.select_related("property"):
        ids.add(link.property_id)
        ids.update(link.property._descendant_ids())
    return Valuation.objects.filter(property__in=ids, project__isnull=True).select_related("property")[:100]


def _year_choices(project):
    """Financial years a budget can be entered for: from the project's start to five years after its target."""
    start = financial_year_of(project.start_date or date.today())
    end = financial_year_of(project.target_date) if project.target_date else start + 4
    end = max(end, financial_year_of(date.today())) + 1
    return [(y, financial_year_label(y)) for y in range(start, min(end, start + 15) + 1)]


MANAGE = {"add_property", "remove_property", "add_member", "remove_member", "add_party", "remove_party",
          "add_milestone", "update_milestone", "add_task", "task_done", "record_gateway", "set_status",
          "add_risk", "update_risk", "link", "unlink", "complete_step", "site_from_inspire"}
CONTRIBUTE = {"add_note", "add_document"}
BUDGET = {"add_budget_line", "set_budget", "remove_budget_line"}


def _act(request, project, can_manage, can_contribute, can_budget=False):
    post, action = request.POST, request.POST.get("action", "")
    if action in MANAGE and not can_manage:
        raise PermissionDenied
    if action in CONTRIBUTE and not can_contribute:
        raise PermissionDenied
    if action in BUDGET and not can_budget:
        raise PermissionDenied
    if action not in MANAGE | CONTRIBUTE | BUDGET:
        raise Http404
    try:
        message = _do(request, project, action, post)
    except (ValueError, ValidationError) as exc:
        text = "; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
        messages.error(request, text)
    else:
        if message:
            messages.success(request, message)
    return redirect(project)


def _do(request, project, action, post):
    if action == "add_property":
        prop = Property.objects.filter(pk=post.get("property")).first()
        if prop is None:
            raise ValueError(_("Choose a property."))
        part = post.get("part") if post.get("part") in ProjectProperty.Part.values else ProjectProperty.Part.IN_SCOPE
        ProjectProperty.objects.update_or_create(project=project, property=prop,
                                                 defaults={"part": part, "notes": post.get("notes", "")[:200]})
        return _("%(ref)s added to the project.") % {"ref": prop.reference}
    if action == "remove_property":
        ProjectProperty.objects.filter(project=project, pk=post.get("link")).delete()
        return _("Property removed from the project.")
    if action == "add_member":
        user = _people(ADMINISTRATORS, SURVEYORS, CONTRIBUTORS).filter(pk=post.get("user")).first()
        if user is None:
            raise ValueError(_("Choose a person."))
        role = post.get("role") if post.get("role") in ProjectMember.Role.values else ProjectMember.Role.MEMBER
        ProjectMember.objects.update_or_create(project=project, user=user, defaults={"role": role})
        return _("%(name)s added to the team.") % {"name": user.get_full_name() or user.username}
    if action == "remove_member":
        ProjectMember.objects.filter(project=project, pk=post.get("member")).delete()
        return _("Removed from the team.")
    if action == "add_party":
        party = Party.objects.filter(pk=post.get("party")).first()
        if party is None or not post.get("role", "").strip():
            raise ValueError(_("Choose a party and give their role."))
        ProjectParty.objects.create(project=project, party=party, role=post["role"].strip()[:60])
        return _("%(name)s added.") % {"name": party.name}
    if action == "remove_party":
        ProjectParty.objects.filter(project=project, pk=post.get("link")).delete()
        return _("Removed.")
    if action == "add_milestone":
        name = post.get("name", "").strip()
        if not name:
            raise ValueError(_("Name the milestone."))
        Milestone.objects.create(project=project, name=name[:150], target_date=_date(post.get("target")),
                                 forecast_date=_date(post.get("forecast")),
                                 order=project.milestones.count())
        return _("Milestone added.")
    if action == "update_milestone":
        milestone = get_object_or_404(Milestone, project=project, pk=post.get("milestone"))
        milestone.forecast_date = _date(post.get("forecast"))
        milestone.actual_date = _date(post.get("actual"))
        milestone.save()
        return _("Milestone updated.")
    if action == "add_task":
        text = post.get("description", "").strip()
        if not text:
            raise ValueError(_("Describe the task."))
        owner = _people(ADMINISTRATORS, SURVEYORS, CONTRIBUTORS).filter(pk=post.get("owner")).first()
        ProjectTask.objects.create(project=project, description=text[:200], owner=owner,
                                   phase=post.get("phase") if post.get("phase") in PHASE_ORDER else project.phase,
                                   due_date=_date(post.get("due")))
        return _("Task added.")
    if action == "task_done":
        task = get_object_or_404(ProjectTask, project=project, pk=post.get("task"))
        if task.done_on:
            task.done_on, task.done_by = None, None
        else:
            task.done_on, task.done_by = date.today(), request.user
        task.save()
        return None
    if action == "record_gateway":
        number = int(post.get("number", "0") or 0)
        workflow.record_gateway(project, number, decision_maker=post.get("decision_maker", ""),
                                decided_on=_date(post.get("decided_on")), outcome=post.get("outcome", ""),
                                reference=post.get("reference", "").strip()[:100], notes=post.get("notes", "").strip(),
                                report=request.FILES.get("report"), user=request.user)
        project.refresh_from_db()
        return _("Gateway %(n)s recorded. The project is now in %(phase)s.") % {
            "n": number, "phase": project.phase_label()} if project.is_open else _("Gateway %(n)s recorded.") % {"n": number}
    if action == "set_status":
        workflow.set_status(project, post.get("status", ""), post.get("reason", ""))
        return _("Project %(status)s.") % {"status": project.get_status_display().lower()}
    if action == "add_budget_line":
        description = post.get("description", "").strip()
        if not description or post.get("category") not in BudgetLine.Category.values:
            raise ValueError(_("Choose a category and describe the budget line."))
        BudgetLine.objects.create(project=project, category=post["category"], description=description[:150],
                                  funding=post.get("funding") if post.get("funding") in BudgetLine.Funding.values
                                  else BudgetLine.Funding.CAPITAL, order=project.budget_lines.count())
        return _("Budget line added.")
    if action == "remove_budget_line":
        line = get_object_or_404(BudgetLine, project=project, pk=post.get("line"))
        if line.years.exclude(actual=0).exists():
            raise ValueError(_("This line has actual spending recorded, so it cannot be removed."))
        line.delete()
        return _("Budget line removed.")
    if action == "set_budget":
        line = get_object_or_404(BudgetLine, project=project, pk=post.get("line"))
        year = int(post.get("year", "0") or 0)
        if year not in dict(_year_choices(project)):
            raise ValueError(_("Choose a financial year."))
        values = {}
        for name in ("approved", "forecast", "actual"):
            raw = post.get(name, "").replace(",", "").replace("£", "").strip()
            try:
                values[name] = Decimal(raw) if raw else Decimal("0")
            except InvalidOperation:
                raise ValueError(_("Enter amounts in pounds, for example 125000."))
        BudgetYear.objects.update_or_create(line=line, year=year, defaults=values)
        return _("%(line)s, %(year)s saved.") % {"line": line.description, "year": financial_year_label(year)}
    if action == "add_risk":
        description = post.get("description", "").strip()
        if not description:
            raise ValueError(_("Describe the risk."))
        def score(name):
            value = post.get(name, "3")
            return int(value) if value in "12345" and len(value) == 1 else 3
        owner = _people(ADMINISTRATORS, SURVEYORS, CONTRIBUTORS).filter(pk=post.get("owner")).first()
        Risk.objects.create(project=project, description=description[:300], likelihood=score("likelihood"),
                            impact=score("impact"), owner=owner, mitigation=post.get("mitigation", "").strip())
        return _("Risk added.")
    if action == "update_risk":
        risk = get_object_or_404(Risk, project=project, pk=post.get("risk"))
        risk.status = Risk.Status.CLOSED if risk.status == Risk.Status.OPEN else Risk.Status.OPEN
        risk.save()
        return _("Risk closed.") if risk.status == Risk.Status.CLOSED else _("Risk reopened.")
    if action == "link":
        return _link(request, project, post.get("kind", ""), post.get("reference", "").strip(), True)
    if action == "unlink":
        return _link(request, project, post.get("kind", ""), post.get("id", ""), False)
    if action == "complete_step":
        key = post.get("key", "")
        if key not in {s.key for s in completion.steps(project, request.user) if not s.automatic}:
            raise Http404
        done = CompletionStep.objects.filter(project=project, key=key)
        if done.exists():
            done.delete()
        else:
            CompletionStep.objects.create(project=project, key=key, done_by=request.user)
        return None
    if action == "site_from_inspire":
        from django.contrib.gis.geos import MultiPolygon

        from apps.properties.models import InspireParcel

        ids = [i.strip() for i in post.get("parcels", "").replace(";", ",").split(",") if i.strip()]
        parcels = list(InspireParcel.objects.filter(inspire_id__in=ids))
        missing = sorted(set(ids) - {p.inspire_id for p in parcels})
        if not ids:
            raise ValueError(_("Enter one or more INSPIRE parcel IDs."))
        if missing:
            raise ValueError(_("These INSPIRE parcels are not in PHAEMA: %(ids)s.") % {"ids": ", ".join(missing)})
        union = parcels[0].geometry
        for parcel in parcels[1:]:
            union = union.union(parcel.geometry)
        project.site_boundary = union if union.geom_type == "MultiPolygon" else MultiPolygon(union, srid=27700)
        project.save()
        return _("Proposed site drawn from %(n)s INSPIRE parcel(s).") % {"n": len(parcels)}
    if action == "add_note":
        text = post.get("text", "").strip()
        if not text:
            raise ValueError(_("Write the note."))
        ProjectNote.objects.create(project=project, text=text)
        return _("Note added.")
    if action == "add_document":
        upload = request.FILES.get("file")
        if not upload:
            raise ValueError(_("Choose a file."))
        doc = ProjectDocument(project=project, title=(post.get("title", "").strip() or upload.name)[:200], file=upload)
        doc.full_clean()
        doc.save()
        return _("Document added.")
    raise Http404


def _link(request, project, kind, value, add):
    """Link (or unlink) a case, maintenance job or valuation to the project, by its reference or number."""
    from apps.cases.models import Case

    if kind == "case":
        model, label = Case, _("Case")
        if add:
            text = value.upper().replace("CAS-", "")
            parts = text.split("-")
            if len(parts) != 2 or not all(p.isdigit() for p in parts):
                raise ValueError(_("Enter the case reference, for example CAS-2026-0012."))
            item = Case.objects.filter(year=int(parts[0]), number=int(parts[1])).first()
    elif kind in ("job", "valuation"):
        module = "maintenance" if kind == "job" else "valuations"
        if not can_use(request.user, module):
            raise PermissionDenied
        if kind == "job":
            from apps.maintenance.models import Job as model

            label = _("Job")
        else:
            from apps.valuations.models import Valuation as model

            label = _("Valuation")
        if add:
            item = None
            if kind == "job":
                text = value.upper().replace("JOB-", "")
                parts = text.split("-")
                if len(parts) == 2 and all(p.isdigit() for p in parts):
                    item = model.objects.filter(year=int(parts[0]), number=int(parts[1])).first()
            elif value.isdigit():
                item = model.objects.filter(pk=int(value)).first()
    else:
        raise Http404
    if not add:
        model.objects.filter(pk=value if str(value).isdigit() else 0, project=project).update(project=None)
        return _("%(what)s unlinked.") % {"what": label}
    if item is None:
        raise ValueError(_("No %(what)s with that reference.") % {"what": str(label).lower()})
    item.project = project
    item.save(update_fields=["project"])
    return _("%(what)s linked to the project.") % {"what": label}


@login_required
def project_geojson(request, pk):
    """The project's properties and proposed site, for its map (WGS 84). Only for people who can see the project."""
    import json

    from django.contrib.gis.db.models.functions import AsGeoJSON, Transform
    from django.http import JsonResponse

    from apps.properties.views import _features

    project = _project(request, pk)
    parts = {link.property_id: link.get_part_display() for link in project.property_links.all()}
    data = _features(Property.objects.filter(pk__in=parts), lambda p: "part")
    if project.site_boundary:
        gj = Project.objects.filter(pk=project.pk).annotate(
            gj=AsGeoJSON(Transform("site_boundary", 4326), precision=7)).values_list("gj", flat=True).first()
        data["features"].insert(0, {"type": "Feature", "geometry": json.loads(gj), "properties": {
            "reference": project.display_reference, "name": _("Proposed site"), "type": project.project_type.name,
            "occupation": "", "occupationLabel": "", "url": project.get_absolute_url(), "role": "self"}})
    return JsonResponse(data)


@login_required
def project_file(request, pk, kind, item):
    """Serve a project document or gateway report to people who can see the project (not through /files/, so a
    confidential project's papers stay with its team)."""
    project = _project(request, pk, what=f"{kind} {item}")
    if kind == "document":
        field = get_object_or_404(ProjectDocument, project=project, pk=item).file
    elif kind == "report":
        field = get_object_or_404(GatewayDecision, project=project, pk=item).report
    else:
        raise Http404
    if not field:
        raise Http404
    content_type = mimetypes.guess_type(field.name)[0] or "application/octet-stream"
    inline = content_type in ("application/pdf", "image/jpeg", "image/png")
    response = FileResponse(field.open("rb"), content_type=content_type, as_attachment=not inline,
                            filename=field.name.rsplit("/", 1)[-1])
    response["Cache-Control"] = "private, max-age=0, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response

