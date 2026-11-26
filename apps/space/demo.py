# SPDX-License-Identifier: AGPL-3.0-or-later
"""Demonstration data for space and costing: an invented civic centre shared by four council departments, a
library and an NHS clinic, and the Northfield Library as a public building.

Everything here is made up. No real building is named or modelled (Stuart, 18 November 2026).
"""
from datetime import date
from decimal import Decimal

from apps.core.models import ModuleSettings
from apps.properties.models import Property

from .models import BuildingCost, CostLine, Headcount, Occupation, Occupier, Space, UseFigure, UseMeasure
from .seed import ensure_cost_lines, ensure_measures

CIVIC = "DM-S30"
LIBRARY = "DM-N03"
SOURCE = "Demonstration figures"

# Yearly costs (£) for the latest full year; the year before is about 4% lower.
COSTS = {
    CIVIC: {"Business rates": 168000, "Energy": 96000, "Water": 9500, "Cleaning": 58000, "Security": 31000,
            "Repairs and maintenance": 47000, "Insurance": 14200, "Facilities management contracts": 22000,
            "Notional rent": 412500},
    LIBRARY: {"Business rates": 21000, "Energy": 18500, "Water": 2100, "Cleaning": 9800,
              "Repairs and maintenance": 7600, "Insurance": 2900, "Notional rent": 64000},
}

# (name, level, parent, external kind, head of service, cost centre)
OCCUPIERS = [
    ("Place Directorate", "directorate", None, "", "Director of Place", "PL000"),
    ("People Directorate", "directorate", None, "", "Director of People", "PE000"),
    ("Resources Directorate", "directorate", None, "", "Director of Resources", "RS000"),
    ("Housing Services", "department", "Place Directorate", "", "Head of Housing", "PL210"),
    ("Planning and Regeneration", "department", "Place Directorate", "", "Head of Planning", "PL320"),
    ("Adult Social Care", "department", "People Directorate", "", "Head of Adult Social Care", "PE110"),
    ("Libraries and Culture", "department", "People Directorate", "", "Head of Libraries", "PE450"),
    ("Customer Services", "department", "Resources Directorate", "", "Head of Customer Services", "RS150"),
    ("Exampleton Community Health (NHS)", "external", None, "nhs", "Practice manager", ""),
]
DEMO_NAMES = [o[0] for o in OCCUPIERS]


def _civic_centre():
    """The civic centre is one of the main demonstration properties (load_demo_data)."""
    return Property.objects.get(reference=CIVIC)


