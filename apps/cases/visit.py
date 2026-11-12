# SPDX-License-Identifier: AGPL-3.0-or-later
"""The site visit sheet: what to take on a visit for a case.

Four parts: the case; what to know before visiting (hazards, asbestos, who is there); the parts of the property
record the case type asks for; and the case type's checklist of things to check or record on site, with the
recorded value beside each item it checks. On a site with several buildings the items marked "for each building"
are repeated under each one. It is written in the document library's markup, so the same text makes the phone
page, the print and the Word file. Nothing entered on it is saved.
"""
from datetime import date

from apps.properties import report as r
from apps.properties.models import Property

BOX = "☐"
BLANK = " "


def _short(text, limit=160):
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _own(prop, key):
    """What the record says about one detail of this property, as text. Blank when nothing is recorded."""
    rows = dict(prop.physical_rows())
    if key == "occupation":
        return str(prop.get_occupation_display())
    if key == "use_description":
        return " ".join(x for x in (prop.use_description, f"({prop.use_class})" if prop.use_class else "") if x)
    if key == "building_description":
        return _short(prop.building_description)
    if key == "built":
        return prop.built
    if key == "construction_type":
        return rows.get("Construction", "")
    if key == "storeys":
        return rows.get("Storeys", "")
    if key == "roof":
        return rows.get("Roof", "")
    if key == "window_type":
        return rows.get("Windows", "")
    if key == "parking":
        return rows.get("Parking", "")
    if key == "services":
        return "; ".join(f"{label}: {value}" for label, value in prop.services_rows()
                         if label not in ("Solar panels", "Services notes"))
    if key == "solar_pv":
        return rows.get("Solar panels", "")
    if key == "floor_areas":
        return ", ".join(f"{label} {value:,.0f} m²" for label, value in (
            ("GIA", prop.gia_sqm), ("NIA", prop.nia_sqm), ("GEA", prop.gea_sqm)) if value is not None)
    if key == "site_area_ha":
        return prop.site_area_text()
    if key == "site_hazards":
        return _short(prop.site_hazards)
    return ""


def recorded(prop, key, parts=()):
    """The recorded value for a checklist item: this property's, or failing that the nearest it is part of, or
    failing that what is recorded on the parts within it."""
    if not key:
        return ""
    for candidate in [prop, *reversed(prop.ancestors())]:
        value = _own(candidate, key)
        if value:
            return value
    if key == "floor_areas":
        breakdown = prop.area_breakdown()
        if breakdown and (breakdown["gia"] or breakdown["leaf_nia"]):
            return ", ".join(f"{label} {value:,.0f} m²" for label, value in (
                ("GIA of the buildings", breakdown["gia"]), ("lettable NIA", breakdown["leaf_nia"])) if value)
    within = [(p.name, _own(p, key)) for p, _depth in parts]
    within = [f"{name}: {value}" for name, value in within if value]
    if within:
        return "; ".join(within[:4]) + ("; and others" if len(within) > 4 else "")
    return "Not recorded"


def _write_in(labels):
    """Rows with an empty cell to write in."""
    return ["| " + label + " | " + BLANK + " |" for label in labels]


def _answer(item):
    if item.kind == item.Kind.TICK:
        return BOX
    if item.kind == item.Kind.YES_NO:
        return f"{BOX} Yes   {BOX} No"
    if item.kind == item.Kind.CHOICE:
        return "   ".join(f"{BOX} {c.strip()}" for c in item.choices.split(",") if c.strip())
    return BLANK


def _checklist(items, prop, parts=()):
    """The items as tables, one for each heading in the order the headings first appear."""
    out, heading = [], None
    for item in items:
        if item.heading != heading or not out:
            if out:
                out.append("")
            heading = item.heading
            out.append(r._head(heading or "Check", "Recorded", "On site"))
        label = r._cell(item.label) + (f" *{r._cell(item.guidance)}*" if item.guidance else "")
        out.append("| " + " | ".join((label, r._cell(recorded(prop, item.checks, parts)) or BLANK, _answer(item)))
                   + " |")
    return out + [""] if out else []


def buildings_of(prop, parts):
    """The buildings a site visit covers one by one: the buildings within the property, when there are any."""
    return [p for p, _depth in parts if p.property_type == Property.PropertyType.BUILDING]


