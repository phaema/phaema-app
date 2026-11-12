# SPDX-License-Identifier: AGPL-3.0-or-later
"""The site visit sheet: its four parts, what administrators can change, and the page, print and Word forms."""
from datetime import date
from decimal import Decimal
from io import BytesIO

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.cases import seed, visit
from apps.cases.models import Case, CaseType, CaseTypeChecklistItem
from apps.core.roles import ADMINISTRATORS, SURVEYORS, VIEWERS
from apps.leases.models import Lease, Party
from apps.properties.models import Property


@pytest.fixture
def site(db, make_user):
    sue = make_user("sue", SURVEYORS, first_name="Sue", last_name="Surveyor")
    estate = Property.objects.create(
        reference="T-01", name="Mill Yard", property_type="site", managing_surveyor=sue, address_line_1="Mill Lane",
        site_area_ha=Decimal("0.25"), site_hazards="Deep water in the mill race.", parking="Yard parking.")
    a = Property.objects.create(
        reference="T-01-A", name="Block A", property_type="building", parent=estate, construction_type="portal_frame",
        storeys=1, roof_type="flat", roof_covering="single_ply", window_type="upvc", electricity="three",
        mains_water="yes", gia_sqm=Decimal("500"), site_hazards="Fragile roof lights.")
    b = Property.objects.create(reference="T-01-B", name="Block B", property_type="building", parent=estate)
    unit = Property.objects.create(reference="T-01-A1", name="Unit 1", property_type="unit", parent=a,
                                   occupation="let", nia_sqm=Decimal("450"))
    tenant = Party.objects.create(name="Acme Joinery Ltd", party_type="company", contact_name="Ann Carpenter",
                                  phone="01632 960001", email="ann@acme.example")
    lease = Lease.objects.create(reference="L-1", agreement_type="lease", counterparty=tenant,
                                 term_start=date(2022, 1, 1), term_end=date(2032, 1, 1), annual_rent=Decimal("24000"),
                                 permitted_use="Joinery workshop")
    lease.properties.add(unit)
    return {"sue": sue, "estate": estate, "a": a, "b": b, "unit": unit, "lease": lease, "tenant": tenant}


def case_of(code, **kwargs):
    return Case.objects.create(case_type=CaseType.objects.get(code=code), title="Test case", **kwargs)


# What PHAEMA ships with

def test_shipped_case_types_have_starting_sheets(db):
    valuation = CaseType.objects.get(code="asset_valuation")
    assert valuation.visit_parts == seed.EVERYTHING
    labels = list(valuation.checklist_items.values_list("label", flat=True))
    assert "Construction as recorded" in labels and "Floor areas check-measured" in labels
    assert valuation.checklist_items.get(label="Construction as recorded").each_building
    assert not valuation.checklist_items.get(label="Photographs taken").each_building
    assert CaseType.objects.get(code="signage").visit_parts == seed.BRIEF_VISIT
    # Types that are not about a visit have no checklist; every shipped type has its property parts set.
    assert not CaseType.objects.get(code="arrears").checklist_items.exists()
    assert not CaseType.objects.filter(visit_parts=[]).exists()
    for code in seed.CHECKLIST_BY_CODE:
        assert CaseType.objects.get(code=code).checklist_items.exists(), code


def test_a_councils_own_case_type_starts_with_the_general_parts_and_no_checklist(db):
    own = CaseType.objects.create(code="garage-swap", name="Garage swap")
    assert own.visit_parts == ["facts", "description", "services", "areas", "agreements", "cases"]
    assert not own.checklist_items.exists()


# The sheet

def test_sheet_for_a_site_with_blocks(site):
    case = case_of("asset_valuation", property=site["estate"], owner=site["sue"])
    text = visit.build(case, user=site["sue"], today=date(2026, 11, 12))
    assert text.startswith(f"# Site visit sheet: {case.display_reference}")
    assert "Asset valuation: Test case. Prepared 12 November 2026 by Sue Surveyor." in text
    parts = [line for line in text.split("\n") if line.startswith("# ")]
    assert [p.split(":")[0] for p in parts] == ["# Site visit sheet", "# The case", "# Before you visit",
                                               "# The property", "# On site"]
    # the case
    assert "| Case owner | Sue Surveyor |" in text and "| Address | Mill Lane |" in text
    # before you visit: hazards of the site and of each block, asbestos warning, who is there
    assert "- T-01 Mill Yard: Deep water in the mill race." in text
    assert "- T-01-A Block A: Fragile roof lights." in text
    assert "no asbestos information is held" in text
    assert "| Acme Joinery Ltd | Unit 1 | Ann Carpenter | 01632 960001 |" in text
    # the property: every part for a valuation
    for heading in ("## The property", "## Location", "## Description, construction and services", "## Floor areas",
                    "## Floor plans", "## Title", "## Tenancies and other agreements", "## Cases in hand"):
        assert heading in text, heading
    assert "## L-1: Acme Joinery Ltd" in text
    # on site: once for the whole visit, then a section for each building with its own recorded values
    assert "## The visit as a whole: Mill Yard" in text
    whole = text.split("## The visit as a whole: Mill Yard")[1].split("## T-01-A Block A")[0]
    assert "Signed in and made yourself known" in whole and "Construction as recorded" not in whole
    assert "| Site hazards as recorded *Note any new hazard and add it to the property record.* | "\
           "Deep water in the mill race. | ☐ Yes   ☐ No |" in whole
    block_a = text.split("## T-01-A Block A")[-1].split("## T-01-B Block B")[0]
    assert "| Construction as recorded | Steel portal frame | ☐ Yes   ☐ No |" in block_a
    assert "| Roof type and covering as recorded *View from the ground or a safe vantage point only.* | "\
           "Flat, Single-ply membrane | ☐ Yes   ☐ No |" in block_a
    assert "☐ Good   ☐ Fair   ☐ Poor   ☐ Bad" in block_a
    block_b = text.split("## T-01-B Block B")[-1]
    assert "| Construction as recorded | Not recorded | ☐ Yes   ☐ No |" in block_b
    assert "| Visited by |" in text and "| To follow up |" in text


