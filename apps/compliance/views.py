# SPDX-License-Identifier: AGPL-3.0-or-later
"""Compliance register, a property's certificates and building information, and higher-risk screening."""
from datetime import date
from decimal import Decimal, InvalidOperation
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _

from apps.cases.models import validate_case_file
from apps.core import places
from apps.core.models import ModuleSettings
from apps.core.roles import can_edit
from apps.properties.models import Property

from . import rules, workflow
from .models import Action, BuildingDocument, BuildingSafety, Certificate, ComplianceType, Requirement


def compliance_view(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not ModuleSettings.load().compliance_enabled:
            return render(request, "compliance/off.html", status=404)
        return view(request, *args, **kwargs)

    return login_required(wrapped)


def _date(text, default=None):
    try:
        return date.fromisoformat(text or "")
    except ValueError:
        return default


@compliance_view
def home(request):
    today, get = date.today(), request.GET
    qs = workflow.requirements()
    if get.get("kind"):
        qs = qs.filter(kind__code=get["kind"])
    if get.get("responsible"):
        qs = qs.filter(responsible=get["responsible"])
    qs = places.apply(qs, get, request.user, "property")
    rows = workflow.statuses(qs, today)
    show = get.get("show", "problems")
    if show == "problems":
        rows = [r for r in rows if r[1][0] != "green"]
    if get.get("format") in ("xlsx", "csv"):
        from apps.reports import datasets, export

        ds = datasets.get("compliance")
        export_qs = ds.queryset().filter(pk__in=qs.values("pk")).order_by("property__reference", "kind__order")
        return export.download(request, "Compliance register", ds, export_qs)
    return render(request, "compliance/home.html", {
        "summary": workflow.summary(today, places.apply(workflow.requirements(), get, request.user, "property")), "rows": rows[:500], "show": show, "today": today,
        "kinds": ComplianceType.objects.filter(active=True), "kind": get.get("kind", ""),
        "responsible": get.get("responsible", ""), "responsibles": Requirement.Responsible.choices,
        "place_filters": places.filters(get), "filtered": bool(get.get("building") or get.get("surveyor")),
        "actions": places.apply(Action.objects.filter(done_on__isnull=True), get, request.user,
                                "certificate__requirement__property").select_related(
            "certificate__requirement__property", "certificate__requirement__kind", "job").order_by("due_on")[:30],
        "tier_a": BuildingSafety.objects.filter(tier="A").select_related("property"),
        "golden_thread": ModuleSettings.load().golden_thread_enabled,
    })


@compliance_view
def property_compliance(request, pk):
    prop = get_object_or_404(Property, pk=pk)
    editable = can_edit(request.user, prop)
    if request.method == "POST":
        if not editable:
            raise PermissionDenied
        _do(request, prop, request.POST.get("action", ""))
        return redirect(request.path + request.POST.get("anchor", ""))
    today = date.today()
    reqs = workflow.statuses(workflow.requirements(property=prop), today)
    reqs.sort(key=lambda r: r[0].kind.order)
    screening = BuildingSafety.objects.filter(property=prop).first()
    have = {r.kind_id for r, _s in reqs}
    from apps.maintenance.models import Contractor, Job

    docs = list(prop.building_documents.select_related("supersedes").order_by("category", "title", "-pk"))
    return render(request, "compliance/property.html", {
        "property": prop, "editable": editable, "today": today, "reqs": reqs,
        "kinds": ComplianceType.objects.filter(active=True).exclude(pk__in=have),
        "who": rules.responsible(prop), "results": Certificate.Result.choices, "priorities": Action.Priority.choices,
        "contractors": Contractor.objects.filter(active=True),
        "jobs": Job.objects.filter(property=prop).order_by("-year", "-number")[:20],
        "screening": screening, "suggested": rules.suggested_tier(prop, screening),
        "countries": BuildingSafety.Country.choices, "tiers": BuildingSafety.Tier.choices,
        "golden_thread": ModuleSettings.load().golden_thread_enabled,
        "maintenance_on": ModuleSettings.load().maintenance_enabled,
        "documents": [d for d in docs if d.is_current], "superseded": [d for d in docs if not d.is_current],
        "categories": BuildingDocument.Category.choices,
        "actions": Action.objects.filter(certificate__requirement__property=prop).select_related(
            "certificate__requirement__kind", "job").order_by("done_on", "due_on"),
    })


def _do(request, prop, action):
    post = request.POST
    if action == "add_requirements":
        kinds = ComplianceType.objects.filter(pk__in=post.getlist("kind"))
        made = workflow.add_requirements(prop, kinds)
        messages.success(request, _("%(n)s certificates added to this property's register.") % {"n": len(made)})
    elif action == "certificate":
        req = get_object_or_404(Requirement, pk=post.get("requirement"), property=prop)
        issued = _date(post.get("issued_on"))
        if issued is None:
            messages.error(request, _("Enter the date of the inspection or certificate."))
            return
        upload = request.FILES.get("file")
        if upload:
            try:
                validate_case_file(upload)
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
                return
        from apps.maintenance.models import Contractor, Job

        result = post.get("result") if post.get("result") in Certificate.Result.values else "ok"
        cert = workflow.record(
            req, issued, _date(post.get("expires_on")), upload, result=result,
            rating=post.get("rating", "").strip()[:10], carried_out_by=post.get("carried_out_by", "").strip()[:200],
            reference=post.get("reference", "").strip()[:60],
            contractor=Contractor.objects.filter(pk=post.get("contractor") or 0).first(),
            job=Job.objects.filter(pk=post.get("job") or 0, property=prop).first(),
            notes=post.get("notes", "").strip())
        for line in post.get("actions", "").splitlines():
            if line.strip():
                Action.objects.create(certificate=cert, description=line.strip()[:300],
                                      priority=post.get("priority", "medium"))
        messages.success(request, _("%(kind)s recorded, valid until %(d)s.")
                         % {"kind": req.kind.name, "d": cert.expires_on.strftime("%-d %B %Y")})
    elif action == "responsible":
        req = get_object_or_404(Requirement, pk=post.get("requirement"), property=prop)
        if post.get("responsible") in Requirement.Responsible.values:
            req.responsible = post["responsible"]
            req.responsible_reason = _("Changed by hand")
            req.save(update_fields=["responsible", "responsible_reason", "updated_at"])
    elif action == "remove_requirement":
        req = get_object_or_404(Requirement, pk=post.get("requirement"), property=prop)
        req.active = False
        req.save(update_fields=["active", "updated_at"])
        messages.success(request, _("%(kind)s no longer needed here. Its certificates are kept.") % {"kind": req.kind})
    elif action in ("action_done", "action_job"):
        item = get_object_or_404(Action, pk=post.get("item"), certificate__requirement__property=prop)
        if action == "action_done":
            item.done_on = _date(post.get("date"), date.today())
            item.save(update_fields=["done_on", "updated_at"])
        elif not item.job_id and ModuleSettings.load().maintenance_enabled:
            job = workflow.raise_job(item, request.user)
            messages.success(request, _("Job %(ref)s raised.") % {"ref": job.reference})
    elif action == "screening":
        s, _created = BuildingSafety.objects.get_or_create(property=prop)
        s.country = post.get("country") if post.get("country") in BuildingSafety.Country.values else "england"
        try:
            s.height_m = Decimal(post["height_m"]) if post.get("height_m", "").strip() else None
        except InvalidOperation:
            messages.error(request, _("Enter the height in metres, for example 18.5."))
            return
        s.storeys = int(post["storeys"]) if post.get("storeys", "").isdigit() else None
        s.residential_units = int(post["residential_units"]) if post.get("residential_units", "").isdigit() else 0
        s.accountable_person = post.get("accountable_person", "").strip()[:200]
        s.responsible_person = post.get("responsible_person", "").strip()[:200]
        s.notes = post.get("notes", "").strip()
        tier = post.get("tier", "")
        if tier in BuildingSafety.Tier.values:
            if tier != s.tier or not s.confirmed_on:
                s.confirmed_by, s.confirmed_on = request.user, date.today()
            s.tier = tier
        s.save()
        suggested = rules.suggested_tier(prop, s)
        messages.success(request, _("Screening saved. Suggested tier %(t)s: %(why)s.") % {"t": suggested[0],
                                                                                          "why": suggested[1]})
    elif action == "document":
        upload = request.FILES.get("file")
        if not upload:
            messages.error(request, _("Choose a file."))
            return
        try:
            validate_case_file(upload)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
            return
        old = BuildingDocument.objects.filter(pk=post.get("supersedes") or 0, property=prop).first()
        category = post.get("category") if post.get("category") in BuildingDocument.Category.values else "other"
        BuildingDocument.objects.create(
            property=prop, category=old.category if old else category,
            title=(post.get("title", "").strip() or (old.title if old else upload.name))[:200],
            document_date=_date(post.get("document_date")), file=upload, original_filename=upload.name[:255],
            supersedes=old, notes=post.get("notes", "").strip())
        messages.success(request, _("New version saved; the old one is kept.") if old else _("Document saved."))


