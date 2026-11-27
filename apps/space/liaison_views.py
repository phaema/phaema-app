# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pages for occupier contacts (/occupier/): their department's buildings, and recording headcount."""
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _

from . import liaison, summary
from .models import Headcount


def _contact_only(view):
    """Signed in and named on an occupier, with the space module on; anyone else gets 404."""

    @login_required
    def wrapped(request, *args, **kwargs):
        if not liaison.is_contact(request.user):
            raise Http404
        return view(request, *args, **kwargs)

    wrapped.__name__ = view.__name__
    return wrapped


@_contact_only
def home(request):
    mine = liaison.occupiers_for(request.user)
    editable = liaison.editable_for(request.user)
    rows = []
    for building in liaison.buildings_for(request.user):
        held = [h for h in summary.holdings(building) if h.occupier.pk in {o.pk for o in mine}]
        rows.append({"building": building, "holdings": held,
                     "people": sum(h.people or 0 for h in held),
                     "capacity": sum(h.capacity for h in held)})
    return render(request, "space/liaison_home.html", {
        "named": liaison.named_on(request.user), "rows": rows, "can_record": bool(editable)})


@_contact_only
def building(request, pk):
    prop = get_object_or_404(liaison.buildings_for(request.user), pk=pk)
    mine = {o.pk for o in liaison.occupiers_for(request.user)}
    editable = liaison.editable_for(request.user)
    held = summary.holdings(prop)
    own = [h for h in held if h.occupier.pk in mine]
    recordable = [h.occupier for h in own if h.occupier.pk in editable]
    if request.method == "POST":
        return _record_headcount(request, prop, recordable)
    from apps.maintenance.reports import enabled as repairs_on

    ctx = {
        "object": prop, "rows": summary.stacking(prop), "holdings": own, "recordable": recordable,
        "surveyor": prop.managing_surveyor, "today": date.today(),
        "history": Headcount.objects.filter(building=prop, occupier_id__in=mine).select_related("occupier")[:10],
    }
    from apps.cases import requests as asks

    ctx["can_ask"] = bool(recordable) and asks.department_types().exists()
    ctx["requests"] = list(asks.department_cases(request.user).filter(property__in=_building_parts(prop))[:20])
    ctx["request_url"] = "occupier:request"
    if repairs_on():
        from apps.maintenance.models import RepairReport

        ctx["can_report"] = bool(recordable)
        ctx["repairs"] = list(RepairReport.objects.filter(occupier_id__in=mine, property__in=_building_parts(prop))
                              .select_related("job").order_by("-created_at")[:20])
    return render(request, "space/liaison_building.html", ctx)


def _building_parts(prop):
    from apps.properties.models import Property

    return Property.objects.filter(pk__in=[prop.pk, *prop._descendant_ids()]).order_by("reference")


@_contact_only
def repair(request, pk):
    """A property liaison reports a repair at one of their department's buildings, into the triage queue."""
    from apps.maintenance import reports

    if not reports.enabled():
        raise Http404
    prop = get_object_or_404(liaison.buildings_for(request.user), pk=pk)
    mine = {o.pk for o in liaison.occupiers_for(request.user)}
    editable = liaison.editable_for(request.user)
    recordable = [h.occupier for h in summary.holdings(prop) if h.occupier.pk in mine and h.occupier.pk in editable]
    if not recordable:
        raise Http404
    form = reports.RepairForm(request.POST or None, request.FILES or None, properties=_building_parts(prop))
    if request.method == "POST" and form.is_valid():
        occupier = next((o for o in recordable if str(o.pk) == request.POST.get("occupier")), recordable[0])
        report = reports.submit(form, source="department", occupier=occupier, user=request.user,
                                reporter_name=request.user.get_full_name() or request.user.username)
        messages.success(request, _("Repair reported. Your reference is %(ref)s.") % {"ref": report.reference})
        return redirect("occupier:building", pk=prop.pk)
    return render(request, "space/liaison_repair.html", {"object": prop, "form": form, "occupiers": recordable})


