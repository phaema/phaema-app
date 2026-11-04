# SPDX-License-Identifier: AGPL-3.0-or-later
"""The valuation programme, impairment prompts and the year-end schedule."""
from dataclasses import dataclass, field
from datetime import date

from django.db import transaction

from apps.properties.models import Property

from .models import AssetClass, Classification, Valuation, ValuationSettings


def current_classes(on=None):
    """{property id: Classification in force on that date}."""
    on = on or date.today()
    result = {}
    for c in (Classification.objects.filter(effective_from__lte=on).select_related("asset_class", "property")
              .order_by("property_id", "-effective_from", "-pk")):
        result.setdefault(c.property_id, c)
    return result


def current_class(prop, on=None):
    return (Classification.objects.filter(property=prop, effective_from__lte=on or date.today())
            .select_related("asset_class").first())


def last_accepted(prop, on=None):
    qs = Valuation.objects.filter(property=prop, status=Valuation.Status.ACCEPTED)
    if on:
        qs = qs.filter(valuation_date__lte=on)
    return qs.first()


@dataclass
class Due:
    property: Property
    asset_class: AssetClass
    last: Valuation = None
    reason: str = ""
    current: Valuation = None  # this year's valuation, if instructed


def programme(year_end=None):
    """Assets to value at the year end, why, and any valuation already under way."""
    settings = ValuationSettings.load()
    year_end = year_end or settings.year_end()
    classes = current_classes(year_end)
    this_year = {v.property_id: v for v in Valuation.objects.filter(valuation_date=year_end)
                 .select_related("valuer", "case")}
    rows = []
    for pid, c in classes.items():
        cls = c.asset_class
        if not cls.revalued:
            continue
        last = last_accepted(c.property, year_end)
        if last and last.valuation_date == year_end:
            last = Valuation.objects.filter(property=c.property, status="accepted",
                                            valuation_date__lt=year_end).first()
        if last is None:
            reason = "Not valued yet"
        elif last.asset_class_id != cls.pk:
            reason = f"Reclassified since the last valuation ({last.asset_class})"
        elif (year_end.year - last.valuation_date.year) >= cls.cycle_years:
            every = "every year" if cls.cycle_years == 1 else f"every {cls.cycle_years} years"
            reason = f"Due: valued {last.valuation_date:%d/%m/%Y}, revalued {every}"
        elif pid in this_year:
            reason = "Valued this year"
        else:
            continue
        if last and last.value is not None and last.value < settings.de_minimis and pid not in this_year:
            continue
        rows.append(Due(c.property, cls, last, reason, this_year.get(pid)))
    return sorted(rows, key=lambda d: (d.asset_class.order, d.property.reference))


@transaction.atomic
def start(year_end, user=None, valuer=None):
    """Open the programme case and an asset valuation case and instruction for every asset due."""
    from apps.cases.models import CaseType
    from apps.cases.workflow import open_case

    label = f"{year_end:%-d %B %Y}"
    types = {t.code: t for t in CaseType.objects.filter(code__in=("valuation_programme", "asset_valuation"))}
    main = open_case(types["valuation_programme"], title=f"Valuation programme, valuations at {label}",
                     owner=user, target_date=year_end)
    made = 0
    for due in programme(year_end):
        if due.current:
            continue
        case = open_case(types["asset_valuation"], title=f"Valuation of {due.property.name} at {label}",
                         property=due.property, owner=due.property.managing_surveyor or user, target_date=year_end)
        Valuation.objects.create(property=due.property, asset_class=due.asset_class, basis=due.asset_class.basis,
                                 valuation_date=year_end, valuer=valuer, case=case)
        made += 1
    return main, made


# ------------------------------------------------------------------ impairment prompts

@dataclass
class Prompt:
    property: Property
    last: Valuation
    reasons: list = field(default_factory=list)


def prompts(today=None):
    """Assets where something has happened since the last valuation that may affect its value (VA-08)."""
    from apps.cases.models import Case
    from apps.leases.models import Lease

    today = today or date.today()
    open_reviews = set(Case.objects.filter(case_type__code="impairment").exclude(status="closed")
                       .values_list("property_id", flat=True))
    result = []
    for pid, c in current_classes(today).items():
        prop = c.property
        last = last_accepted(prop, today)
        if last is None or pid in open_reviews:
            continue
        reasons = []
        if last.occupation_then and prop.occupation != last.occupation_then:
            reasons.append(f"Occupation changed to {prop.get_occupation_display().lower()}")
        if last.purpose_then and prop.holding_purpose != last.purpose_then:
            reasons.append(f"Holding purpose now {prop.get_holding_purpose_display().lower()}: check the class")
        ended = Lease.objects.filter(properties=prop, actual_end__gt=last.valuation_date, actual_end__lte=today)
        if ended.exists():
            reasons.append("A lease has ended: " + ", ".join(lease.reference for lease in ended[:3]))
        try:
            from apps.maintenance.models import Component, Job

            if Job.objects.filter(property=prop, priority="emergency", reported_on__gt=last.valuation_date).exists():
                reasons.append("Emergency repair since the valuation: check for physical damage")
            if Component.objects.filter(property=prop, condition="D", condition_on__gt=last.valuation_date).exists():
                reasons.append("A component has been graded D (bad) since the valuation")
        except LookupError:
            pass
        if reasons:
            result.append(Prompt(prop, last, reasons))
    return sorted(result, key=lambda p: p.property.reference)


def open_review(prop, reasons, user=None):
    from apps.cases.models import CaseNote, CaseType
    from apps.cases.workflow import open_case

    case = open_case(CaseType.objects.get(code="impairment"), title=f"Impairment review: {prop.name}",
                     property=prop, owner=prop.managing_surveyor or user)
    CaseNote.objects.create(case=case, text="Raised by PHAEMA because:\n" + "\n".join(f"- {r}" for r in reasons))
    return case


# ------------------------------------------------------------------ year-end schedule

def schedule(year_end):
    """Every classified asset with its latest accepted valuation at the year end (VA-09)."""
    rows = []
    for pid, c in sorted(current_classes(year_end).items(), key=lambda i: i[1].property.reference):
        v = last_accepted(c.property, year_end)
        rows.append((c.property, c.asset_class, v))
    return rows


# ------------------------------------------------------------------ indexation

@dataclass
class Indexed:
    value: object = None
    factor: object = None
    note: str = ""


def indexed(valuation, year_end):
    """The last accepted value brought forward to the year end with the class's index (VA-07). The index is applied
    to the buildings where land and buildings are split, and to the whole value otherwise."""
    from decimal import ROUND_HALF_UP, Decimal

    from .models import IndexPoint

    if valuation is None or valuation.value is None or valuation.valuation_date >= year_end:
        return Indexed()
    name = valuation.asset_class.index.strip()
    if not name:
        return Indexed(note="No index set for this class")
    start, end = IndexPoint.at(name, valuation.valuation_date), IndexPoint.at(name, year_end)
    if start is None or end is None or not start.value:
        return Indexed(note=f"{name}: index values missing")
    factor = (end.value / start.value).quantize(Decimal("0.0001"), ROUND_HALF_UP)
    if valuation.building_value is not None and valuation.land_value is not None:
        value = valuation.land_value + (valuation.building_value * factor)
    else:
        value = valuation.value * factor
    return Indexed(value.quantize(Decimal("1"), ROUND_HALF_UP), factor, f"{name} {start.value} to {end.value}")
