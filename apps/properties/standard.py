# SPDX-License-Identifier: AGPL-3.0-or-later
"""The estate set out in the layout of the Government Property Data Standard (GovS004-PDS010, version 1.0).

The standard binds central government, not councils, so this is a mapping, not a certificate of compliance: each
column is headed with the standard's field name and reference number, and a last sheet lists the fields PHAEMA does
not hold or that do not apply to a council.

Only what PHAEMA records is exported. Nothing is guessed: a blank cell means not recorded.
"""
import io
import re
from datetime import date

STANDARD = "Government Property Data Standard"
STANDARD_REF = "GovS004-PDS010, version 1.0 (Cabinet Office, 1 February 2023)"
STANDARD_URL = "https://www.gov.uk/government/publications/government-property-data-standard"
GRID = "EPSG:27700 (British National Grid)"
CELL_LIMIT = 32000  # Excel holds 32,767 characters in a cell.

DISPOSAL_METHODS = {  # PHAEMA's value: the standard's term
    "private_treaty": "Private Treaty", "auction": "Auction", "formal_tender": "Formal Tender",
    "informal_tender": "Informal Tender", "development": "Development Agreement", "building": "Building Agreement",
    "community": "Other", "other": "Other",
}
VALUE_TYPES = {"euv": "EUV", "drc": "DRC", "fv": "Other UK", "fv_sale": "Other UK", "historic": "Other UK",
               "other": "Other UK"}
VACANCY = {"available": "Available", "under_offer": "Under Offer", "underlet": "Underlet", "withdrawn": "Withdrawn"}

# Fields of the standard that this export leaves out, and why. (reference, field, position, note)
NOT_EXPORTED = [
    ("1.1.0009", "Region", "Not held", "One value for the whole council. Add it by hand if needed."),
    ("1.1.0010", "Country", "Not held", "One value for the whole council. Add it by hand if needed."),
    ("1.1.0013", "Local Authority", "Not held",
     "The authority whose area the property is in: usually the council itself. Add it by hand if needed."),
    ("1.1.0015", "Secondary Property Number", "Not held", "Unit numbers are part of the unit's name."),
    ("2.1.0002", "Floor area by tenure", "Worked out", "Each property row has its own tenure and floor area."),
    ("2.2.0011", "BREEAM Rating", "Not held", ""),
    ("2.2.0012", "BREEAM Certificate Reference", "Not held", ""),
    ("2.2.0014", "Physical Constraints", "Not held",
     "Hazards for visitors and designation notes are recorded, but not constraints as the standard means them."),
    ("8.4.0001", "DEC Building Rating", "Partly",
     "A Display Energy Certificate is recorded with one rating, exported as the operational rating."),
    ("8.4.0005", "DEC Operational Rating Value", "Not held", "The letter is recorded, not the number."),
    ("8.4.0006", "DEC Property Reference", "Not held", ""),
    ("8.4.0009", "EPC Property Reference", "Not held", ""),
    ("8.4.0010", "EPC Property Rating Value", "Not held", "The letter is recorded, not the number."),
    ("8.4.0015", "Out of Scope Reason for DEC", "Not held", ""),
    ("8.4.0016", "Out of Scope Reason for EPC", "Not held", ""),
    ("6.0.0010", "Actual Break Date", "Not held", "A break that is used ends the agreement: see its end date."),
    ("6.0.0013", "Break Penalty", "Partly", "Written in the break's conditions, not as a figure."),
    ("6.0.0016", "PFI End Date", "Not held", ""),
    ("5.0.0004", "Capital Expenditure", "Partly",
     "Project budgets and job costs are recorded, but not totalled for each property here."),
    ("5.0.0005", "Unitary Charge", "Not held", ""),
    ("7.0.0001", "Total Operational Costs", "Not held", "Running costs are exported under 7.0.0002."),
    ("4.2.0003", "Status of Sale", "Partly", "Progress is on the disposal case, not a field."),
    ("4.2.0004", "Date Disposal Receipt Claimed", "Does not apply", "A central government procedure."),
    ("4.2.0007", "40-day Expiry Status", "Does not apply", "A central government procedure."),
    ("4.2.0013", "Total Surplus Area", "Worked out", "The land area of each surplus property is on its row."),
    ("4.2.0014", "Estimated Housing Capacity", "Not held", ""),
    ("4.2.0015", "Cost of Maintaining Surplus Property", "Partly",
     "The running cost of a surplus property is on its row."),
    ("3.2.0002", "Occupying Organisation", "Does not apply", "A vacant space has no occupier."),
    ("1.2.0001", "Space Occupier Contact Name", "Held, not exported",
     "Tenants' contact details are personal data and are left out."),
    ("1.2.0006", "Space Occupier Contact Email", "Held, not exported",
     "Tenants' contact details are personal data and are left out."),
    ("1.2.0002", "Organisation Contact Name", "Held, not exported",
     "The managing surveyor is recorded; names are left out of this export."),
    ("1.2.0005", "Organisation Contact Email", "Held, not exported", ""),
    ("1.3.0002", "Organisation Identifier", "Not held", ""),
    ("1.3.0009", "Parent Organisation", "Does not apply", ""),
    ("2.3.0002", "Security Classification", "Partly",
     "A property can be marked \"exclude from open data\": see the last column of the Properties sheet."),
    ("2.3.0004", "Reason for archiving a Record", "Partly", "See the disposal columns."),
    ("FMS002-2", "FM Asset ID", "Not held", "PHAEMA's own record number is given instead."),
    ("FMS002-8", "FM Asset Criticality", "Not held", ""),
    ("FMS002-9", "FM Asset Maintainer", "Partly", "The contractor is on the planned task, not the component."),
    ("FMS002-19", "FM Asset Beyond Economic Repair", "Partly", "Condition D means life expired."),
    ("FMS002-20", "FM Asset Operational Status", "Not held", ""),
    ("FMS002-23", "Last FM Inspection Date", "Partly", "On planned tasks, not the component."),
    ("FMS002-24", "Next FM Inspection Date", "Partly", "On planned tasks, not the component."),
    ("FMS002-25", "FM Inspection Report ID", "Not held", ""),
]


