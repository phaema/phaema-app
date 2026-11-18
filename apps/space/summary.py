# SPDX-License-Identifier: AGPL-3.0-or-later
"""Working out who holds how much of a building: the stacking view and the per-occupier figures."""
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from .models import ZERO, Headcount, Occupation, Space

# Colours for occupiers in the stacking view. Chosen to tell apart and to carry dark text; outside organisations
# are marked by a pattern as well, so colour is never the only signal.
PALETTE = ["#9ecae1", "#fdae6b", "#a1d99b", "#bcbddc", "#fdd0a2", "#c7e9c0", "#dadaeb", "#fcbba1",
           "#c6dbef", "#fee391", "#d9f0a3", "#e7cbe8"]
SHARED_COLOUR = "#e0e0e0"
VACANT_COLOUR = "#ffffff"


def colour_for(occupier):
    return PALETTE[occupier.pk % len(PALETTE)]


@dataclass
class Block:
    label: str
    area: Decimal | None
    kind: str  # "occupier", "shared" or "vacant"
    occupier: object = None
    space: object = None
    occupation: object = None
    width: Decimal = ZERO

    @property
    def colour(self):
        if self.kind == "occupier":
            return colour_for(self.occupier)
        return SHARED_COLOUR if self.kind == "shared" else VACANT_COLOUR


@dataclass
class Row:
    name: str
    level: int
    area: Decimal | None
    space: object = None
    blocks: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


@dataclass
class Holding:
    occupier: object
    area: Decimal = ZERO
    shared: Decimal = ZERO
    capacity: Decimal = ZERO
    people: int | None = None
    people_on: date | None = None
    people_source: str = ""

    @property
    def total(self):
        return self.area + self.shared

    @property
    def utilisation(self):
        if self.people is None or not self.capacity:
            return None
        return (Decimal(self.people) / self.capacity * 100).quantize(Decimal("1"))

    @property
    def per_person(self):
        if not self.people:
            return None
        return (self.total / self.people).quantize(Decimal("0.1"))

    @property
    def colour(self):
        return colour_for(self.occupier)


def current_occupations(building, on=None):
    on = on or date.today()
    return [o for o in Occupation.objects.filter(building=building).select_related("occupier", "space",
                                                                                        "space__floor", "building")
            if o.current(on)]


def _area(space):
    if space.area_sqm is not None:
        return space.area_sqm
    parts = [p.area_sqm for p in space.parts.all() if p.area_sqm is not None]
    return sum(parts, ZERO) if parts else None


def _check_shares(space, occs):
    """Warn if the shares in one space add up to more than all of it."""
    total = sum((o.percent() for o in occs), ZERO)
    if total > 100:
        return [f"{space}: shares add up to {total:.0f}%, more than the whole space."]
    return []


def stacking(building, on=None):
    """Rows for the stacking view, top floor first, with blocks sized by area."""
    occs = current_occupations(building, on)
    floors = list(Space.objects.filter(building=building, kind=Space.Kind.FLOOR).prefetch_related("parts"))
    rows = []
    by_space = {}
    for o in occs:
        by_space.setdefault(o.space_id, []).append(o)
    for fl in sorted(floors, key=lambda f: -f.level):
        row = Row(name=fl.name, level=fl.level, area=_area(fl), space=fl)
        used = ZERO
        on_floor = [(fl, by_space.get(fl.pk, []))]
        for part in sorted(fl.parts.all(), key=lambda p: (p.kind, p.name)):
            on_floor.append((part, by_space.get(part.pk, [])))
        for space, its in on_floor:
            row.warnings += _check_shares(space, its)
            if space.is_shared:
                if space.area_sqm:
                    row.blocks.append(Block(space.name, space.area_sqm, "shared", space=space))
                    used += space.area_sqm
                continue
            for o in its:
                a = o.area()
                row.blocks.append(Block(o.occupier.name, a, "occupier", occupier=o.occupier, space=space,
                                        occupation=o))
                used += a or ZERO
        if row.area is not None:
            free = row.area - used
            if free > 0:
                row.blocks.append(Block("Vacant", free, "vacant"))
            elif free < 0:
                row.warnings.append(f"{fl.name}: more space is allocated ({used} m²) than the floor has "
                                    f"({row.area} m²).")
        rows.append(row)
    loose = [o for o in occs if o.space_id is None or o.space.building_id != building.pk]
    if loose:
        row = Row(name="Whole building", level=99, area=occs[0].whole_area() if occs else None)
        for o in loose:
            row.blocks.append(Block(o.occupier.name, o.area(), "occupier", occupier=o.occupier, occupation=o))
        rows.insert(0, row)
    widest = max((r.area or sum((b.area or ZERO for b in r.blocks), ZERO) for r in rows), default=ZERO) or ZERO
    for r in rows:
        total = r.area or sum((b.area or ZERO for b in r.blocks), ZERO)
        for b in r.blocks:
            if widest and b.area:
                b.width = (b.area / widest * 100).quantize(Decimal("0.1"))
            elif not widest and r.blocks:
                b.width = (Decimal(100) / len(r.blocks)).quantize(Decimal("0.1"))
        r.scale = (total / widest * 100).quantize(Decimal("0.1")) if widest and total else Decimal(100)
    return rows


def latest_headcounts(building, on=None):
    on = on or date.today()
    found = {}
    for h in Headcount.objects.filter(building=building, counted_on__lte=on).order_by("occupier_id", "-counted_on"):
        found.setdefault(h.occupier_id, h)
    return found


def holdings(building, on=None):
    """Per occupier: area held, their share of shared space (by area held), capacity, people, utilisation."""
    occs = current_occupations(building, on)
    result = OrderedDict()
    for o in occs:
        if o.space_id and o.space.is_shared:
            continue
        h = result.setdefault(o.occupier_id, Holding(o.occupier))
        h.area += o.area() or ZERO
        if o.space_id and o.space.capacity:
            h.capacity += Decimal(o.space.capacity) * o.percent() / 100
    shared = sum((s.area_sqm or ZERO for s in Space.objects.filter(building=building, kind=Space.Kind.SHARED)), ZERO)
    held = sum((h.area for h in result.values()), ZERO)
    for h in result.values():
        if shared and held:
            h.shared = (shared * h.area / held).quantize(Decimal("0.01"))
        h.capacity = h.capacity.quantize(Decimal("1"))
    for occupier_id, count in latest_headcounts(building, on).items():
        if occupier_id in result:
            h = result[occupier_id]
            h.people, h.people_on, h.people_source = count.people, count.counted_on, count.source
    return sorted(result.values(), key=lambda h: -h.total)


def buildings_with_space():
    from apps.properties.models import Property

    ids = set(Space.objects.values_list("building_id", flat=True)) | set(
        Occupation.objects.values_list("building_id", flat=True))
    return Property.objects.filter(pk__in=ids).order_by("reference")


def occupier_buildings(occupier, on=None):
    """Every building an occupier (and those below it) is in today, with its holding there."""
    family = {o.pk for o in occupier.family()}
    on = on or date.today()
    buildings = {o.building for o in Occupation.objects.filter(occupier_id__in=family).select_related("building")
                 if o.current(on)}
    rows = []
    for b in sorted(buildings, key=lambda p: p.reference):
        mine = [h for h in holdings(b, on) if h.occupier.pk in family]
        if mine:
            total = Holding(occupier)
            for h in mine:
                total.area += h.area
                total.shared += h.shared
                total.capacity += h.capacity
                if h.people is not None:
                    total.people = (total.people or 0) + h.people
            rows.append((b, total))
    return rows
