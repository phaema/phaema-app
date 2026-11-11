# SPDX-License-Identifier: AGPL-3.0-or-later
"""Site and buildings: the physical details, floor plans, and the property and initial valuation reports."""
from datetime import date
from decimal import Decimal
from io import BytesIO

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.cases.models import Case, CaseType
from apps.core.files import validate_plan
from apps.core.roles import ADMINISTRATORS, SURVEYORS, VIEWERS, can_edit
from apps.leases.models import Lease, Party
from apps.properties import report
from apps.properties.models import Property, PropertyPlan

PDF = b"%PDF-1.4 plan"
DWG = b"AC1032" + b"\x00" * 50
DXF = b"  0\nSECTION\n  2\nHEADER\n"


@pytest.fixture
def site(db, make_user):
    sue = make_user("sue", SURVEYORS, first_name="Sue", last_name="Surveyor")
    estate = Property.objects.create(
        reference="T-01", name="Mill Yard", property_type="site", managing_surveyor=sue, tenure="freehold",
        site_area_ha=Decimal("0.25"), location_description="Edge of town, off the A40.",
        building_description="Two blocks around a yard.", parking="Yard parking.", parking_spaces=12)
    block = Property.objects.create(
        reference="T-01-A", name="Block A", property_type="building", parent=estate, managing_surveyor=sue,
        gia_sqm=Decimal("500"), construction_type="portal_frame", storeys=1, basement_levels=1,
        roof_type="flat", roof_covering="single_ply", roof_detail="Renewed 2019", window_type="upvc",
        mains_gas="no", electricity="three", mains_water="yes", drainage="mains", solar_pv="yes",
        solar_capacity_kwp=Decimal("49.50"))
    unit = Property.objects.create(reference="T-01-A1", name="Unit 1", property_type="unit", parent=block,
                                   managing_surveyor=sue, nia_sqm=Decimal("450"), occupation="let")
    Property.objects.create(reference="T-01-B", name="Block B", property_type="building", parent=estate)
    tenant = Party.objects.create(name="Acme Joinery Ltd", party_type="company")
    lease = Lease.objects.create(reference="L-1", agreement_type="lease", counterparty=tenant,
                                 term_start=date(2022, 1, 1), term_end=date(2032, 1, 1), annual_rent=Decimal("24000"),
                                 security_of_tenure="contracted_out", repairing="fri",
                                 permitted_use="Joinery workshop | storage")
    lease.properties.add(unit)
    old = Lease.objects.create(reference="L-0", agreement_type="lease", counterparty=tenant, status="ended",
                               term_start=date(2012, 1, 1), term_end=date(2022, 1, 1))
    old.properties.add(unit)
    return {"sue": sue, "estate": estate, "block": block, "unit": unit, "lease": lease}


# The details

def test_details_read_well(site):
    estate, block = site["estate"], site["block"]
    assert estate.site_area_sqm == Decimal("2500") and estate.site_area_text() == "0.25 ha (2,500 m²)"
    rows = dict(block.physical_rows())
    assert rows["Construction"] == "Steel portal frame"
    assert rows["Storeys"] == "1 plus 1 basement level"
    assert rows["Roof"] == "Flat, Single-ply membrane; Renewed 2019"
    assert rows["Electricity"] == "Three-phase" and rows["Mains gas"] == "No"
    assert rows["Solar panels"] == "Yes, 49.5 kWp"
    assert dict(estate.physical_rows())["Parking"] == "12 spaces. Yard parking."
    assert Property(reference="X", name="X", property_type="land").physical_rows() == []


def test_solar_capacity_needs_solar(site):
    block = site["block"]
    block.solar_pv = "no"
    with pytest.raises(ValidationError):
        block.full_clean()


def test_property_page_shows_details_and_plans(client, site):
    PropertyPlan.objects.create(property=site["block"], title="Ground floor",
                                file=SimpleUploadedFile("ground.dwg", DWG), drawn_on=date(2019, 5, 1))
    client.force_login(site["sue"])
    page = client.get(site["block"].get_absolute_url()).content.decode()
    assert "Site and buildings" in page and "Steel portal frame" in page and "Three-phase" in page
    assert "Ground floor" in page and "AutoCAD DWG" in page
    assert reverse("properties:report", args=[site["block"].pk]) in page
    empty = client.get(site["unit"].get_absolute_url()).content.decode()
    assert "Nothing recorded yet about the location" in empty and "No floor plans held." in empty