def _case_part(case, prop):
    party = case.party or (case.lease.counterparty if case.lease_id else None)
    contact = ""
    if party:
        contact = "; ".join(x for x in (party.name, party.contact_name, party.phone, party.email) if x)
    stage = case.get_stage_display() + (" (on hold)" if case.status == case.Status.ON_HOLD else "")
    pairs = [
        ("Case", case.display_reference), ("Type", case.case_type.name), ("About", case.title), ("Stage", stage),
        ("Case owner", r._name(case.owner)), ("Received", r._date(case.received_on)),
        ("Target date", r._date(case.target_date)),
        ("Applicant or tenant", contact), ("Their reference", case.applicant_reference),
        ("Agreement", f"{case.lease.reference} {case.lease.get_agreement_type_display()}" if case.lease_id else ""),
        ("Property", f"{prop.reference} {prop.name}"), ("Address", prop.address),
        ("Managing surveyor", r._name(prop.managing_surveyor)),
    ]
    return r._table([(label, value) for label, value in pairs if r._cell(value)]) + [""]


def _before(prop, gathered):
    from apps.compliance.safety import info

    safety = info(prop)
    out = []
    hazards = list(safety["hazards"])
    hazards += [(p, p.site_hazards.strip()) for p, _d in gathered.parts if (p.site_hazards or "").strip()]
    if hazards:
        out += ["**Site hazards recorded:**", ""]
        for p, text in hazards:
            out += [f"- {p.reference} {p.name}: {_short(text, 400)}"]
        out.append("")
    else:
        out += ["No site hazards are recorded. Stay alert: add any you find to the property record.", ""]
    if safety["compliance"]:
        asbestos = safety["asbestos"] or {}
        register, certificate = asbestos.get("register"), asbestos.get("certificate")
        if register or certificate:
            bits = []
            if register:
                bits.append(f"register held ({register.title}"
                            + (f", {register.document_date:%B %Y}" if register.document_date else "") + ")")
            if certificate:
                bits.append(f"reviewed {r._date(certificate.issued_on)}")
            out += ["**Asbestos:** " + "; ".join(bits) + ". Read the register in PHAEMA before disturbing anything.", ""]
        else:
            out += ["**Asbestos:** no asbestos information is held. Assume asbestos may be present in buildings "
                    "built before 2000 until checked.", ""]
        if safety["actions"]:
            out += ["**Open compliance actions:**", ""]
            out += [f"- {a.description} ({a.certificate.requirement.kind.name})" for a in safety["actions"]] + [""]
        if safety["tier_a"]:
            out += ["**Higher-risk building.**", ""]
    occupiers = [lease for lease in gathered.leases if lease.direction == "out"
                 and lease.status in ("current", "holding_over")]
    if occupiers:
        out += [r._head("Occupier", "Premises", "Contact", "Phone")]
        out += [r._row(lease.counterparty.name, r._premises(lease), lease.counterparty.contact_name,
                       lease.counterparty.phone) for lease in occupiers]
        out.append("")
    return out


def build(case, user=None, today=None):
    """The sheet as markup text, or None when the case is not about a property."""
    prop = case.main_property
    if prop is None:
        return None
    today = today or date.today()
    gathered = r.Gathered(prop, case)
    items = list(case.case_type.checklist_items.all())
    out = [f"# Site visit sheet: {case.display_reference}", "",
           f"{case.case_type.name}: {case.title}. Prepared {r._date(today)}" + (f" by {r._name(user)}" if user else "")
           + ".", ""]
    out += ["# The case", ""] + _case_part(case, prop)
    out += ["# Before you visit", ""] + _before(prop, gathered)

    sections = r.sections(prop, wanted=case.case_type.visit_parts or [], case=case, gathered=gathered)
    if sections:
        out += ["# The property", "",
                "*From the council's records. Confirm on site and correct the record afterwards.*", ""]
        for heading, lines in sections:
            out += [f"## {heading}", ""] + lines

    out += ["# On site", ""]
    out += _write_in(["Visited by", "Date and time", "Weather", "People met"]) + [""]
    buildings = buildings_of(prop, gathered.parts)
    if not items:
        out += ["This type of case has no checklist. An administrator can add one in Manage data, Case types.", ""]
    elif len(buildings) > 1 or (buildings and buildings[0].pk != prop.pk):
        whole = [i for i in items if not i.each_building]
        each = [i for i in items if i.each_building]
        if whole:
            out += [f"## The visit as a whole: {prop.name}", ""] + _checklist(whole, prop, gathered.parts)
        for building in buildings if each else []:
            out += [f"## {building.reference} {building.name}", ""] + _checklist(each, building)
    else:
        out += _checklist(items, prop, gathered.parts)
    out += _write_in(["Notes", "Measurements", "To follow up"]) + [""]
    return "\n".join(out)