def _year(value):
    return value.year if value else ""


def _yes_no(value):
    return {"yes": "Yes", "no": "No"}.get(value, "")


def _listed(prop):
    if not prop.listed_building:
        return ""
    return "No" if prop.listed_building == "no" else f"Yes: {prop.get_listed_building_display()}"


def _split_address(line):
    """('12A', 'High Street') from '12A High Street'; ('', line) when it does not start with a number."""
    match = re.match(r"^\s*(\d+[A-Za-z]?(?:\s?-\s?\d+[A-Za-z]?)?)[,\s]+(.+)$", line or "")
    return (match.group(1), match.group(2)) if match else ("", line or "")


def _floor_area(prop):
    """The floor area to report and what it is: gross internal first, as the measure most often held."""
    for value, label in ((prop.gia_sqm, "GIA"), (prop.nia_sqm, "NIA"), (prop.gea_sqm, "GEA")):
        if value is not None:
            basis = prop.get_area_standard_display() if prop.area_standard else ""
            return value, f"{label} ({basis})" if basis else label
    return "", ""


def _boundary(prop):
    if not prop.boundary:
        return ""
    wkt = prop.boundary.wkt
    return wkt if len(wkt) <= CELL_LIMIT else "Held, too long for a cell: use the map download"


def _surplus(prop):
    if not prop.holding_purpose:
        return ""
    return "Yes" if prop.holding_purpose in ("surplus", "held_for_sale") else "No"


