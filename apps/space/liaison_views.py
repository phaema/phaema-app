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
    return render(request, "space/liaison_building.html", {
        "object": prop, "rows": summary.stacking(prop), "holdings": own, "recordable": recordable,
        "surveyor": prop.managing_surveyor, "today": date.today(),
        "history": Headcount.objects.filter(building=prop, occupier_id__in=mine).select_related("occupier")[:10],
    })


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
