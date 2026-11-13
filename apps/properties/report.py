# SPDX-License-Identifier: AGPL-3.0-or-later
"""The property report: everything PHAEMA holds about a property that a valuer or colleague needs first.

Opened from a valuation case it is the "Initial valuation report": the property, its site and buildings, floor
areas, floor plans, titles, tenancies and other agreements, and the cases in hand. It is written in the document
library's simple markup (see apps/documents/render.py), so the same text makes the page and the Word file.
"""
from datetime import date
from decimal import Decimal

from django.utils.formats import date_format

from .models import Property

MISSING = "[Not recorded]"


def _cell(value):
    """Text that is safe inside a table cell of the markup."""
    text = "" if value is None else str(value)
    return " ".join(text.replace("|", "/").split())


def _row(*cells):
    return "| " + " | ".join(_cell(c) or "–" for c in cells) + " |"


def _head(*cells):
    return _row(*(f"**{c}**" for c in cells))


def _table(pairs):
    return [_row(label, value) for label, value in pairs]


def _para(text):
    """Free text as paragraphs; lines that would be read as markup lose their leading mark."""
    out = []
    for chunk in str(text).replace("\r", "").split("\n\n"):
        lines = [line.strip().lstrip("#|-").strip() for line in chunk.split("\n")]
        chunk = "\n".join(line for line in lines if line)
        if chunk:
            out += [chunk, ""]
    return out


def _date(d):
    return f"{d.day} {d:%B %Y}" if d else ""


def _money(amount):
    return f"£{amount:,.0f}" if amount is not None else ""


def _area(value):
    return f"{value:,.0f} m²" if value is not None else ""


def _name(user):
    return (user.get_full_name() or user.username) if user else ""


def _physical(prop):
    """Location and description as text, and the remaining facts as rows."""
    skip = {"Location", "Description"}
    return [(label, value) for label, value in prop.physical_rows() if label not in skip]


def family(prop):
    """The property, its parts (in tree order, with depth) and the properties it is part of."""
    return prop.descendants(), prop.ancestors()


def agreements(prop, parts, ancestors):
    """Tenancies and other agreements over the property, its parts or what it is part of, that have not ended."""
    from apps.leases.models import Lease

    ids = [prop.pk, *[p.pk for p, _d in parts], *[a.pk for a in ancestors]]
    return (Lease.objects.filter(properties__in=ids).exclude(status=Lease.Status.ENDED).distinct()
            .select_related("counterparty").prefetch_related("properties", "breaks")
            .order_by("direction", "status", "reference"))


def open_cases(prop, parts, ancestors, leases, exclude=None):
    from django.db.models import Q

    from apps.cases.models import Case

    ids = [prop.pk, *[p.pk for p, _d in parts], *[a.pk for a in ancestors]]
    cases = (Case.objects.filter(Q(property__in=ids) | Q(lease__in=[lease.pk for lease in leases]))
             .exclude(status=Case.Status.CLOSED).select_related("case_type", "owner", "property", "lease").distinct()
             .order_by("received_on", "pk"))
    return cases.exclude(pk=exclude.pk) if exclude is not None else cases


def gaps(prop, parts):
    """What a valuer will ask for that is not yet recorded."""
    out = []
    if not prop.location_description:
        out.append("Location description")
    if not prop.building_description:
        out.append("Description of the property")
    buildings = [p for p, _d in parts if p.property_type == Property.PropertyType.BUILDING] or (
        [prop] if prop.property_type in (Property.PropertyType.BUILDING, Property.PropertyType.UNIT) else [])
    for b in buildings:
        missing = [label for label, value in (("construction", b.construction_type), ("storeys", b.storeys),
                                              ("roof", b.roof_type or b.roof_covering), ("windows", b.window_type))
                   if not value]
        if missing:
            out.append(f"{b.name}: {', '.join(missing)}")
    if prop.property_type in (Property.PropertyType.ESTATE, Property.PropertyType.SITE, Property.PropertyType.LAND) \
            and prop.site_area_ha is None:
        out.append("Site area")
    if not any((prop.gia_sqm, prop.nia_sqm, prop.gea_sqm)) and not parts \
            and prop.property_type != Property.PropertyType.LAND:
        out.append("Floor areas")
    elif any((prop.gia_sqm, prop.nia_sqm, prop.gea_sqm)) and not prop.area_standard:
        out.append("The measurement standard the floor areas follow")
    if not any((prop.mains_gas, prop.electricity, prop.mains_water, prop.drainage)) and not any(
            (b.mains_gas, b.electricity, b.mains_water, b.drainage) for b in buildings):
        out.append("Services")
    plans = prop.plans.exists() or any(p.plans.exists() for p, _d in parts)
    if not plans and prop.property_type != Property.PropertyType.LAND:
        out.append("Floor plans")
    if not prop.titles.exists():
        out.append("Title (no title is linked to this property)")
    return out