# (heading, reference) for each column of the Properties sheet, in order. A blank reference is PHAEMA's own.
PROPERTY_COLUMNS = [
    ("PHAEMA reference", ""), ("PHAEMA type", ""), ("Part of (PHAEMA reference)", ""),
    ("Organisation", "1.3.0001"), ("Primary Property Name", "1.1.0001"), ("Primary Property Number", "1.1.0005"),
    ("Secondary Property Name", "1.1.0014"), ("Street Name", "1.1.0003"), ("Town", "1.1.0006"),
    ("Postcode", "1.1.0008"), ("Easting", "1.3.0005"), ("Northing", "1.3.0006"),
    ("Coordinate Reference System", "1.3.0007"), ("UPRN", "1.3.0008"), ("Boundary", "1.3.0010"),
    ("Floor Area (sq m)", "2.1.0001"), ("Floor Area Measurement Type", "2.1.0003"), ("Land Area (ha)", "2.1.0005"),
    ("Usage", "2.2.0002"), ("PHAEMA use", ""), ("Listed Building", "2.2.0004"), ("Ancient Monument", "2.2.0005"),
    ("SSSI/ASSI", "2.2.0006"), ("Conservation Area", "2.2.0007"), ("Construction Date (year)", "2.2.0008"),
    ("Acquisition Date (year)", "2.2.0009"), ("Building Condition", "4.1.0004"),
    ("Building Condition date", "4.1.0005"), ("EPC Property Rating", "8.4.0008"),
    ("EPC Certificate Reference", "8.4.0011"), ("EPC Issue Date", "8.4.0014"), ("EPC Expiry Date", "8.4.0012"),
    ("DEC Operational Rating", "8.4.0004"), ("DEC Certificate Reference", "8.4.0002"),
    ("DEC Certificate Issue Date", "8.4.0013"), ("DEC Expiry Date", "8.4.0003"), ("Title Number", "1.3.0004"),
    ("Tenure", "6.0.0001"), ("Value (£)", "4.1.0001"), ("Value Type", "4.1.0002"), ("Valuation Date", "4.1.0003"),
    ("Rates (£ a year)", "5.0.0003"), ("Total Property/Space Running Costs (£)", "7.0.0002"),
    ("Year of rates and running costs", ""), ("Surplus Status", "2.2.0001"), ("Future Disposal Date", "4.2.0001"),
    ("Future Disposal Value (£)", "4.2.0008"), ("Reason for Disposal", "4.2.0011"), ("Disposal Method", "4.2.0005"),
    ("Disposal Date", "4.2.0002"), ("Disposal Proceeds (£)", "4.2.0006"), ("Excluded from open data", ""),
]

CONTRACT_COLUMNS = [
    ("PHAEMA property reference", ""), ("Primary Property Name", "1.1.0001"), ("PHAEMA agreement reference", ""),
    ("Tenure", "6.0.0001"), ("Landlord Name", "6.0.0004"), ("Licence Type", "6.0.0007"),
    ("Rent (£ a year)", "6.0.0003"), ("Payment Frequency", "6.0.0015"), ("Start Date", "6.0.0020"),
    ("Expiry Date", "6.0.0008"), ("Earliest Break Date", "6.0.0009"), ("Last Break Date", "6.0.0012"),
    ("Break Notice Term (months)", "6.0.0011"), ("Post-Expiry Status", "6.0.0014"),
    ("Rent Review Frequency (years)", "6.0.0017"), ("Review Date", "6.0.0019"), ("Repair Liability", "6.0.0018"),
]

VACANT_COLUMNS = [
    ("PHAEMA reference", ""), ("Primary Property Name", "1.1.0001"),
    ("Vacant Space Floor Area (sq m)", "3.1.0001"), ("Floor Area Measurement Type", "2.1.0003"),
    ("Vacation Date", "3.1.0002"), ("Available Start Date", "3.1.0003"), ("Availability End Date", "3.1.0007"),
    ("Vacant Space Status", "3.1.0004"), ("Description", "3.1.0005"), ("Use Classification", "3.2.0008"),
]

