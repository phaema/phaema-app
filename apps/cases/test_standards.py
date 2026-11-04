# SPDX-License-Identifier: AGPL-3.0-or-later
"""Professional standards checks added from the RICS review: late service charge reasons and categories, fair value
level and indexation, dilapidations, conflicts of interest, MEES and safety information."""
from datetime import date, timedelta
from decimal import Decimal as D

import pytest
from django.core.exceptions import ValidationError

from apps.cases import standards, workflow
from apps.cases.models import CaseType
from apps.compliance import safety
from apps.compliance import workflow as compliance
from apps.compliance.models import ComplianceType
from apps.core.models import StaffProfile
from apps.leases.models import Lease, Party
from apps.properties.models import Property


@pytest.fixture
def setup(db, make_user):
    surveyor = make_user("surv", "Surveyors")
    building = Property.objects.create(reference="B1", name="Block", property_type="building",
                                       site_hazards="Fragile roof", managing_surveyor=surveyor)
    unit = Property.objects.create(reference="B1-U1", name="Unit 1", property_type="unit", parent=building,
                                   managing_surveyor=surveyor, site_hazards="Dog on site")
    tenant = Party.objects.create(name="Tenant Ltd", party_type="company")
    lease = Lease.objects.create(reference="L1", agreement_type="lease", counterparty=tenant,
                                 term_start=date(2020, 1, 1), term_end=date(2026, 12, 31), annual_rent=D("10000"),
                                 deposit=D("2500"), deposit_held="Council deposit account")
    lease.properties.add(unit)
    return {"surveyor": surveyor, "building": building, "unit": unit, "lease": lease}


def test_mees_warnings_on_lettings(setup):
    case = workflow.open_case(CaseType.objects.get(code="new_letting"), title="Let", property=setup["unit"])
    assert "no EPC" in standards.mees(case)[0]
    epc = ComplianceType.objects.get(code="epc")
    req = compliance.add_requirements(setup["building"], [epc])[0]
    compliance.record(req, date.today() - timedelta(days=100), rating="D")
    assert standards.mees(case) == []  # the building's EPC covers the unit
    unit_req = compliance.add_requirements(setup["unit"], [epc])[0]
    compliance.record(unit_req, date.today() - timedelta(days=100), rating="F")
    assert "rated F" in standards.mees(case)[0]  # the unit's own EPC is nearer
    old = workflow.open_case(CaseType.objects.get(code="assignment"), title="Assign", lease=setup["lease"])
    assert standards.mees(old) == []  # only lettings and renewals


def test_dilapidations_on_the_case_page(client, setup):
    case = workflow.open_case(CaseType.objects.get(code="dilapidations"), title="Dilaps", lease=setup["lease"],
                              property=setup["unit"])
    client.force_login(setup["surveyor"])
    url = case.get_absolute_url()
    page = client.get(url).content.decode()
    assert "Dilapidations" in page and "2,500.00" in page  # the deposit held
    client.post(url, {"action": "save_dilaps", "dilaps_schedule_value": "abc"})
    case.refresh_from_db()
    assert case.dilaps_schedule_value is None
    client.post(url, {"action": "save_dilaps", "dilaps_schedule_value": "£45,000", "dilaps_served_on": "2027-01-10",
                      "dilaps_settlement_value": "30000", "dilaps_notes": "Section 18 valuation obtained"})
    case.refresh_from_db()
    assert case.dilaps_schedule_value == D("45000") and case.dilaps_served_on == date(2027, 1, 10)
    assert standards.dilaps(case)["gap"] == D("15000")
    assert "15,000.00 less than the schedule" in client.get(url).content.decode()