def test_sheet_for_one_unit_uses_one_list_and_looks_up_the_building(site):
    case = case_of("alterations", lease=site["lease"], party=site["tenant"])
    text = visit.build(case)
    assert "The visit as a whole" not in text and "## T-01-A Block A" not in text
    assert "| Applicant or tenant | Acme Joinery Ltd; Ann Carpenter; 01632 960001; ann@acme.example |" in text
    assert "| Agreement | L-1 Lease |" in text and "| Property | T-01-A1 Unit 1 |" in text
    # the unit has no services of its own, so the building's are shown
    assert "Electricity: Three-phase; Mains water: Yes" in text
    # hazards of everything the unit is part of
    assert "Deep water in the mill race." in text and "Fragile roof lights." in text
    # a consent shows no location, titles or floor areas
    assert "## Location" not in text and "## Title" not in text and "## Floor areas" not in text
    assert "What is proposed matches the application" in text


def test_administrator_choices_change_the_sheet(site):
    case_type = CaseType.objects.get(code="boundary")
    case_type.visit_parts = ["facts"]
    case_type.full_clean()
    case_type.save()
    case_type.checklist_items.all().delete()
    CaseTypeChecklistItem.objects.create(case_type=case_type, heading="Fence", label="Height of fence",
                                         guidance="In metres", kind="number", order=1)
    CaseTypeChecklistItem.objects.create(case_type=case_type, heading="Fence", label="Material", kind="choice",
                                         choices="Timber, Wire , Hedge", order=2)
    text = visit.build(case_of("boundary", property=site["b"]))
    assert "## The property" in text and "## Description" not in text and "## Tenancies" not in text
    assert "| **Fence** | **Recorded** | **On site** |" in text
    assert "| Height of fence *In metres* |" in text
    assert "☐ Timber   ☐ Wire   ☐ Hedge" in text

    case_type.visit_parts = []
    case_type.save()
    case_type.checklist_items.all().delete()
    text = visit.build(case_of("boundary", property=site["b"]))
    assert "# The property" not in text and "# Before you visit" in text  # safety is always there
    assert "This type of case has no checklist." in text


def test_settings_are_checked(db):
    case_type = CaseType.objects.get(code="boundary")
    case_type.visit_parts = ["facts", "nonsense"]
    with pytest.raises(ValidationError):
        case_type.full_clean()
    item = CaseTypeChecklistItem(case_type=case_type, label="Material", kind="choice", choices=" , ")
    with pytest.raises(ValidationError):
        item.full_clean()


def test_a_case_with_no_property_has_no_sheet(client, site):
    case = case_of("enquiry")
    assert visit.build(case) is None
    client.force_login(site["sue"])
    assert "Site visit sheet" not in client.get(case.get_absolute_url()).content.decode()
    assert client.get(reverse("cases:site-visit", args=[case.pk])).status_code == 404


# The page, print and Word

def test_page_and_word(client, site, make_user):
    case = case_of("asset_valuation", property=site["estate"], owner=site["sue"])
    url = reverse("cases:site-visit", args=[case.pk])
    assert client.get(url).status_code == 302  # sign in first
    client.force_login(make_user("vic", VIEWERS))
    assert url in client.get(case.get_absolute_url()).content.decode()
    page = client.get(url).content.decode()
    assert "phaema-sheet" in page and "Before you visit" in page and "Construction as recorded" in page
    assert "Nothing you tick or type here is saved" in page and "Download as Word" in page
    assert "Change this sheet for all cases of this type" not in page
    word = client.get(url + "?format=docx")
    assert word.status_code == 200 and word.content[:2] == b"PK"
    assert f"Site visit sheet {case.reference}.docx" in word["Content-Disposition"]
    from docx import Document

    doc = Document(BytesIO(word.content))
    cells = [cell.text for table in doc.tables for row in table.rows for cell in row.cells]
    assert any("Construction as recorded" in c for c in cells) and any("☐ Yes" in c for c in cells)

    client.force_login(make_user("boss", ADMINISTRATORS))
    assert "Change this sheet for all cases of this type" in client.get(url).content.decode()


def test_administrator_edits_the_sheet_in_manage_data(client, make_user):
    client.force_login(make_user("boss", ADMINISTRATORS))
    case_type = CaseType.objects.get(code="asset_valuation")
    page = client.get(reverse("admin:cases_casetype_change", args=[case_type.pk])).content.decode()
    assert "Property information on the site visit sheet" in page
    assert "Site visit checklist: what to check or record on site" in page and "Floor plans held" in page
