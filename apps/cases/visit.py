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
        return prop.use_text()
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
        return ", ".join(f"{label} {value:,.0f} m²" for label, value in prop.area_lines())
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
    gathered = r.Gathered(prop, case, user)
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


# ------------------------------------------------------------------ level B: a visit filled in and saved

def _plan(case, prop, gathered):
    """[(building or None, [items])]: the checklist as it is answered, a group for the visit as a whole and, on a
    site with several buildings, a group for each building."""
    items = list(case.case_type.checklist_items.all())
    buildings = buildings_of(prop, gathered.parts)
    if items and (len(buildings) > 1 or (buildings and buildings[0].pk != prop.pk)):
        whole = [i for i in items if not i.each_building]
        each = [i for i in items if i.each_building]
        groups = [(None, whole)] if whole else []
        groups += [(b, each) for b in buildings] if each else []
        return groups
    return [(None, items)] if items else []


def start_visit(case, user, today=None):
    """Start a visit for the case: one answer for each checklist item (and building), with the recorded value as
    it stands today."""
    from .models import SiteVisit, SiteVisitAnswer

    prop = case.main_property
    if prop is None:
        return None
    gathered = r.Gathered(prop, case, user)
    visit = SiteVisit.objects.create(case=case, property=prop, visited_by=user, visited_on=today or date.today(),
                                     created_by=user)
    answers, n = [], 0
    for building, items in _plan(case, prop, gathered):
        for item in items:
            n += 1
            value = recorded(building, item.checks) if building else recorded(prop, item.checks, gathered.parts)
            answers.append(SiteVisitAnswer(
                visit=visit, item=item, building=building, heading=item.heading, label=item.label,
                guidance=item.guidance, kind=item.kind, choices=item.choices, checks=item.checks,
                recorded=(value or "")[:400], order=n))
    # The visit's creation is logged; its blank question rows are not, one by one. Answers people record are.
    SiteVisitAnswer.objects.bulk_create(answers)
    return visit


def visit_sections(visit):
    """[{"key", "title", "answers"}]: the answers grouped as they are filled in, a section for the visit as a whole
    and one for each building. Each section is saved on its own, so a dropped connection loses little."""
    groups = {}
    for a in visit.answers.select_related("building").prefetch_related("photos"):
        key = str(a.building_id or 0)
        if key not in groups:
            title = f"{a.building.reference} {a.building.name}" if a.building_id else (
                f"The visit as a whole: {visit.property.name}" if visit.answers.exclude(building=None).exists()
                else visit.property.name)
            groups[key] = {"key": key, "title": title, "answers": []}
        groups[key]["answers"].append(a)
    return list(groups.values())


def answer_from(post, a):
    """The value for one answer from a submitted form, checked against its kind."""
    raw = (post.get(f"v{a.pk}") or "").strip()
    if a.kind == "tick":
        return "checked" if raw else ""
    if a.kind == "yes_no":
        return raw if raw in ("yes", "no") else ""
    if a.kind == "choice":
        return raw if raw in a.choice_list() else ""
    return raw[:2000]


def progress(visit):
    """(answered, total)."""
    answers = list(visit.answers.values_list("value", flat=True))
    return sum(1 for v in answers if v), len(answers)


def build_record(visit, user=None, today=None):
    """The finished (or draft) visit as markup: the record of the inspection."""
    case = visit.case
    today = today or date.today()
    answered, total = progress(visit)
    state = (f"Finished {r._date(visit.finished_on)}" if visit.is_finished
             else f"In progress at {r._date(today)}")
    out = [f"# Site visit record: {case.display_reference}", "",
           f"{case.case_type.name}: {case.title}. {state}.", ""]
    facts = [("Property", f"{visit.property.reference} {visit.property.name}"), ("Address", visit.property.address),
             ("Visited by", r._name(visit.visited_by)), ("Date", r._date(visit.visited_on)), ("Time", visit.time),
             ("Weather", visit.weather), ("People met", visit.people_met),
             ("Checklist", f"{answered} of {total} items answered"), ("Photos", str(visit.photos.count()))]
    out += r._table([(k, v) for k, v in facts if r._cell(v)]) + [""]
    for section in visit_sections(visit):
        out += [f"# {section['title']}", ""]
        heading = None
        for a in section["answers"]:
            if a.heading != heading or heading is None:
                if heading is not None:
                    out.append("")
                heading = a.heading
                out.append(r._head(a.heading or "Check", "Recorded", "Found on site", "Note"))
            out.append(r._row(a.label, a.recorded if a.checks else "", a.shown(), a.note))
        out.append("")
    found = differences(visit)
    if found:
        out += ["# Differences from the record", "", r._head("Item", "Property", "Recorded", "Found on site", "Outcome")]
        for a in found:
            outcome = a.get_resolution_display() if a.resolution else "To decide"
            if a.resolution and a.resolved_by:
                outcome += f" ({r._name(a.resolved_by)}, {r._date(a.resolved_at.date())})"
            out.append(r._row(a.label, a.target.reference, a.recorded, a.shown(), outcome))
        out.append("")
    if visit.notes:
        out += ["# General notes", ""] + r._para(visit.notes)
    if visit.follow_up:
        out += ["# To follow up", ""] + r._para(visit.follow_up)
    photos = list(visit.photos.select_related("answer"))
    if photos:
        out += ["# Photos", "", r._head("Photo", "Caption", "About", "Also on the property")]
        out += [r._row(str(n), p.caption, p.answer.label if p.answer_id else "The visit",
                       "Yes" if p.property_photo_id else "No") for n, p in enumerate(photos, start=1)]
        out.append("")
    return "\n".join(out)