# The parts of the property information. A report or a site visit sheet can include any selection of them.
PARTS = [
    ("facts", "Key facts (reference, address, tenure, use, managing surveyor)"),
    ("location", "Location"),
    ("description", "Description, construction, storeys, roof and windows"),
    ("services", "Services and solar panels"),
    ("parking", "Parking"),
    ("areas", "Floor areas and how they are made up"),
    ("plans", "Floor plans held"),
    ("titles", "Titles, restrictions and covenants"),
    ("agreements", "Tenancies and other agreements: summary table"),
    ("agreement_terms", "Tenancies and other agreements: main terms of each"),
    ("cases", "Other open cases"),
]
ALL_PARTS = [key for key, _label in PARTS]
_SERVICE_LABELS = {"Mains gas", "Electricity", "Mains water", "Drainage", "Solar panels", "Services notes"}
_SITE_LABELS = {"Location", "Description"}


class Gathered:
    """The property with its family, agreements and titles, read once for all the sections."""

    def __init__(self, prop, case=None):
        self.prop, self.case = prop, case
        self.parts, self.ancestors = family(prop)
        self.leases = list(agreements(prop, self.parts, self.ancestors))
        self.titles = list(prop.titles.all())


def _rows_for(prop, wanted):
    """The recorded facts about a property that belong to the wanted parts, other than the free text."""
    rows = []
    for label, value in prop.physical_rows():
        if label in _SITE_LABELS:
            continue
        if label in _SERVICE_LABELS:
            part = "services"
        elif label == "Parking":
            part = "parking"
        else:
            part = "description"
        if part in wanted:
            rows.append((label, value))
    return rows


def _costs(prop):
    cost = prop.latest_cost()
    if not cost:
        return ""
    parts = [f"running cost £{cost.running_cost:,.0f}" if cost.running_cost is not None else "",
             f"rates £{cost.rates:,.0f}" if cost.rates is not None else ""]
    return f"{cost.year_label()}: " + ", ".join(x for x in parts if x)


def _facts(g, wanted):
    prop = g.prop
    return _table([
        ("Reference", prop.reference), ("Name", prop.name), ("Type", prop.get_property_type_display()),
        ("Address", prop.address), ("UPRN", prop.uprn),
        ("Part of", ", ".join(f"{a.reference} {a.name}" for a in g.ancestors)),
        ("Tenure", prop.get_tenure_display()), ("Title numbers", ", ".join(str(t) for t in g.titles)),
        ("Holding purpose", prop.get_holding_purpose_display()),
        ("Portfolio", prop.portfolio.name if prop.portfolio_id else ""),
        ("Occupation", prop.get_occupation_display()),
        ("Use", prop.use_text()),
        ("Vacancy", prop.vacancy_text()),
        ("Acquired", date_format(prop.acquired_on, "j F Y") if prop.acquired_on else ""),
        ("Designations", "; ".join(f"{label}: {value}" for label, value in prop.designation_rows())),
        ("Planned disposal", "; ".join(f"{label}: {value}" for label, value in prop.planned_disposal_rows())),
        ("Running costs and rates", _costs(prop)),
        ("Managing surveyor", _name(prop.managing_surveyor)),
        ("Grid reference", f"{prop.easting}, {prop.northing}" if prop.easting else ""),
    ]) + [""]


def _location(g, wanted):
    return _para(g.prop.location_description) if g.prop.location_description else [MISSING, ""]


def _description(g, wanted):
    """The property and then each building or part in turn, with whichever of description, services and parking
    are wanted."""
    prop, out = g.prop, []
    text = "description" in wanted
    if text:
        out += _para(prop.building_description) if prop.building_description else [MISSING, ""]
    rows = _rows_for(prop, wanted)
    if rows:
        out += _table(rows) + [""]
    elif not text:
        out += [MISSING, ""]
    for part, _depth in g.parts:
        rows = _rows_for(part, wanted)
        if not (part.property_type == Property.PropertyType.BUILDING or rows
                or (text and part.building_description)):
            continue
        out += [f"## {part.get_property_type_display()}: {part.reference} {part.name}", ""]
        if text and part.location_description:
            out += _para(part.location_description)
        if text and part.building_description:
            out += _para(part.building_description)
        out += (_table(rows) + [""]) if rows else ([MISSING, ""] if not (text and part.building_description) else [])
    return out


