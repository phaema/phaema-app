# SPDX-License-Identifier: AGPL-3.0-or-later
"""Retail zoning: the area In Terms of Zone A (ITZA).

The ground floor sales area is divided into zones parallel to the shop front, each the zone depth deep (6.1 m, that
is 20 ft, is usual in England and Wales; some towns use 9.1 m or 15.2 m). Each zone counts at half the zone in front of
it ("halving back"): Zone A in full, Zone B at a half, Zone C at a quarter and the remainder at an eighth. Other areas
(upper floor sales, storage, staff rooms) are added at a fraction of Zone A, written A/n, as agreed locally or by the
valuer. The total is the ITZA; rent ÷ ITZA is the rent per m² Zone A, the figure used to compare shops.

The ground floor can be entered as a simple rectangle (internal width and depth), or as the measured area of each
zone for an irregular shop. Adjustments for return frontages, masking or an unusual shape are matters of valuation
judgement and are not made here: note them with the figure.
"""
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

DEFAULT_ZONE_DEPTH = Decimal("6.1")
ZONES = (("Zone A", Decimal("1")), ("Zone B", Decimal("0.5")), ("Zone C", Decimal("0.25")),
         ("Remainder", Decimal("0.125")))
SQFT = Decimal("10.7639")
PLACES = Decimal("0.01")
COMMON_DIVISORS = (2, 4, 6, 8, 10, 12, 15, 20)
OTHER_ROWS = 6


@dataclass
class Row:
    label: str
    area: Decimal
    fraction: Decimal
    fraction_text: str
    itza: Decimal


@dataclass
class Result:
    zone_depth: Decimal
    rows: list = field(default_factory=list)
    total: Decimal = None
    ground_floor: Decimal = None  # ground floor sales area, all zones together
    errors: list = field(default_factory=list)
    zone_a_rate: Decimal = None  # entered, to see the rent it gives
    rent_at_rate: Decimal = None

    @property
    def ok(self):
        return not self.errors and self.total is not None


def _number(text, label, errors, required=False):
    text = str(text or "").replace(",", "").replace("£", "").strip()
    if not text:
        if required:
            errors.append(f"Enter the {label}.")
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        errors.append(f"The {label} must be a number.")
        return None
    if value < 0:
        errors.append(f"The {label} cannot be negative.")
        return None
    return value


def calculate(spec):
    """Work out the ITZA from a specification (the calculator's form, or the workings saved on the property)."""
    errors = []
    depth = _number(spec.get("zone_depth"), "zone depth", errors) or DEFAULT_ZONE_DEPTH
    if depth <= 0:
        errors.append("The zone depth must be more than 0.")
        depth = DEFAULT_ZONE_DEPTH
    result = Result(zone_depth=depth)
    if spec.get("mode", "rectangle") == "zones":
        areas = [_number(a, f"{label} area", errors) or Decimal("0")
                 for a, (label, _w) in zip(list(spec.get("zones") or []) + [""] * 4, ZONES)]
    else:
        width = _number(spec.get("width"), "internal width", errors, required=True)
        shop_depth = _number(spec.get("depth"), "shop depth", errors, required=True)
        areas = []
        if width is not None and shop_depth is not None:
            remaining = shop_depth
            for n in range(len(ZONES)):
                part = remaining if n == len(ZONES) - 1 else min(remaining, depth)
                areas.append(width * part)
                remaining -= part
    for (label, weight), area in zip(ZONES, areas):
        if area:
            result.rows.append(Row(label, area.quantize(PLACES), weight, _fraction_text(weight),
                                   (area * weight).quantize(PLACES, ROUND_HALF_UP)))
    result.ground_floor = sum((Decimal(a) for a in areas), Decimal("0")).quantize(PLACES) if areas else None
    for n, other in enumerate(spec.get("others") or []):
        label = str(other.get("label") or "").strip()[:80]
        area = _number(other.get("area"), f"area of {label or 'other area ' + str(n + 1)}", errors)
        if area is None and not label:
            continue
        if area is None:
            errors.append(f"Enter the area of {label}.")
            continue
        divisor = _number(other.get("divisor"), f"fraction for {label or 'the other area'}", errors)
        if not divisor:
            errors.append(f"Choose the fraction of Zone A for {label or 'the other area'} (A/n).")
            continue
        result.rows.append(Row(label or "Other area", area.quantize(PLACES), 1 / divisor, f"A/{divisor.normalize():f}",
                               (area / divisor).quantize(PLACES, ROUND_HALF_UP)))
    if not result.rows and not errors:
        errors.append("Enter the ground floor sales area, or other areas.")
    result.errors = errors
    if not errors:
        result.total = sum((r.itza for r in result.rows), Decimal("0"))
        rate = _number(spec.get("zone_a_rate"), "Zone A rate", errors)
        if rate is not None and not errors:
            result.zone_a_rate = rate
            result.rent_at_rate = (rate * result.total).quantize(PLACES, ROUND_HALF_UP)
        result.errors = errors
    return result


def _fraction_text(weight):
    return {Decimal("1"): "A", Decimal("0.5"): "A/2", Decimal("0.25"): "A/4", Decimal("0.125"): "A/8"}[weight]


def spec_from_post(post):
    return {
        "zone_depth": post.get("zone_depth", ""), "mode": "zones" if post.get("mode") == "zones" else "rectangle",
        "width": post.get("width", ""), "depth": post.get("depth", ""),
        "zones": [post.get(f"zone_{n}", "") for n in range(len(ZONES))],
        "others": [{"label": post.get(f"other_label_{n}", ""), "area": post.get(f"other_area_{n}", ""),
                    "divisor": post.get(f"other_divisor_{n}", "")} for n in range(OTHER_ROWS)],
        "zone_a_rate": post.get("zone_a_rate", ""),
    }


def per_sqft(rate_per_sqm):
    return (rate_per_sqm / SQFT).quantize(PLACES, ROUND_HALF_UP)


def sqft(area_sqm):
    return (area_sqm * SQFT).quantize(Decimal("1"), ROUND_HALF_UP)