# ------------------------------------------------------------------ level B part 2: differences from the record

# The property fields a surveyor can correct for each detail a checklist item checks. Floor areas are the
# check-measure: the measured areas with their standard, source and date.
UPDATES = {
    "occupation": ["occupation"],
    "use_description": ["use_description"],
    "building_description": ["building_description"],
    "built": ["built"],
    "construction_type": ["construction_type", "construction_detail"],
    "storeys": ["storeys", "basement_levels"],
    "roof": ["roof_type", "roof_covering", "roof_detail"],
    "window_type": ["window_type", "window_detail"],
    "parking": ["parking_spaces", "parking"],
    "services": ["mains_gas", "electricity", "mains_water", "drainage", "services_notes"],
    "solar_pv": ["solar_pv", "solar_capacity_kwp"],
    "floor_areas": ["gia_sqm", "nia_sqm", "gea_sqm", "area_standard", "area_source", "areas_measured_on",
                    "areas_measured_by", "areas_method"],
    "floor_areas_ipms": ["ipms1_sqm", "ipms2_sqm", "ipms3_sqm", "ipms3_kind", "ipms_measured_on", "ipms_source",
                         "ipms_measured_by", "ipms_method", "ipms_checked", "ipms_checked_how"],
    "site_area_ha": ["site_area_ha"],
    "site_hazards": ["site_hazards"],
}


def _plain(text):
    return " ".join(str(text or "").lower().replace(",", " ").split())


def is_difference(a):
    """Did the visit find something other than the record? A "no" to an item that checks the record, or a written,
    chosen or measured answer that is not what was recorded."""
    if not a.checks or not a.value or a.checks not in UPDATES:
        return False
    if a.kind == "yes_no":
        return a.value == "no"
    if a.kind == "tick":
        return False
    return _plain(a.value) != _plain(a.recorded)


def differences(visit):
    return [a for a in visit.answers.select_related("building", "resolved_by") if is_difference(a)]


def open_differences(visit):
    return [a for a in differences(visit) if not a.resolution]


def update_fields(key, target=None):
    """The property fields offered for a difference. A check-measure offers the council's chosen basis: the
    Code of Measuring Practice areas, or the IPMS areas."""
    if key == "floor_areas" and target is not None and target.area_basis() == "ipms":
        return UPDATES["floor_areas_ipms"]
    return UPDATES[key]


def update_form_class(key, target=None):
    from django import forms

    from apps.properties.models import Property

    fields = update_fields(key, target)

    class UpdateForm(forms.ModelForm):
        class Meta:
            model = Property
            fields = update_fields(key, target)
            widgets = {"areas_measured_on": forms.DateInput(attrs={"type": "date"}),
                       "ipms_measured_on": forms.DateInput(attrs={"type": "date"})}

    UpdateForm.field_names = fields
    return UpdateForm


def initial_for(a, visit):
    """Starting values for the update form: for a check-measure, the measured source and date of the visit."""
    if a.checks == "floor_areas":
        if a.target.area_basis() == "ipms":
            return {"ipms_source": "survey", "ipms_measured_on": visit.visited_on, "ipms_checked": "yes"}
        return {"area_source": "survey", "areas_measured_on": visit.visited_on}
    return {}


def resolve(a, user, resolution):
    from django.utils import timezone

    a.resolution, a.resolved_by, a.resolved_at = resolution, user, timezone.now()
    a.save(update_fields=["resolution", "resolved_by", "resolved_at"])


def save_record_to_case(visit, user):
    """Keep the finished record as a Word document on the case."""
    from types import SimpleNamespace

    from django.core.files.base import ContentFile

    from apps.documents import merge
    from apps.documents import render as doc_render

    from .models import CaseDocument

    data = doc_render.to_docx(SimpleNamespace(letterhead=True, prescribed_form=""), build_record(visit, user),
                              merge.context(user=user, case=visit.case, prop=visit.property))
    name = f"Site visit {visit.case.reference} {visit.visited_on:%Y-%m-%d}.docx"
    doc = CaseDocument(case=visit.case, description=f"Site visit record, {visit.visited_on:%d %B %Y}",
                       original_filename=name, created_by=user)
    doc.file.save(name, ContentFile(data), save=True)
    return doc