def _record_headcount(request, prop, recordable):
    occupier = next((o for o in recordable if str(o.pk) == request.POST.get("occupier")), None)
    if occupier is None:
        raise Http404
    errors = []
    try:
        people = int(request.POST.get("people", ""))
        if people < 0:
            raise ValueError
    except ValueError:
        errors.append(_("Enter the number of people based here, as a whole number."))
        people = None
    fte = request.POST.get("fte", "").strip()
    try:
        fte = round(float(fte), 1) if fte else None
        if fte is not None and fte < 0:
            raise ValueError
    except ValueError:
        errors.append(_("Enter the full-time equivalent as a number, such as 42.5, or leave it blank."))
    try:
        counted_on = date.fromisoformat(request.POST.get("counted_on") or date.today().isoformat())
        if counted_on > date.today():
            errors.append(_("The date cannot be in the future."))
    except ValueError:
        errors.append(_("Enter the date as day, month and year."))
        counted_on = date.today()
    if errors:
        for error in errors:
            messages.error(request, error)
        return redirect("occupier:building", pk=prop.pk)
    name = request.user.get_full_name() or request.user.get_username()
    Headcount.objects.update_or_create(
        building=prop, occupier=occupier, counted_on=counted_on,
        defaults={"people": people, "fte": fte, "source": _("Entered by %(name)s for %(occupier)s")
                  % {"name": name, "occupier": occupier.name},
                  "from_department": True, "checked_by": None, "checked_on": None})
    messages.success(request, _("Headcount recorded. %(surveyor)s will check it.") % {
        "surveyor": (prop.managing_surveyor.get_full_name() if prop.managing_surveyor else "") or _("The estates team")})
    return redirect("occupier:building", pk=prop.pk)


def to_check(user):
    """Headcounts entered by departments, not yet checked, for buildings this surveyor manages."""
    return (Headcount.objects.filter(from_department=True, checked_on__isnull=True, building__managing_surveyor=user)
            .select_related("building", "occupier"))


@login_required
def check(request, pk):
    """The managing surveyor (or an administrator) looks at a department's headcount and marks it checked.
    Works without the space module's access area, since the surveyor of the building is the one who checks."""
    from apps.core.access import can_use
    from apps.core.roles import is_administrator

    item = get_object_or_404(Headcount.objects.select_related("building", "occupier", "created_by"), pk=pk,
                             from_department=True)
    if not (is_administrator(request.user) or item.building.managing_surveyor_id == request.user.pk):
        raise Http404
    if request.method == "POST":
        item.checked_by, item.checked_on = request.user, date.today()
        item.save(update_fields=["checked_by", "checked_on", "updated_at"])
        messages.success(request, _("Headcount marked as checked."))
        if can_use(request.user, "space"):
            return redirect("space:building", pk=item.building_id)
        return redirect(item.building.get_absolute_url())
    earlier = (Headcount.objects.filter(building=item.building, occupier=item.occupier, counted_on__lt=item.counted_on)
               .order_by("-counted_on").first())
    return render(request, "space/headcount_check.html", {
        "item": item, "earlier": earlier, "can_open_space": can_use(request.user, "space")})


def _recordable(user, prop):
    mine = {o.pk for o in liaison.occupiers_for(user)}
    editable = liaison.editable_for(user)
    return [h.occupier for h in summary.holdings(prop) if h.occupier.pk in mine and h.occupier.pk in editable]


@_contact_only
def request_new(request, pk):
    """A property liaison asks the estates team for something that opens a case, such as a space request."""
    from apps.cases import requests as asks

    prop = get_object_or_404(liaison.buildings_for(request.user), pk=pk)
    recordable = _recordable(request.user, prop)
    types = asks.department_types()
    if not recordable or not types.exists():
        raise Http404
    form = asks.RequestForm(request.POST or None, request.FILES or None, types=types)
    if request.method == "POST" and form.is_valid():
        occupier = next((o for o in recordable if str(o.pk) == request.POST.get("occupier")), recordable[0])
        name = request.user.get_full_name() or request.user.username
        case = asks.submit(form, received="dept", who=f"{name} ({occupier.name})", prop=prop, occupier=occupier,
                           user=request.user)
        messages.success(request, _("Request sent. Your reference is %(ref)s.") % {"ref": case.display_reference})
        return redirect("occupier:building", pk=prop.pk)
    return render(request, "space/liaison_request.html", {"object": prop, "form": form, "occupiers": recordable})


@_contact_only
def request_detail(request, pk):
    from apps.cases import requests as asks

    case = get_object_or_404(asks.department_cases(request.user), pk=pk)
    return render(request, "space/liaison_request_detail.html", {
        "case": case, "progress": asks.progress(case), "documents": asks.shared_documents(case),
        "doc_url": "occupier:request-document"})


@_contact_only
def request_document(request, pk, doc):
    from django.http import FileResponse

    from apps.cases import requests as asks

    case = get_object_or_404(asks.department_cases(request.user), pk=pk)
    item = get_object_or_404(asks.shared_documents(case), pk=doc)
    return FileResponse(item.file.open("rb"), as_attachment=True,
                        filename=item.original_filename or item.file.name.rsplit("/", 1)[-1])
