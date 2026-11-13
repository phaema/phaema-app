# SPDX-License-Identifier: AGPL-3.0-or-later
"""The details the Government Property Data Standard asks for, and the export of the estate in its layout."""
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError
from django.urls import reverse

from apps.compliance.models import Certificate, ComplianceType, Requirement
from apps.core.models import ModuleSettings
from apps.core.roles import ADMINISTRATORS, SURVEYORS, VIEWERS
from apps.leases.models import BreakOption, Lease, Party
from apps.maintenance.models import Component
from apps.properties import standard
from apps.properties.models import Property, PropertyCost, PropertyUse
from apps.properties.uses import STARTING_USES, year_from
from apps.valuations.models import AssetClass, Valuation

TODAY = date.today()


@pytest.fixture
def estate(db, make_user):
    settings = ModuleSettings.load()
    settings.organisation_name = "Testshire Council"
    settings.valuation_enabled = settings.maintenance_enabled = settings.compliance_enabled = True
    settings.save()
    sue = make_user("sue", SURVEYORS)
    hall = Property.objects.create(
        reference="T-1", name="Old Library", property_type="building", managing_surveyor=sue, tenure="freehold",
        address_line_1="12A High Street", town="Testford", postcode="TE1 1AA", easting=450000, northing=200000,
        uprn="100012345678", gia_sqm=Decimal("800"), area_standard="comp6", holding_purpose="operational",
        occupation="council", use_type=PropertyUse.objects.get(name="Library"), use_description="Reading room and archive",
        use_class="F1(d)", built="c. 1936, extended 1988", acquired_on=date(1974, 4, 1), listed_building="2",
        scheduled_monument="no", sssi="no", conservation_area="yes", designation_notes="List entry 1234567",
        condition_grade="C", condition_surveyed_on=date(2024, 5, 20))
    shop = Property.objects.create(
        reference="T-1-U1", name="Shop 1", property_type="unit", parent=hall, managing_surveyor=sue,
        nia_sqm=Decimal("60"), occupation="vacant", use_type=PropertyUse.objects.get(name="Shop"),
        vacant_since=TODAY - timedelta(days=90), vacancy_status="under_offer",
        available_from=TODAY - timedelta(days=60), tenure="freehold")
    yard = Property.objects.create(
        reference="T-2", name="Depot Yard", property_type="land", managing_surveyor=sue, tenure="freehold",
        site_area_ha=Decimal("1.2000"), holding_purpose="held_for_sale", occupation="vacant",
        address_line_1="Depot Road", town="Testford", disposal_reason="Surplus after the depot review",
        disposal_method="community", disposal_expected_on=TODAY + timedelta(days=200),
        disposal_expected_value=Decimal("450000"))
    return {"sue": sue, "hall": hall, "shop": shop, "yard": yard, "admin": make_user("admin", ADMINISTRATORS)}


def test_starting_uses_and_year_built():
    assert year_from("1987") == 1987 and year_from("1930s") == 1930 and year_from("c. 1936, extended 1988") == 1936
    assert year_from("Victorian") is None and year_from("") is None and year_from("12345") is None
    names = [name for name, _standard in STARTING_USES]
    assert len(names) == len(set(names)) and "Office" in names


def test_uses_list_is_seeded_and_kept_by_administrators(client, estate):
    assert PropertyUse.objects.count() == len(STARTING_USES)
    assert PropertyUse.objects.get(name="Shop").standard_usage == "Retail"
    retired = PropertyUse.objects.get(name="Hostel")
    retired.active = False
    retired.save()
    client.force_login(estate["admin"])
    assert client.get(reverse("admin:properties_propertyuse_changelist")).status_code == 200
    form = client.get(reverse("admin:properties_property_change", args=[estate["hall"].pk])).content.decode()
    assert ">Library</option>" in form and ">Hostel</option>" not in form  # only uses still in use are offered
    client.force_login(estate["sue"])  # surveyors can see the list; it is the administrators' to change
    assert client.get(reverse("admin:properties_propertyuse_changelist")).status_code == 200
    assert client.get(reverse("admin:properties_propertyuse_add")).status_code == 403
    # A surveyor records running costs on a property they manage.
    form = client.get(reverse("admin:properties_property_change", args=[estate["hall"].pk])).content.decode()
    assert 'name="costs-0-year_starting"' in form and 'name="listed_building"' in form