# Floor plans

@pytest.mark.parametrize("name,data,ok", [
    ("plan.pdf", PDF, True), ("plan.dwg", DWG, True), ("plan.DXF", DXF, True),
    ("plan.dwg", PDF, False), ("plan.pdf", b"not a pdf", False), ("plan.exe", PDF, False),
    ("plan.dxf", b"MZ\x00\x00SECTION", False),
])
def test_plan_files_are_checked(name, data, ok):
    upload = SimpleUploadedFile(name, data)
    if ok:
        validate_plan(upload)
    else:
        with pytest.raises(ValidationError):
            validate_plan(upload)


def test_plan_keeps_its_name_and_goes_with_the_record(site):
    plan = PropertyPlan.objects.create(property=site["block"], title="Site layout",
                                       file=SimpleUploadedFile("Mill Yard layout.pdf", PDF))
    assert plan.original_filename == "Mill Yard layout.pdf" and plan.file.name.endswith(".pdf")
    assert plan.file_type() == "PDF"
    storage, name = plan.file.storage, plan.file.name
    assert storage.exists(name)
    plan.delete()
    assert not storage.exists(name)


def test_who_can_change_plans(site, make_user):
    plan = PropertyPlan.objects.create(property=site["block"], title="P", file=SimpleUploadedFile("p.pdf", PDF))
    assert can_edit(site["sue"], plan)
    assert not can_edit(make_user("other", SURVEYORS), plan)
    assert not can_edit(make_user("vic", VIEWERS), plan)
    assert site["sue"].has_perm("properties.add_propertyplan")


def test_edit_form_takes_site_area_in_square_metres(client, site, make_user):
    client.force_login(make_user("boss", ADMINISTRATORS))
    url = reverse("admin:properties_property_change", args=[site["estate"].pk])
    form = client.get(url).context["adminform"].form
    assert form.fields["site_area_sqm"].initial == Decimal("2500")
    data = {}
    for name, field in form.fields.items():
        value = form.initial.get(name, field.initial)
        if value is None or value is False:
            continue
        data[name] = getattr(value, "pk", value)
    data["boundary"] = ""
    data.update({"site_area_sqm": "3600", "photos-TOTAL_FORMS": 0, "photos-INITIAL_FORMS": 0,
                 "plans-TOTAL_FORMS": 1, "plans-INITIAL_FORMS": 0, "plans-0-title": "Yard plan",
                 "plans-0-file": SimpleUploadedFile("yard.pdf", PDF),
                 "Title_properties-TOTAL_FORMS": 0, "Title_properties-INITIAL_FORMS": 0})
    response = client.post(url, data)
    assert response.status_code == 302, response.context["adminform"].form.errors
    site["estate"].refresh_from_db()
    assert site["estate"].site_area_ha == Decimal("0.3600")
    assert site["estate"].plans.get().title == "Yard plan"


# The report

@pytest.fixture
def valuation_case(site):
    case_type = CaseType.objects.get(code="asset_valuation")
    return Case.objects.create(case_type=case_type, title="Valuation for the accounts", property=site["estate"],
                               owner=site["sue"])