def _areas(g, wanted):
    prop, out = g.prop, []
    own = [("Gross internal area (GIA)", _area(prop.gia_sqm)), ("Net internal area (NIA)", _area(prop.nia_sqm)),
           ("Gross external area (GEA)", _area(prop.gea_sqm))]
    own = [(label, value) for label, value in own if value]
    breakdown = prop.area_breakdown()
    if breakdown and breakdown["gia"] and not prop.gia_sqm:
        own.insert(0, ("Gross internal area (GIA), total of the buildings", _area(breakdown["gia"])))
    if own:
        basis = "; ".join(x for x in (
            str(prop.get_area_standard_display()), str(prop.get_area_source_display()).lower(),
            _date(prop.areas_measured_on)) if x)
        out += _table(own + [("Basis of measurement", basis or MISSING)]) + [""]
    elif not breakdown:
        out += [MISSING, ""]
    if breakdown:
        out += [_head("Part", "Type", "Occupation", "NIA m²", "GIA m²")]
        for part, depth in breakdown["parts"]:
            out.append(_row(("– " * (depth - 1)) + f"{part.reference} {part.name}", part.get_property_type_display(),
                            part.get_occupation_display(),
                            f"{part.nia_sqm:,.0f}" if part.nia_sqm is not None else "",
                            f"{part.gia_sqm:,.0f}" if part.gia_sqm is not None else ""))
        out += [_row("**Total of lettable parts**", "", "", f"**{breakdown['leaf_nia']:,.0f}**",
                     f"**{breakdown['leaf_gia']:,.0f}**"), ""]
        if breakdown["net_to_gross"]:
            out += [f"Net to gross: {breakdown['net_to_gross']}%.", ""]
    return out


def _plans(g, wanted):
    plans = [(g.prop, plan) for plan in g.prop.plans.all()]
    plans += [(part, plan) for part, _d in g.parts for plan in part.plans.all()]
    if not plans:
        return ["No floor plans are held.", ""]
    out = [_head("Plan", "Of", "File", "Date", "Notes")]
    out += [_row(plan.title, owner.name, plan.file_type(), _date(plan.drawn_on), plan.notes) for owner, plan in plans]
    return out + ["", "The plans are held in PHAEMA on each property's page.", ""]


def _titles(g, wanted):
    if not g.titles:
        return ["No title is linked to this property.", ""]
    out = []
    for t in g.titles:
        out += _table([("Title", str(t)), ("Tenure", t.get_tenure_display()),
                       ("Class of title", t.get_title_class_display()),
                       ("Restrictions, covenants and rights", t.restrictions_and_covenants)]) + [""]
    return out


def _term(lease):
    return f"{_date(lease.term_start)} to {_date(lease.term_end) or 'periodic'}"


def _agreement_terms(lease):
    breaks = "; ".join(
        f"{_date(b.break_date)} ({b.get_exercisable_by_display().lower()}"
        + (f", {b.notice_months} months' notice" if b.notice_months else "") + ")" for b in lease.breaks.all())
    review = str(lease.get_review_basis_display())
    if lease.next_review_date:
        review = f"{review}; next review {_date(lease.next_review_date)}"
        if lease.time_of_essence:
            review += " (time is of the essence)"
    pairs = [
        ("Council is", "Landlord" if lease.direction == "out" else "Tenant"),
        ("Agreement", lease.get_agreement_type_display()), ("Premises", _premises(lease)),
        ("Date of agreement", _date(lease.lease_date)), ("Term", _term(lease)),
        ("Security of tenure", lease.get_security_of_tenure_display()),
        ("Rent", " ".join(x for x in (_money(lease.annual_rent) + " a year" if lease.annual_rent is not None
                                      else "", str(lease.get_rent_frequency_display()).lower(),
                                      "plus VAT" if lease.vat_chargeable else "") if x)),
        ("Rent review", review), ("Break options", breaks),
        ("Repairs", lease.get_repairing_display()), ("Insurance", lease.get_insurance_display()),
        ("Service charge", "Payable" if lease.service_charge_payable else ""),
        ("Permitted use", lease.permitted_use), ("Assignment and subletting", lease.alienation),
        ("Alterations", lease.alterations), ("Incentives", lease.incentives),
        ("Special rights", lease.special_rights),
    ]
    return _table([(label, value) for label, value in pairs if _cell(value)]) + [""]