def test_details_are_checked_and_tidied(estate):
    hall, shop = estate["hall"], estate["shop"]
    assert hall.built_year == 1936  # taken from the "built" text
    assert hall.use_text() == "Library: Reading room and archive (F1(d))" and shop.use_text() == "Shop"
    hall.use_description = "Public library"  # the description already names the use
    assert hall.use_text(with_class=False) == "Public library"
    hall.use_description = "Reading room and archive"
    assert hall.designated and not estate["yard"].designated
    assert dict(hall.designation_rows())["Listed building"] == "Grade II"
    assert "C: poor" in hall.condition_text() and "20 May 2024" in hall.condition_text()

    for field, value in (("condition_surveyed_on", TODAY + timedelta(days=1)),
                         ("acquired_on", TODAY + timedelta(days=1)), ("built_year", TODAY.year + 9)):
        broken = Property.objects.get(pk=hall.pk)
        setattr(broken, field, value)
        with pytest.raises(ValidationError) as caught:
            broken.full_clean()
        assert field in caught.value.message_dict
    no_grade = Property.objects.get(pk=hall.pk)
    no_grade.condition_grade = ""
    with pytest.raises(ValidationError) as caught:
        no_grade.full_clean()
    assert "condition_grade" in caught.value.message_dict
    shop.available_until = shop.available_from - timedelta(days=1)
    with pytest.raises(ValidationError) as caught:
        shop.full_clean()
    assert "available_until" in caught.value.message_dict

    # Vacancy details go when the property is occupied again.
    shop.available_until = None
    assert "Under offer" in shop.vacancy_text()
    shop.occupation = "let"
    shop.save()
    shop.refresh_from_db()
    assert (shop.vacant_since, shop.vacancy_status, shop.available_from) == (None, "", None)
    assert shop.vacancy_text() == ""


def test_running_costs_by_year(estate):
    hall = estate["hall"]
    PropertyCost.objects.create(property=hall, year_starting=2024, running_cost=Decimal("41000"),
                                rates=Decimal("18000"))
    latest = PropertyCost.objects.create(property=hall, year_starting=2025, running_cost=Decimal("43500"))
    assert latest.year_label() == "2025-26" and hall.latest_cost() == latest
    with pytest.raises(ValidationError):
        PropertyCost(property=hall, year_starting=2026).full_clean()  # needs a figure
    with pytest.raises(IntegrityError):
        PropertyCost.objects.create(property=hall, year_starting=2025, rates=Decimal("1"))


def test_property_page_and_report_show_the_details(client, estate):
    hall, shop, yard = estate["hall"], estate["shop"], estate["yard"]
    PropertyCost.objects.create(property=hall, year_starting=2025, running_cost=Decimal("43500"),
                                rates=Decimal("18250"), notes="From finance")
    client.force_login(estate["sue"])
    page = client.get(hall.get_absolute_url()).content.decode()
    for text in ("Library: Reading room and archive", "Acquired 1 April 1974", "Listed building: Grade II",
                 "Conservation area: Yes", "List entry 1234567", "2025-26", "£43,500", "£18,250", "From finance",
                 "C: poor"):
        assert text in page, text
    page = client.get(shop.get_absolute_url()).content.decode()
    assert "Under offer" in page and "Vacant since" in page and "Available from" in page
    page = client.get(yard.get_absolute_url()).content.decode()
    for text in ("Planned disposal", "Surplus after the depot review", "Community asset transfer", "£450,000"):
        assert text in page, text
    report = client.get(reverse("properties:report", args=[hall.pk])).content.decode()
    assert "Listed building: Grade II" in report and "running cost £43,500" in report

    # Once sold, the plan gives way to what happened.
    yard.disposed_on, yard.disposal_price = TODAY, Decimal("460000")
    yard.save()
    page = client.get(yard.get_absolute_url()).content.decode()
    assert "Planned disposal" not in page and "£460,000" in page and "community asset transfer" in page


