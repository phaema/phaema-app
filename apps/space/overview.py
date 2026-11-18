# SPDX-License-Identifier: AGPL-3.0-or-later
"""A short account of who occupies a property and what it costs them, for the property page and the property
report. It covers the property itself and any buildings within it that have space records, and respects the
person's access: nothing if the space module is off for them, and no costs without the costing module."""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from apps.core.access import can_use

from . import costs, summary
from .models import ZERO, Occupation, Space


@dataclass
class BuildingOverview:
    building: object
    holdings: list
    occupations: list
    shared: list
    floor_area: Decimal | None
    sharing: object = None  # costs.Sharing for the latest year with costs, if the person may see costs
    warnings: list = field(default_factory=list)

    @property
    def held(self):
        return sum((h.total for h in self.holdings), ZERO)

    @property
    def people(self):
        counted = [h.people for h in self.holdings if h.people is not None]
        return sum(counted) if counted else None

    @property
    def capacity(self):
        return sum((h.capacity for h in self.holdings), ZERO)

    @property
    def utilisation(self):
        if self.people is None or not self.capacity:
            return None
        return (Decimal(self.people) / self.capacity * 100).quantize(Decimal("1"))

    @property
    def vacant(self):
        if not self.floor_area:
            return None
        rest = self.floor_area - self.held
        return rest if rest > 0 else ZERO

    @property
    def external(self):
        return sum(1 for h in self.holdings if h.occupier.is_external)


def _with_space(prop):
    """The property and the buildings within it that have floors, rooms or occupations recorded."""
    candidates = [prop, *[p for p, _d in prop.descendants()]]
    ids = [p.pk for p in candidates]
    held = set(Space.objects.filter(building_id__in=ids).values_list("building_id", flat=True)) | set(
        Occupation.objects.filter(building_id__in=ids).values_list("building_id", flat=True))
    return [p for p in candidates if p.pk in held]


def latest_sharing(building, today=None):
    """The cost sharing for the newest financial year that has any costs, or None."""
    for year in costs.years_held(building):
        if costs.building_costs(building, year):
            return costs.share_out(building, year, today)
    return None


def for_property(prop, user, on=None, today=None):
    """One BuildingOverview for each building with space records, or None if the person cannot see space."""
    if user is None or not can_use(user, "space"):
        return None
    on = on or date.today()
    with_costs = can_use(user, "spacecosts")
    out = []
    for b in _with_space(prop):
        occs = sorted(summary.current_occupations(b, on),
                      key=lambda o: (-(o.space.floor.level if o.space and o.space.floor_id else
                                       (o.space.level if o.space else 99)), o.space.name if o.space else "",
                                     o.occupier.name))
        rows = summary.stacking(b, on)
        item = BuildingOverview(
            building=b, holdings=summary.holdings(b, on), occupations=occs,
            shared=list(Space.objects.filter(building=b, kind=Space.Kind.SHARED).select_related("floor")),
            floor_area=costs.total_area(b, on), warnings=[w for r in rows for w in r.warnings])
        if with_costs:
            item.sharing = latest_sharing(b, today)
        out.append(item)
    return out
