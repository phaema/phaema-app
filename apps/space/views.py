# SPDX-License-Identifier: AGPL-3.0-or-later
"""Space and costing pages: the estate's shared buildings, a building's stacking view, and each occupier."""
from datetime import date
from decimal import Decimal

from django.shortcuts import get_object_or_404, render

from apps.core.access import module_view
from apps.core.roles import can_edit, is_administrator
from apps.properties.models import Property

from . import summary
from .models import ZERO, Occupier, UseFigure

space_view = module_view("space", "space/off.html")


def _on(request):
    try:
        return date.fromisoformat(request.GET.get("on", ""))
    except ValueError:
        return date.today()


@space_view
def home(request):
    on = _on(request)
    rows = []
    for b in summary.buildings_with_space():
        held = summary.holdings(b, on)
        people = sum((h.people or 0 for h in held))
        capacity = sum((h.capacity for h in held), ZERO)
        rows.append({
            "building": b,
            "occupiers": held,
            "external": sum(1 for h in held if h.occupier.is_external),
            "area": sum((h.total for h in held), ZERO),
            "people": people,
            "capacity": capacity,
            "utilisation": (Decimal(people) / capacity * 100).quantize(Decimal("1")) if people and capacity else None,
        })
    return render(request, "space/home.html", {"rows": rows, "on": on, "is_admin": is_administrator(request.user)})


@space_view
def building(request, pk):
    prop = get_object_or_404(Property, pk=pk)
    on = _on(request)
    rows = summary.stacking(prop, on)
    held = summary.holdings(prop, on)
    figures = UseFigure.objects.filter(building=prop).select_related("measure", "created_by", "updated_by")[:20]
    warnings = [w for r in rows for w in r.warnings]
    return render(request, "space/building.html", {
        "object": prop, "rows": rows, "holdings": held, "figures": figures, "warnings": warnings, "on": on,
        "can_edit": can_edit(request.user, prop),
        "total_area": sum((h.total for h in held), ZERO),
        "total_people": sum((h.people or 0 for h in held)),
        "has_external": any(h.occupier.is_external for h in held),
    })


@space_view
def occupiers(request):
    on = _on(request)
    found = []
    for occ in Occupier.objects.filter(active=True).select_related("parent", "liaison"):
        places = summary.occupier_buildings(occ, on)
        found.append({
            "occupier": occ, "buildings": len(places),
            "area": sum((h.total for _b, h in places), ZERO),
            "people": sum((h.people or 0 for _b, h in places)),
        })
    council = [f for f in found if not f["occupier"].is_external]
    outside = [f for f in found if f["occupier"].is_external]
    return render(request, "space/occupiers.html", {"council": council, "outside": outside, "on": on,
                                                    "is_admin": is_administrator(request.user)})


@space_view
def occupier(request, pk):
    occ = get_object_or_404(Occupier, pk=pk)
    on = _on(request)
    places = summary.occupier_buildings(occ, on)
    return render(request, "space/occupier.html", {
        "object": occ, "places": places, "on": on,
        "area": sum((h.total for _b, h in places), ZERO),
        "people": sum((h.people or 0 for _b, h in places)),
        "children": occ.children.filter(active=True),
    })