def _export(estate):
    hall, shop = estate["hall"], estate["shop"]
    PropertyCost.objects.create(property=hall, year_starting=2024, running_cost=Decimal("1"), rates=Decimal("2"))
    PropertyCost.objects.create(property=hall, year_starting=2025, running_cost=Decimal("43500"),
                                rates=Decimal("18250"))
    epc = Requirement.objects.create(property=hall, kind=ComplianceType.objects.get(code="epc"))
    Certificate.objects.create(requirement=epc, issued_on=date(2015, 3, 1), expires_on=date(2025, 3, 1), rating="E",
                               reference="OLD")
    Certificate.objects.create(requirement=epc, issued_on=date(2025, 3, 2), expires_on=date(2035, 3, 2), rating="C",
                               reference="0000-1111")
    cls = AssetClass.objects.get(code="investment")
    Valuation.objects.create(property=hall, asset_class=cls, valuation_date=date(2025, 3, 31), basis="euv",
                             value=Decimal("900000"), status="accepted")
    Valuation.objects.create(property=hall, asset_class=cls, valuation_date=date(2026, 3, 31), basis="euv",
                             value=Decimal("990000"), status="received")  # not yet accepted: left out
    Component.objects.create(property=hall, name="Main roof", category="roof", uniclass="Ss_30_10", quantity=1,
                             unit="nr", installed_year=TODAY.year - 20, life_years=30, condition="C",
                             condition_on=date(2024, 5, 20), location="Roof")
    landlord = Party.objects.create(name="Estates Holdings Ltd", party_type="company")
    tenant = Party.objects.create(name="A Tenant Ltd", party_type="company")
    held = Lease.objects.create(reference="IN-1", direction="in", agreement_type="lease", status="current",
                                counterparty=landlord, term_start=date(2020, 1, 1), term_end=date(2035, 1, 1),
                                annual_rent=Decimal("24000"), repairing="fri", review_interval_years=5,
                                next_review_date=date(2030, 1, 1))
    held.properties.add(shop)
    BreakOption.objects.create(lease=held, break_date=date(2025, 1, 1), notice_months=6)
    BreakOption.objects.create(lease=held, break_date=date(2030, 1, 1), notice_months=9)
    let = Lease.objects.create(reference="OUT-1", direction="out", agreement_type="lease", status="current",
                               counterparty=tenant, term_start=date(2021, 1, 1), annual_rent=Decimal("9000"))
    let.properties.add(shop)


def _row(data, sheet, columns, reference):
    headings = [heading for heading, _ref in columns]
    row = next(r for r in data[sheet] if r[0] == reference)
    return dict(zip(headings, row))


def test_export_maps_the_estate_to_the_standard(estate):
    _export(estate)
    data = standard.gather(today=TODAY)
    hall = _row(data, "properties", standard.PROPERTY_COLUMNS, "T-1")
    expected = {
        "Organisation": "Testshire Council", "Primary Property Name": "Old Library", "Primary Property Number": "12A",
        "Secondary Property Name": "", "Street Name": "High Street", "Town": "Testford", "Postcode": "TE1 1AA",
        "Easting": 450000, "Northing": 200000, "Coordinate Reference System": standard.GRID,
        "UPRN": "100012345678", "Floor Area (sq m)": Decimal("800"),
        "Floor Area Measurement Type": "GIA (RICS Code of Measuring Practice, 6th edition)",
        "Usage": "Public Library", "PHAEMA use": "Library: Reading room and archive (F1(d))",
        "Listed Building": "Yes: Grade II", "Ancient Monument": "No", "SSSI/ASSI": "No", "Conservation Area": "Yes",
        "Construction Date (year)": 1936, "Acquisition Date (year)": 1974, "Building Condition": "C",
        "Building Condition date": date(2024, 5, 20), "EPC Property Rating": "C",
        "EPC Certificate Reference": "0000-1111", "EPC Expiry Date": date(2035, 3, 2), "Tenure": "Freehold",
        "Value (£)": Decimal("900000"), "Value Type": "EUV", "Valuation Date": date(2025, 3, 31),
        "Rates (£ a year)": Decimal("18250"), "Total Property/Space Running Costs (£)": Decimal("43500"),
        "Year of rates and running costs": "2025-26", "Surplus Status": "No", "Excluded from open data": "No",
    }
    for heading, value in expected.items():
        assert hall[heading] == value, heading

    shop = _row(data, "properties", standard.PROPERTY_COLUMNS, "T-1-U1")  # a unit takes its building's address
    assert (shop["Primary Property Name"], shop["Secondary Property Name"]) == ("Old Library", "Shop 1")
    assert (shop["Primary Property Number"], shop["Street Name"], shop["Postcode"]) == ("12A", "High Street", "TE1 1AA")
    assert shop["Usage"] == "Retail" and shop["Floor Area Measurement Type"] == "NIA"
    assert shop["Easting"] == "" and shop["Coordinate Reference System"] == ""  # nothing is filled in by default

    yard = _row(data, "properties", standard.PROPERTY_COLUMNS, "T-2")
    assert yard["Surplus Status"] == "Yes" and yard["Disposal Method"] == "Other"
    assert yard["Future Disposal Value (£)"] == Decimal("450000") and yard["Land Area (ha)"] == Decimal("1.2000")
    assert yard["Listed Building"] == "" and yard["Primary Property Number"] == ""

    # Contracts: what the council holds as tenant, with the next break still to come. Its own lettings are left out.
    assert [r[2] for r in data["contracts"]] == ["IN-1"]
    contract = _row(data, "contracts", standard.CONTRACT_COLUMNS, "T-1-U1")
    assert contract["Landlord Name"] == "Estates Holdings Ltd" and contract["Tenure"] == "Leasehold"
    assert contract["Earliest Break Date"] == date(2030, 1, 1) and contract["Break Notice Term (months)"] == 9
    assert contract["Repair Liability"] == "Full repairing and insuring"
    assert "A Tenant Ltd" not in str(data)  # tenants' names are not exported

    vacant = _row(data, "vacant", standard.VACANT_COLUMNS, "T-1-U1")
    assert vacant["Vacant Space Status"] == "Under Offer" and vacant["Vacant Space Floor Area (sq m)"] == Decimal("60")
    assert vacant["Vacation Date"] == TODAY - timedelta(days=90)
    assert [r[0] for r in data["vacant"]] == ["T-1-U1", "T-2"]

    asset = _row(data, "assets", standard.ASSET_COLUMNS, "T-1")
    assert asset["FM Asset Name"] == "Main roof" and asset["FM Asset Classification Code"] == "Ss_30_10"
    assert asset["Remain Life Expectancy (Years)"] == 10 and asset["FM Asset Condition"] == "C"

    coverage = {heading: (filled, total) for heading, _ref, filled, total, _pc in standard.coverage(data)}
    assert coverage["Listed Building"] == (1, 3) and coverage["Primary Property Name"] == (3, 3)
    assert "PHAEMA reference" not in coverage


