# SPDX-License-Identifier: AGPL-3.0-or-later
"""Space and costing pages: the estate's shared buildings, a building's stacking view, and each occupier."""
from datetime import date
from decimal import Decimal

from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render

from apps.core.access import can_use, module_view
from apps.core.roles import can_edit, is_administrator
from apps.properties.models import Property

from . import costs, summary
from .models import ZERO, CostSharing, Occupier, UseFigure, financial_year_label

space_view = module_view("space", "space/off.html")


def _can_cost(request):
    return can_use(request.user, "spacecosts")


def _year(request):
    text = request.GET.get("year", "")
    return int(text) if text.isdigit() and 1990 <= int(text) <= 2200 else costs.year_of(date.today())


def _years(year, building=None):
    years = costs.years_held(building)
    if year not in years:
        years = sorted({*years, year}, reverse=True)
    return [(y, financial_year_label(y)) for y in years]


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
    sharing = None
    year = _year(request)
    if _can_cost(request):
        sharing = costs.share_out(prop, year)
    return render(request, "space/building.html", {
        "sharing": sharing, "year": year, "years": _years(year, prop) if sharing else [],
        "can_edit_costs": bool(sharing) and request.user.has_perm("space.add_buildingcost"),
        "sharing_setting": CostSharing.objects.filter(building=prop).first(),
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
    year = _year(request)
    cost_rows = costs.for_occupier(occ, year) if _can_cost(request) else None
    cost_total = None
    if cost_rows is not None:
        cost_total = {"cash": sum((x.cash for _b, _s, mine in cost_rows for x in mine), ZERO),
                      "notional": sum((x.notional for _b, _s, mine in cost_rows for x in mine), ZERO)}
        cost_total["total"] = cost_total["cash"] + cost_total["notional"]
    return render(request, "space/occupier.html", {
        "object": occ, "places": places, "on": on, "cost_rows": cost_rows, "cost_total": cost_total,
        "year": year, "years": _years(year) if cost_rows is not None else [],
        "area": sum((h.total for _b, h in places), ZERO),
        "people": sum((h.people or 0 for _b, h in places)),
        "children": occ.children.filter(active=True),
    })


@space_view
def estate_costs(request):
    from django.core.exceptions import PermissionDenied

    if not _can_cost(request):
        raise PermissionDenied
    year = _year(request)
    sharings, rows, unshared = costs.estate(year)
    context = {"year": year, "label": financial_year_label(year), "years": _years(year), "sharings": sharings,
               "rows": rows, "unshared": unshared, "is_admin": is_administrator(request.user),
               "cash": sum((s.cash for s in sharings), ZERO), "notional": sum((s.notional for s in sharings), ZERO)}
    if request.GET.get("format") == "xlsx":
        return _workbook(context)
    return render(request, "space/costs.html", context)


def _workbook(ctx):
    from io import BytesIO

    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    head = (Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="1D3557"))

    def sheet(ws, title, header, rows, money=()):
        ws.title = title
        ws.append(header)
        for cell in ws[1]:
            cell.font, cell.fill = head
        for row in rows:
            ws.append([float(v) if isinstance(v, Decimal) else v for v in row])
        for col in money:
            for cell in ws.iter_cols(min_col=col, max_col=col, min_row=2):
                for c in cell:
                    c.number_format = "#,##0"
        for i, h in enumerate(header, start=1):
            ws.column_dimensions[ws.cell(1, i).column_letter].width = max(12, min(48, len(str(h)) + 4))

    sheet(wb.active, "By occupier",
          ["Occupier", "Outside organisation", "Cost centre", "Buildings", "Area (m²)", "People", "Cash cost (£)",
           "Notional rent (£)", "Total (£)", "£ per m²", "£ per person"],
          [(t.occupier.name, "Yes" if t.occupier.is_external else "", t.occupier.cost_centre, t.buildings,
            t.area, t.people or None, t.cash, t.notional, t.total, t.per_sqm, t.per_person) for t in ctx["rows"]],
          money=(7, 8, 9))
    shares = []
    for s in ctx["sharings"]:
        for x in s.shares:
            shares.append((s.building.reference, s.building.name, s.method_label, x.label, x.percent, x.area,
                           x.people, x.cash, x.notional, x.total))
    sheet(wb.create_sheet(), "By building",
          ["Reference", "Building", "Method", "Occupier", "Share (%)", "Area (m²)", "People", "Cash cost (£)",
           "Notional rent (£)", "Total (£)"], shares, money=(8, 9, 10))
    lines = [(s.building.reference, s.building.name, c.line, "Notional" if c.notional else "Cash", c.amount,
              c.origin, c.source) for s in ctx["sharings"] for c in s.costs]
    sheet(wb.create_sheet(), "Costs and sources",
          ["Reference", "Building", "Cost", "Kind", "Amount (£)", "From", "Source"], lines, money=(5,))
    about = wb.create_sheet("About")
    for line in (f"Space costs by occupier, financial year {ctx['label']}", "",
                 "Each building's costs are shared between its occupiers by the method set for that building "
                 "(by floor area unless set otherwise). Shared space is spread in proportion to the space each "
                 "occupier holds. Vacant space stays with the corporate landlord.",
                 "Notional rent is not cash: it is what a freehold building would cost to rent.",
                 "These figures show the cost of occupation; they are not recharges.",
                 f"Produced by PHAEMA on {date.today():%d %B %Y}."):
        about.append([line])
    about.column_dimensions["A"].width = 110
    buf = BytesIO()
    wb.save(buf)
    response = HttpResponse(buf.getvalue(),
                            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="space-costs-{ctx["label"]}.xlsx"'
    return response