def test_report_brings_everything_together(site, valuation_case):
    other = Case.objects.create(case_type=CaseType.objects.exclude(group="valuation").first(),
                                title="Alterations to Unit 1", lease=site["lease"], owner=site["sue"])
    closed = Case.objects.create(case_type=other.case_type, title="Old closed matter", property=site["block"],
                                 status="closed")
    PropertyPlan.objects.create(property=site["block"], title="Ground floor", file=SimpleUploadedFile("g.pdf", PDF))
    text = report.build(site["estate"], case=valuation_case, user=site["sue"], today=date(2026, 11, 11))
    assert text.startswith("# Initial valuation report: T-01 Mill Yard")
    assert "Prepared 11 November 2026 by Sue Surveyor." in text and valuation_case.reference in text
    assert "Edge of town, off the A40." in text and "| Site area | 0.25 ha (2,500 m²) |" in text
    # each block has its own part, and a block with nothing recorded says so
    assert "## Building: T-01-A Block A" in text and "| Construction | Steel portal frame |" in text
    assert "## Building: T-01-B Block B" in text
    assert "| Solar panels | Yes, 49.5 kWp |" in text
    # floor areas, including the make-up
    assert "| – T-01-A1 Unit 1 | Lettable unit | Let to a third party | 450 | – |" in text
    assert "| Ground floor | Block A | PDF |" in text
    # current agreements only, with the detail a valuer needs; a "|" in the records cannot break the table
    assert "L-1 Lease" in text and "L-0" not in text
    assert "| Security of tenure | Contracted out of the 1954 Act |" in text and "£24,000 a year" in text
    assert "| Permitted use | Joinery workshop / storage |" in text
    assert "landlord: £24,000 a year" in text
    # cases in hand: open ones on the property, its parts and agreements, but not this case or closed ones
    assert other.reference in text and "Alterations to Unit 1" in text
    assert "Old closed matter" not in text and text.count(valuation_case.reference) == 1
    assert closed.status == "closed"
    # what is missing
    assert "Not yet recorded" in text and "- Block B: construction, storeys, roof, windows" in text
    assert "- Title (no title is linked to this property)" in text


def test_report_without_a_case_is_a_property_report(site):
    text = report.build(site["unit"], today=date(2026, 11, 11))
    assert text.startswith("# Property report: T-01-A1 Unit 1")
    assert "| Part of | T-01 Mill Yard, T-01-A Block A |" in text
    assert "L-1 Lease" in text  # the unit's own tenancy


def test_report_page_and_word_download(client, site, valuation_case, make_user):
    client.force_login(make_user("vic", VIEWERS))
    url = reverse("properties:report", args=[site["estate"].pk]) + f"?case={valuation_case.pk}"
    page = client.get(url)
    html = page.content.decode()
    assert page.status_code == 200 and "Initial valuation report" in html and "Acme Joinery Ltd" in html
    assert "Download as Word" in html
    word = client.get(url + "&format=docx")
    assert word.status_code == 200 and word.content[:2] == b"PK"
    assert "Initial valuation report T-01.docx" in word["Content-Disposition"]
    from docx import Document

    doc = Document(BytesIO(word.content))
    assert any("Initial valuation report: T-01 Mill Yard" in p.text for p in doc.paragraphs)
    assert any("Acme Joinery Ltd" in cell.text for table in doc.tables for row in table.rows for cell in row.cells)


def test_report_needs_sign_in(client, site):
    assert client.get(reverse("properties:report", args=[site["estate"].pk])).status_code == 302


def test_valuation_cases_link_to_the_report(client, site, valuation_case):
    client.force_login(site["sue"])
    link = reverse("properties:report", args=[site["estate"].pk]) + f"?case={valuation_case.pk}"
    assert link in client.get(valuation_case.get_absolute_url()).content.decode()
    other = Case.objects.create(case_type=CaseType.objects.exclude(group="valuation").first(), title="Consent",
                                property=site["estate"], owner=site["sue"])
    assert "Initial valuation report" not in client.get(other.get_absolute_url()).content.decode()


# Imports, exports and demonstration data

def test_import_takes_the_new_columns():
    from apps.properties import importer

    headings = [h for h, _f, _r, _g in importer.COLUMNS]
    for heading in ("Construction", "Roof covering", "Electricity", "Solar capacity kWp", "Storeys"):
        assert heading in headings
    assert importer._choice("roof_covering", "single-ply membrane") == "single_ply"
    assert importer._choice("electricity", "Three-phase") == "three"


def test_reports_offer_the_new_columns(site):
    from apps.reports.datasets import _property_fields

    fields = {f.key: f for f in _property_fields()}
    assert fields["construction_type"].value(site["block"]) == "Steel portal frame"
    assert fields["site_area_sqm"].value(site["estate"]) == Decimal("2500")
    assert fields["solar_capacity_kwp"].value(site["block"]) == Decimal("49.50")


def test_demonstration_data_has_site_and_building_details(db):
    from django.core.management import call_command

    call_command("load_demo_data", verbosity=0)
    park = Property.objects.get(reference="DM-N01")
    text = report.build(park)
    assert park.location_description and "## Building: DM-N01-B01 Hangar block" in text
    assert "| Solar panels | Yes, 150 kWp |" in text