def test_workbook_and_who_may_download_it(client, make_user, estate):
    from openpyxl import load_workbook

    _export(estate)
    page_url, file_url = reverse("properties:data-standard"), reverse("properties:data-standard-download")
    assert client.get(file_url).status_code == 302  # signed out
    client.force_login(make_user("vera", VIEWERS))
    assert client.get(page_url).status_code == 403 and client.get(file_url).status_code == 403
    assert "Government Property Data Standard" not in client.get(reverse("reports:list")).content.decode()

    client.force_login(estate["sue"])
    assert "Government Property Data Standard export" in client.get(reverse("reports:list")).content.decode()
    page = client.get(page_url).content.decode()
    for text in ("not a certificate of compliance", "How complete the records are", "Listed Building", "2.2.0004",
                 "BREEAM Rating"):
        assert text in page, text
    response = client.get(file_url)
    assert response.status_code == 200 and "estate-government-property-data-standard" in response["Content-Disposition"]
    book = load_workbook(BytesIO(response.content))
    assert book.sheetnames == ["About", "Properties", "Contracts", "Vacant spaces", "FM assets", "Fields not exported"]
    sheet = book["Properties"]
    headings = [c.value for c in sheet[1]]
    assert "Primary Property Name [1.1.0001]" in headings and "Listed Building [2.2.0004]" in headings
    assert sheet.max_row == 4 and sheet.cell(row=2, column=headings.index("Value (£) [4.1.0001]") + 1).value == 900000
    assert "Testshire Council" in book["About"]["A1"].value
    assert any(row[0].value == "2.2.0011" for row in book["Fields not exported"].iter_rows(min_row=2))


@pytest.mark.own_areas
def test_export_leaves_out_what_the_person_cannot_see(make_user, estate):
    _export(estate)
    newcomer = make_user("nell", SURVEYORS)  # in no access area, so no valuations, compliance or maintenance
    data = standard.gather(newcomer, today=TODAY)
    hall = _row(data, "properties", standard.PROPERTY_COLUMNS, "T-1")
    assert hall["Value (£)"] == "" and hall["EPC Property Rating"] == "" and data["assets"] == []
    assert hall["Listed Building"] == "Yes: Grade II"  # the property record itself is still there
    assert not (data["valuation"] or data["compliance"] or data["maintenance"])


def test_demonstration_data_has_the_details(db):
    call_command("load_demo_data", verbosity=0)
    demo = Property.objects.filter(reference__startswith="DM-")
    assert not demo.filter(use_type__isnull=True).exists()
    assert demo.exclude(listed_building="").exists() and demo.filter(listed_building="2").exists()
    assert demo.exclude(condition_grade="").count() >= 8 and demo.exclude(vacancy_status="").exists()
    assert demo.exclude(disposal_reason="").exists() and PropertyCost.objects.count() >= 4
    before = PropertyCost.objects.count()
    call_command("load_demo_data", verbosity=0)  # repeatable
    assert PropertyCost.objects.count() == before
    data = standard.gather()
    assert len(data["properties"]) == demo.count() and data["vacant"] and data["contracts"]
    assert len(standard.workbook(data)) > 10000
