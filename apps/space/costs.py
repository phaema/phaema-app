# SPDX-License-Identifier: AGPL-3.0-or-later
"""What each building costs in a financial year, and how that cost is shared between its occupiers.

Decisions of 18 November 2026: show, not charge; by floor area unless the council chooses headcount or fixed
percentages for a building; shared space spread in proportion; notional rent shown as its own line, with totals
with and without it; every figure keeps its source; every report says which method was used.
"""
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from apps.core.models import ModuleSettings

from . import summary
from .models import ZERO, BuildingCost, CostLine, CostSharing, Space, financial_year_label

PENNY = Decimal("0.01")


def year_of(day):
    """The financial year (April to March) a date falls in, as its starting year."""
    return day.year if day.month >= 4 else day.year - 1


def year_dates(year):
    return date(year, 4, 1), date(year + 1, 3, 31)


def as_at(year, today=None):
    """The date to read occupation from for a year: its last day, or today while the year is running."""
    today = today or date.today()
    return min(year_dates(year)[1], today)


@dataclass
class Cost:
    line: str
    amount: Decimal
    notional: bool
    source: str
    origin: str  # "entered", "property record" or "maintenance jobs"


def building_costs(building, year):
    """Every cost for the building in the year, with where each figure came from."""
    found = [Cost(c.line.name, c.amount, c.line.notional, c.source, "entered")
             for c in BuildingCost.objects.filter(building=building, year_starting=year).select_related("line")]
    names = {c.line for c in found}
    record = building.costs.filter(year_starting=year).first()
    if record is not None:
        if record.rates is not None and "Business rates" not in names:
            found.append(Cost("Business rates", record.rates, False, record.notes or "Property record",
                              "property record"))
        cash_entered = [c for c in found if not c.notional and c.line != "Business rates"]
        if record.running_cost is not None and not cash_entered:
            found.append(Cost("Running costs", record.running_cost, False, record.notes or "Property record",
                              "property record"))
    if ModuleSettings.load().maintenance_enabled:
        for line in CostLine.objects.filter(active=True, from_jobs=True).exclude(name__in=names):
            if any(c.origin == "property record" and c.line == "Running costs" for c in found):
                break  # the running cost already covers repairs
            total = _jobs_cost(building, year)
            if total:
                found.append(Cost(line.name, total, False, "Completed maintenance jobs at the council's cost",
                                  "maintenance jobs"))
    order = {name: i for i, name in enumerate(CostLine.objects.values_list("name", flat=True))}
    return sorted(found, key=lambda c: (c.notional, order.get(c.line, 999), c.line))


def _jobs_cost(building, year):
    from apps.maintenance.models import Job, Responsibility

    start, end = year_dates(year)
    parts = [building.pk, *building.children.values_list("pk", flat=True)]
    jobs = Job.objects.filter(property_id__in=parts, completed_on__range=(start, end),
                              responsibility=Responsibility.LANDLORD)
    return sum((j.cost or ZERO for j in jobs), ZERO)


def total_area(building, on):
    """The area costs are spread over: the floors' areas, or the building's own figure."""
    floors = Space.objects.filter(building=building, kind=Space.Kind.FLOOR)
    areas = [summary._area(f) for f in floors]
    if any(a is not None for a in areas):
        return sum((a or ZERO for a in areas), ZERO)
    return building.floor_area("net")[0] or building.floor_area("gross")[0]