ASSET_COLUMNS = [
    ("PHAEMA property reference", ""), ("PHAEMA component number", ""), ("FM Asset Name", "FMS002-1"),
    ("System/Element Group", "FMS002-3"), ("FM Asset Classification Code", "FMS002-6"),
    ("FM Asset Classification Description", "FMS002-7"), ("Room / Zone", "FMS002-17"),
    ("FM Asset Condition", "FMS002-18"), ("Date of last FM condition survey", "FMS002-21"),
    ("Remain Life Expectancy (Years)", "FMS002-22"), ("Quantity of FM Assets", "FMS002-26"),
    ("Unit of Measure", "FMS002-27"),
]


def gather(user=None, today=None):
    """Everything the export needs, as plain rows: {'properties': [...], 'contracts': [...], ...}.

    Valuations, energy certificates and components are included only where their module is switched on and, when a
    user is given, that person may see the whole of it.
    """
    from apps.core.access import scope
    from apps.core.models import ModuleSettings
    from apps.leases.models import Lease

    from .models import Property

    today = today or date.today()
    settings = ModuleSettings.load()
    organisation = settings.organisation_name

    def included(module, flag):
        return scope(user, module, settings) == "full" if user is not None else getattr(settings, flag)

    compliance = included("compliance", "compliance_enabled")
    valuation = included("valuations", "valuation_enabled")
    maintenance = included("maintenance", "maintenance_enabled")
    props = list(Property.objects.select_related("parent", "use_type").prefetch_related("titles", "costs")
                 .order_by("reference"))
    parents = {p.parent_id for p in props if p.parent_id}

    certificates = {}
    if compliance:
        from apps.compliance.models import Certificate

        for cert in (Certificate.objects.filter(requirement__kind__code__in=("epc", "dec"))
                     .select_related("requirement__kind").order_by("issued_on")):
            certificates[(cert.requirement.property_id, cert.requirement.kind.code)] = cert  # the latest wins

    valuations = {}
    if valuation:
        from apps.valuations.models import Valuation

        for val in Valuation.objects.filter(status="accepted", value__isnull=False).order_by("valuation_date"):
            valuations[val.property_id] = val

    rows = []
    for p in props:
        unit = p.property_type == "unit" and p.parent is not None
        addressed = p.parent if unit and not p.address_line_1 else p
        number, street = _split_address(addressed.address_line_1)
        area, area_type = _floor_area(p)
        epc, dec = certificates.get((p.pk, "epc")), certificates.get((p.pk, "dec"))
        val = valuations.get(p.pk)
        cost = p.latest_cost()
        has_point = p.easting is not None
        rows.append([
            p.reference, p.get_property_type_display(), p.parent.reference if p.parent else "",
            organisation, p.parent.name if unit else p.name, number, p.name if unit else "", street,
            p.town or addressed.town, p.postcode or addressed.postcode,
            p.easting if has_point else "", p.northing if has_point else "", GRID if has_point else "",
            p.uprn, _boundary(p), area, area_type, p.site_area_ha if p.site_area_ha is not None else "",
            p.use_type.standard_usage if p.use_type else "", p.use_text(),
            _listed(p), _yes_no(p.scheduled_monument), _yes_no(p.sssi), _yes_no(p.conservation_area),
            p.built_year or "", _year(p.acquired_on), p.condition_grade, p.condition_surveyed_on or "",
            epc.rating if epc else "", epc.reference if epc else "", epc.issued_on if epc else "",
            (epc.expires_on or "") if epc else "",
            dec.rating if dec else "", dec.reference if dec else "", dec.issued_on if dec else "",
            (dec.expires_on or "") if dec else "",
            ", ".join(t.title_number for t in p.titles.all() if t.title_number),
            p.get_tenure_display() if p.tenure in ("freehold", "leasehold") else "",
            val.value if val else "", VALUE_TYPES.get(val.basis, "") if val else "",
            val.valuation_date if val else "",
            cost.rates if cost and cost.rates is not None else "",
            cost.running_cost if cost and cost.running_cost is not None else "",
            cost.year_label() if cost else "",
            _surplus(p), "" if p.disposed_on else (p.disposal_expected_on or ""),
            "" if p.disposed_on or p.disposal_expected_value is None else p.disposal_expected_value,
            p.disposal_reason, DISPOSAL_METHODS.get(p.disposal_method, ""),
            p.disposed_on or "", p.disposal_price if p.disposal_price is not None else "",
            "Yes" if p.exclude_from_publication else "No",
        ])

    contracts = []
    held = (Lease.objects.filter(direction="in").exclude(status__in=("proposed", "ended"))
            .select_related("counterparty").prefetch_related("properties", "breaks").order_by("reference"))
    for lease in held:
        every = sorted(lease.breaks.all(), key=lambda b: b.break_date)
        breaks = [b for b in every if b.break_date >= today] or every
        for p in lease.properties.all():
            contracts.append([
                p.reference, p.name, lease.reference,
                "Leasehold" if lease.agreement_type in ("lease", "afl", "fbt", "taw") else "Other",
                lease.counterparty.name, lease.get_agreement_type_display(),
                lease.annual_rent if lease.annual_rent is not None else "", lease.get_rent_frequency_display(),
                lease.term_start or "", lease.term_end or "",
                breaks[0].break_date if breaks else "", breaks[-1].break_date if breaks else "",
                breaks[0].notice_months if breaks and breaks[0].notice_months is not None else "",
                "Holding over" if lease.status == "holding_over" else "",
                lease.review_interval_years or "", lease.next_review_date or "",
                lease.get_repairing_display() if lease.repairing else "",
            ])

    vacant = []
    for p in props:
        if p.occupation != "vacant" or p.pk in parents or p.disposed_on:
            continue
        area, area_type = (p.nia_sqm, "NIA") if p.nia_sqm is not None else _floor_area(p)
        vacant.append([
            p.reference, p.name, area if area is not None else "", area_type, p.vacant_since or "",
            p.available_from or "", p.available_until or "", VACANCY.get(p.vacancy_status, ""),
            p.building_description or p.use_text(), p.use_type.standard_usage if p.use_type else "",
        ])

    assets = []
    if maintenance:
        from apps.maintenance.models import Component

        for c in Component.objects.select_related("property").order_by("property__reference", "pk"):
            remaining = c.remaining_life()
            assets.append([
                c.property.reference, c.pk, c.name, c.get_category_display(), c.uniclass or c.nrm3,
                ("Uniclass" if c.uniclass else "NRM 3") if (c.uniclass or c.nrm3) else "", c.location,
                c.condition, c.condition_on or "", remaining if remaining is not None else "",
                c.quantity if c.quantity is not None else "", c.unit,
            ])

    return {"organisation": organisation, "today": today, "properties": rows, "contracts": contracts,
            "vacant": vacant, "assets": assets, "maintenance": maintenance, "compliance": compliance,
            "valuation": valuation}