def load(today=None):
    today = today or date.today()
    modules = ModuleSettings.load()
    if not (modules.space_enabled and modules.space_costing_enabled):
        modules.space_enabled = modules.space_costing_enabled = True
        modules.save()
    ensure_measures()
    ensure_cost_lines()
    occ = {}
    for name, level, parent, kind, head, cc in OCCUPIERS:
        occ[name], _c = Occupier.objects.update_or_create(name=name, defaults={
            "level": level, "parent": occ.get(parent), "external_kind": kind, "head_of_service": head,
            "cost_centre": cc, "active": True})
    civic = _civic_centre()
    _costs(today)
    if Space.objects.filter(building=civic).exists():
        return Space.objects.filter(building=civic).count()
    start = date(today.year - 2, 4, 1)

    def floor(name, level, area):
        return Space.objects.create(building=civic, kind="floor", name=name, level=level, area_sqm=Decimal(area))

    def part(fl, name, kind, use, area, capacity=None):
        return Space.objects.create(building=civic, kind=kind, name=name, floor=fl, level=fl.level, use=use,
                                    area_sqm=Decimal(area), capacity=capacity)

    def put(space, who, **kw):
        return Occupation.objects.create(building=civic, space=space, occupier=occ[who], starts=kw.pop("starts", start),
                                         **kw)

    ground = floor("Ground floor", 0, "1200")
    part(ground, "Reception and waiting", "shared", "reception", "150")
    put(part(ground, "Customer service centre", "room", "public", "300", 18), "Customer Services")
    put(part(ground, "Library", "room", "library", "480", 12), "Libraries and Culture")
    part(ground, "Meeting rooms G.1 to G.4", "shared", "meeting", "120")
    first = floor("First floor", 1, "1100")
    put(part(first, "Open-plan office east", "room", "office", "520", 70), "Housing Services")
    put(part(first, "Open-plan office west", "room", "office", "430", 60), "Adult Social Care")
    part(first, "Kitchen and welfare", "shared", "kitchen", "80")
    second = floor("Second floor", 2, "1000")
    office = part(second, "Open-plan office", "room", "office", "500", 64)
    put(office, "Planning and Regeneration", share_percent=Decimal("60"), basis="shared")
    put(office, "Customer Services", share_percent=Decimal("20"), basis="shared",
        notes="Back-office team, moved up from the ground floor")
    put(part(second, "Health hub", "room", "clinic", "380", 14), "Exampleton Community Health (NHS)",
        starts=date(today.year - 1, 10, 1), notes="Licence to the NHS trust; One Public Estate funded fit-out")
    part(second, "Meeting rooms 2.1 and 2.2", "shared", "meeting", "70")

    counted = date(today.year, 4, 1) if today >= date(today.year, 4, 1) else date(today.year - 1, 4, 1)
    for who, people, fte in [("Customer Services", 31, "27.5"), ("Libraries and Culture", 9, "6.8"),
                             ("Housing Services", 88, "81.0"), ("Adult Social Care", 74, "69.4"),
                             ("Planning and Regeneration", 41, "38.2"),
                             ("Exampleton Community Health (NHS)", 11, "9.0")]:
        Headcount.objects.create(building=civic, occupier=occ[who], counted_on=counted, people=people,
                                 fte=Decimal(fte), source="HR establishment list, April (demonstration)")
        # the year before, a few more people, for the previous year's costs and a trend
        Headcount.objects.create(building=civic, occupier=occ[who], counted_on=date(counted.year - 1, 4, 1),
                                 people=people + 3, fte=Decimal(fte) + 2,
                                 source="HR establishment list, April (demonstration)")

    measures = {m.name: m for m in UseMeasure.objects.all()}
    year_start = date(today.year - 1, 4, 1)
    year_end = date(today.year, 3, 31)
    figures = [(civic, "Visits", "212400", None), (civic, "Hours used", "2150", "2860")]
    library = Property.objects.filter(reference=LIBRARY).first()
    if library:
        Occupation.objects.get_or_create(building=library, space=None, occupier=occ["Libraries and Culture"],
                                         defaults={"starts": date(2015, 4, 1)})
        Headcount.objects.get_or_create(building=library, occupier=occ["Libraries and Culture"], counted_on=counted,
                                        defaults={"people": 6, "fte": Decimal("4.2"),
                                                  "source": "HR establishment list, April (demonstration)"})
        figures += [(library, "Visits", "48600", None), (library, "Registered members", "5210", None),
                     (library, "Hours used", "1480", "2340")]
    for building, measure, value, available in figures:
        if measure in measures:
            UseFigure.objects.get_or_create(
                building=building, measure=measures[measure], period_start=year_start,
                defaults={"period_end": year_end, "value": Decimal(value),
                          "available": Decimal(available) if available else None, "source": SOURCE + " (door counter)"})
    return Space.objects.filter(building=civic).count()


def _costs(today):
    from .costs import year_of

    lines = {c.name: c for c in CostLine.objects.all()}
    latest = year_of(today) - 1
    for ref, amounts in COSTS.items():
        building = Property.objects.filter(reference=ref).first()
        if building is None:
            continue
        for year, factor in ((latest, Decimal("1")), (latest - 1, Decimal("0.96"))):
            for name, amount in amounts.items():
                source = ("Valuer's estimate of market rent (demonstration)" if name == "Notional rent"
                          else "Finance ledger (demonstration)")
                BuildingCost.objects.get_or_create(
                    building=building, year_starting=year, line=lines[name],
                    defaults={"amount": (Decimal(amount) * factor).quantize(Decimal("1")), "source": source})


def remove():
    demo = Property.objects.filter(reference__startswith="DM-")
    UseFigure.objects.filter(building__in=demo).delete()
    BuildingCost.objects.filter(building__in=demo).delete()
    Headcount.objects.filter(building__in=demo).delete()
    Occupation.objects.filter(building__in=demo).delete()
    Space.objects.filter(building__in=demo, floor__isnull=False).delete()  # rooms before their floors
    Space.objects.filter(building__in=demo).delete()
    for name in reversed(DEMO_NAMES):  # teams and departments before directorates
        o = Occupier.objects.filter(name=name).first()
        if o and not o.occupations.exists() and not o.children.exists():
            o.delete()