@dataclass
class Share:
    label: str
    occupier: object
    fraction: Decimal
    cash: Decimal = ZERO
    notional: Decimal = ZERO
    area: Decimal | None = None
    people: int | None = None

    @property
    def percent(self):
        return (self.fraction * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

    @property
    def total(self):
        return self.cash + self.notional

    @property
    def per_sqm(self):
        return (self.total / self.area).quantize(PENNY) if self.area else None

    @property
    def per_person(self):
        return (self.total / self.people).quantize(Decimal("1")) if self.people else None


@dataclass
class Sharing:
    building: object
    year: int
    method: str
    method_label: str
    costs: list
    shares: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    on: date | None = None

    @property
    def label(self):
        return financial_year_label(self.year)

    @property
    def cash(self):
        return sum((c.amount for c in self.costs if not c.notional), ZERO)

    @property
    def notional(self):
        return sum((c.amount for c in self.costs if c.notional), ZERO)

    @property
    def total(self):
        return self.cash + self.notional

    @property
    def area(self):
        return total_area(self.building, self.on)

    @property
    def per_sqm(self):
        area = self.area
        return (self.total / area).quantize(PENNY) if area else None


def share_out(building, year, today=None):
    """Share the building's costs for the year between its occupiers, by the building's chosen method."""
    on = as_at(year, today)
    costs = building_costs(building, year)
    setting = CostSharing.objects.filter(building=building).prefetch_related("shares__occupier").first()
    method = setting.method if setting else CostSharing.Method.AREA
    result = Sharing(building, year, method, str(CostSharing.Method(method).label), costs, on=on)
    held = summary.holdings(building, on)
    fractions = OrderedDict()
    if method == CostSharing.Method.AREA:
        base = total_area(building, on)
        if not base:
            result.warnings.append("The building has no floor area, so costs cannot be shared by area.")
            return result
        for h in held:
            fractions[h.occupier.pk] = (h, h.total / base)
        rest = 1 - sum((f for _h, f in fractions.values()), ZERO)
        rest_label = "Vacant space (cost stays with the corporate landlord)"
    elif method == CostSharing.Method.HEADCOUNT:
        people = sum((h.people or 0 for h in held))
        if not people:
            result.warnings.append("No headcount is recorded for this building, so costs cannot be shared by "
                                   "headcount.")
            return result
        for h in held:
            if h.people is None:
                result.warnings.append(f"{h.occupier.name} has no headcount, so takes no share.")
            fractions[h.occupier.pk] = (h, Decimal(h.people or 0) / people)
        rest, rest_label = ZERO, ""
    else:
        by_occupier = {h.occupier.pk: h for h in held}
        for s in setting.shares.all():
            h = by_occupier.get(s.occupier_id) or summary.Holding(s.occupier)
            fractions[s.occupier_id] = (h, s.percent / 100)
        rest = 1 - sum((f for _h, f in fractions.values()), ZERO)
        rest_label = "Not shared out (fixed shares add up to less than 100%)"
        if rest < 0:
            result.warnings.append("The fixed shares add up to more than 100%.")
        missing = [h.occupier.name for h in held if h.occupier.pk not in fractions]
        if missing:
            result.warnings.append("No fixed share for: " + ", ".join(missing) + ".")
    for h, fraction in fractions.values():
        result.shares.append(Share(h.occupier.name, h.occupier, fraction,
                                   cash=(result.cash * fraction).quantize(PENNY),
                                   notional=(result.notional * fraction).quantize(PENNY),
                                   area=h.total or None, people=h.people))
    if rest > Decimal("0.0005"):
        vacant_area = None
        if method == CostSharing.Method.AREA:
            vacant_area = (total_area(building, on) * rest).quantize(PENNY)
        result.shares.append(Share(rest_label, None, rest, cash=(result.cash * rest).quantize(PENNY),
                                   notional=(result.notional * rest).quantize(PENNY), area=vacant_area))
    result.shares.sort(key=lambda s: (s.occupier is None, -s.total))
    return result


def years_held(building=None):
    """Financial years with costs, newest first, always including the current one."""
    qs = BuildingCost.objects.all()
    if building is not None:
        qs = qs.filter(building=building)
    years = set(qs.values_list("year_starting", flat=True))
    from apps.properties.models import PropertyCost

    pc = PropertyCost.objects.all() if building is None else PropertyCost.objects.filter(property=building)
    years |= set(pc.values_list("year_starting", flat=True))
    years.add(year_of(date.today()))
    return sorted(years, reverse=True)


@dataclass
class OccupierTotal:
    occupier: object
    buildings: int = 0
    area: Decimal = ZERO
    people: int = 0
    cash: Decimal = ZERO
    notional: Decimal = ZERO

    @property
    def total(self):
        return self.cash + self.notional

    @property
    def per_sqm(self):
        return (self.total / self.area).quantize(PENNY) if self.area else None

    @property
    def per_person(self):
        return (self.total / self.people).quantize(Decimal("1")) if self.people else None


def estate(year, today=None):
    """Every building's sharing for the year, and the totals for each occupier across the estate."""
    sharings = [share_out(b, year, today) for b in summary.buildings_with_space()]
    totals = OrderedDict()
    unshared = ZERO
    for s in sharings:
        for share in s.shares:
            if share.occupier is None:
                unshared += share.total
                continue
            t = totals.setdefault(share.occupier.pk, OccupierTotal(share.occupier))
            t.buildings += 1
            t.area += share.area or ZERO
            t.people += share.people or 0
            t.cash += share.cash
            t.notional += share.notional
    rows = sorted(totals.values(), key=lambda t: -t.total)
    return sharings, rows, unshared


def for_occupier(occupier, year, today=None):
    """The occupier's (and those below it) share in each building for the year."""
    family = {o.pk for o in occupier.family()}
    found = []
    for b in summary.buildings_with_space():
        s = share_out(b, year, today)
        mine = [x for x in s.shares if x.occupier is not None and x.occupier.pk in family]
        if mine:
            found.append((b, s, mine))
    return found