def coverage(data):
    """How much of each mapped property column is filled in: [(heading, reference, filled, of, percent)]."""
    rows, out = data["properties"], []
    live = [r for r in rows if not r[PROPERTY_HEADINGS.index("Disposal Date")]]
    for i, (heading, ref) in enumerate(PROPERTY_COLUMNS):
        if not ref or heading in ("Disposal Date", "Disposal Proceeds (£)"):  # current records only
            continue
        filled = sum(1 for r in live if r[i] not in ("", None))
        out.append((heading, ref, filled, len(live), round(100 * filled / len(live)) if live else 0))
    return out


PROPERTY_HEADINGS = [heading for heading, _ref in PROPERTY_COLUMNS]


def _header(heading, ref):
    return f"{heading} [{ref}]" if ref else heading


def workbook(data):
    """The export as an Excel workbook, returned as bytes."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    bold, fill = Font(bold=True), PatternFill("solid", fgColor="DDE5ED")
    wrap = Alignment(wrap_text=True, vertical="top")

    about = wb.active
    about.title = "About"
    organisation = data["organisation"] or "This council"
    lines = [
        (f"{organisation}: the estate in the layout of the {STANDARD}", True),
        (f"Produced from PHAEMA on {data['today']:%-d %B %Y}.", False),
        ("", False),
        (f"Standard: {STANDARD}, {STANDARD_REF}.", False),
        (STANDARD_URL, False),
        ("", False),
        ("What this is", True),
        ("PHAEMA's property records mapped to the standard's fields. Each column is headed with the standard's "
         "field name and, in square brackets, its reference number. Columns with no number are PHAEMA's own, "
         "added so a row can be traced back.", False),
        ("The standard binds central government bodies, not councils. This is a mapping to it, not a certificate "
         "of compliance.", False),
        ("A blank cell means the fact is not recorded. Nothing is estimated or filled in by default.", False),
        ("", False),
        ("Sheets", True),
        (f"Properties: {len(data['properties'])} records. Every site, building, unit and parcel of land, "
         "including those disposed of. A unit's primary name is its building; its own name is the secondary name.",
         False),
        (f"Contracts: {len(data['contracts'])} rows. Agreements under which the council holds property as tenant "
         "or licensee, one row for each property in each. Lettings by the council are not part of the standard's "
         "contract fields: they are in PHAEMA's reports.", False),
        (f"Vacant spaces: {len(data['vacant'])} rows. Vacant property with no parts of its own.", False),
        ((f"FM assets: {len(data['assets'])} rows. Building components from the maintenance module, in the layout "
          "of standard FMS002.") if data["maintenance"] else
         "FM assets: empty, because maintenance is switched off or not open to the person who produced this.",
         False),
        ("Fields not exported: the standard's fields that PHAEMA does not hold, holds only partly, or that do not "
         "apply to a council, with the reason for each.", False),
        ("", False),
        ("Notes", True),
        ("Grid references are British National Grid eastings and northings. Boundaries are in well-known text "
         "(WKT) on the same grid.", False),
        ("Floor area is the gross internal area where held, otherwise net internal, otherwise gross external; the "
         "next column says which, and the measuring standard.", False),
        ("Value is the latest valuation accepted for the accounts." if data["valuation"] else
         "Value columns are empty because asset valuation is switched off or not open to the person who produced "
         "this.", False),
        ("Energy certificates are the latest recorded for each property." if data["compliance"] else
         "Energy certificate columns are empty because compliance is switched off or not open to the person who "
         "produced this.", False),
        ("Usage is the standard's term matched to the council's own list of uses under Manage data, Property "
         "uses. The council's own wording is in the next column.", False),
        ("Tenants' and officers' names and contact details are left out.", False),
    ]
    for text, heading in lines:
        about.append([text])
        cell = about.cell(row=about.max_row, column=1)
        cell.alignment = wrap
        if heading:
            cell.font = bold
    about.column_dimensions["A"].width = 110

    def sheet(title, columns, rows):
        ws = wb.create_sheet(title)
        ws.append([_header(h, r) for h, r in columns])
        for cell in ws[1]:
            cell.font, cell.fill, cell.alignment = bold, fill, wrap
        for row in rows:
            ws.append(row)
        ws.freeze_panes = "B2"
        ws.auto_filter.ref = ws.dimensions
        ws.row_dimensions[1].height = 48
        for i in range(1, len(columns) + 1):
            ws.column_dimensions[get_column_letter(i)].width = 18
        return ws

    sheet("Properties", PROPERTY_COLUMNS, data["properties"])
    sheet("Contracts", CONTRACT_COLUMNS, data["contracts"])
    sheet("Vacant spaces", VACANT_COLUMNS, data["vacant"])
    sheet("FM assets", ASSET_COLUMNS, data["assets"])
    missing = sheet("Fields not exported", [("Reference", ""), ("Field", ""), ("Position", ""), ("Note", "")],
                    [list(row) for row in NOT_EXPORTED])
    missing.column_dimensions["B"].width = 40
    missing.column_dimensions["D"].width = 100

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