def _agreements(g, wanted):
    if not g.leases:
        return ["No current tenancies or other agreements are recorded.", ""]
    out = []
    if "agreements" in wanted:
        total = sum((lease.annual_rent or Decimal("0") for lease in g.leases
                     if lease.direction == "out" and lease.status in ("current", "holding_over")), Decimal("0"))
        out += [_head("Agreement", "Party", "Premises", "Term", "Rent a year", "Status")]
        for lease in g.leases:
            out.append(_row(f"{lease.reference} {lease.get_agreement_type_display()}", lease.counterparty.name,
                            _premises(lease), _term(lease), _money(lease.annual_rent), lease.get_status_display()))
        out += ["", f"Total current rent from agreements where the council is landlord: {_money(total)} a year.", ""]
    if "agreement_terms" in wanted:
        for lease in g.leases:
            out += [f"## {lease.reference}: {lease.counterparty.name}", ""] + _agreement_terms(lease)
    return out


def _cases(g, wanted):
    cases = list(open_cases(g.prop, g.parts, g.ancestors, g.leases, exclude=g.case))
    if not cases:
        return ["No other open cases on this property or its agreements.", ""]
    out = [_head("Case", "Type", "About", "Stage", "Owner", "Received")]
    for c in cases:
        stage = c.get_stage_display() + (" (on hold)" if c.status == c.Status.ON_HOLD else "")
        out.append(_row(c.reference, c.case_type.name, c.title, stage, _name(c.owner), _date(c.received_on)))
    return out + [""]


def sections(prop, wanted=None, case=None, gathered=None):
    """(title, lines) for each wanted part of the property information, in report order. Description, services
    and parking share one section, as do the agreements summary and terms."""
    wanted = set(ALL_PARTS if wanted is None else wanted)
    g = gathered or Gathered(prop, case)
    out = []
    if "facts" in wanted:
        out.append(("The property", _facts(g, wanted)))
    if "location" in wanted:
        out.append(("Location", _location(g, wanted)))
    physical = wanted & {"description", "services", "parking"}
    if physical:
        if "description" in physical:
            title = "Description, construction and services" if "services" in physical else "Description and construction"
        else:
            title = " and ".join(x for x in ("Services" if "services" in physical else "",
                                             "parking" if "parking" in physical else "") if x).capitalize()
        out.append((title, _description(g, physical)))
    if "areas" in wanted:
        out.append(("Floor areas", _areas(g, wanted)))
    if "plans" in wanted:
        out.append(("Floor plans", _plans(g, wanted)))
    if "titles" in wanted:
        out.append(("Title", _titles(g, wanted)))
    if wanted & {"agreements", "agreement_terms"}:
        out.append(("Tenancies and other agreements", _agreements(g, wanted)))
    if "cases" in wanted:
        out.append(("Cases in hand", _cases(g, wanted)))
    return out


def build(prop, case=None, user=None, today=None):
    """The whole report as markup text."""
    today = today or date.today()
    g = Gathered(prop, case)
    title = "Initial valuation report" if case is not None else "Property report"
    out = [f"# {title}: {prop.reference} {prop.name}", ""]
    intro = f"Prepared {_date(today)}" + (f" by {_name(user)}" if user else "") + "."
    if case is not None:
        intro += f" Case {case.display_reference}: {case.title} ({case.case_type.name})."
    out += [intro, "",
            "*Compiled from the council's property records as background information. It is not a valuation, and "
            "the details should be checked on inspection.*", ""]
    numbered = sections(prop, case=case, gathered=g)
    if prop.site_hazards:
        numbered.append(("Site hazards", _para(prop.site_hazards)))
    missing = gaps(prop, g.parts)
    if missing:
        numbered.append(("Not yet recorded", [
            "A valuer is likely to ask for these. Add them on the property's page, then open this report again.", "",
            *[f"- {m}" for m in missing], ""]))
    for n, (heading, lines) in enumerate(numbered, 1):
        out += [f"# {n}. {heading}", ""] + lines
    return "\n".join(out)


def _premises(lease):
    return lease.premises_description or ", ".join(p.name for p in lease.properties.all())