def test_conflict_shown_to_the_approver(client, make_user, setup):
    head = make_user("head", "Surveyors")
    StaffProfile.objects.update_or_create(user=setup["surveyor"], defaults={"supervisor": head})
    case = workflow.open_case(CaseType.objects.get(code="assignment"), title="A", lease=setup["lease"])
    case.stage = "assessing"
    case.save()
    client.force_login(setup["surveyor"])
    url = case.get_absolute_url()
    assert "Confirm whether there is a conflict of interest first" in client.get(url).content.decode()
    client.post(url, {"action": "save_conflict", "conflict": "declared",
                      "conflict_details": "My brother is a director of the assignee. A colleague reviews."})
    client.post(url, {"action": "request_approval", "stage": "decision", "recommendation": "Grant"})
    assert case.approvals.filter(status="pending").exists()
    client.force_login(head)
    assert "My brother is a director" in client.get(url).content.decode()


def test_safety_information(client, setup):
    info = safety.info(setup["unit"])
    assert [p.reference for p, _t in info["hazards"]] == ["B1", "B1-U1"]
    assert info["asbestos"]["register"] is None
    case = workflow.open_case(CaseType.objects.get(code="assignment"), title="A", lease=setup["lease"])
    client.force_login(setup["surveyor"])
    page = client.get(case.get_absolute_url()).content.decode()
    assert "Before you visit" in page and "Fragile roof" in page and "No asbestos information held" in page
    assert "Dog on site" in client.get(setup["unit"].get_absolute_url()).content.decode()


def test_service_charge_late_reasons_and_categories(client, make_user, db):
    from apps.core.models import ModuleSettings
    from apps.servicecharges.models import CostHeading, Expenditure, Schedule, ScheduleYear

    s = ModuleSettings.load()
    s.service_charges_enabled = True
    s.save()
    year = ScheduleYear.objects.create(schedule=Schedule.objects.create(name="S"), start=date(2025, 4, 1),
                                       end=date(2026, 3, 31))
    client.force_login(make_user("admin", "Administrators"))
    late = (year.statements_due + timedelta(days=10)).isoformat()
    client.post(f"/service-charges/years/{year.pk}/issued/", {"what": "statements", "date": late})
    year.refresh_from_db()
    assert year.statements_issued_on is None  # a reason is needed when late
    client.post(f"/service-charges/years/{year.pk}/issued/", {"what": "statements", "date": late,
                                                              "late_reason": "Waiting for the final energy bill"})
    year.refresh_from_db()
    assert year.statements_issued_on and year.statements_late_reason == "Waiting for the final energy bill"
    heading = CostHeading.objects.first()
    defect = Expenditure.objects.create(year=year, heading=heading, spent_on=date(2025, 6, 1), description="Cladding",
                                        amount=D("1000"), category="bsa_defect", recoverable=True)
    assert defect.recoverable is False  # Building Safety Act remediation costs are not recoverable
    improvement = Expenditure(year=year, heading=heading, spent_on=date(2025, 6, 1), description="New gates",
                              amount=D("500"), category="improvement", recoverable=True)
    with pytest.raises(ValidationError):
        improvement.full_clean()
    improvement.improvement_agreed = True
    improvement.full_clean()


def test_fair_value_level_and_indexation(db):
    from apps.valuations import programme
    from apps.valuations.models import AssetClass, IndexPoint, Valuation

    cls = AssetClass.objects.get(code="operational")
    prop = Property.objects.create(reference="H1", name="Hall", property_type="building")
    v = Valuation.objects.create(property=prop, asset_class=cls, valuation_date=date(2025, 3, 31),
                                 value=D("1000000"), land_value=D("200000"), building_value=D("800000"),
                                 status="accepted", fair_value_level="3")
    assert programme.indexed(v, date(2026, 3, 31)).note.endswith("index values missing")
    IndexPoint.objects.create(index=cls.index, on=date(2025, 1, 1), value=D("400"))
    IndexPoint.objects.create(index=cls.index, on=date(2026, 1, 1), value=D("420"))
    result = programme.indexed(v, date(2026, 3, 31))
    assert result.factor == D("1.0500") and result.value == D("1040000")  # land is not indexed
