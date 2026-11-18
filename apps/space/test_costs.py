# SPDX-License-Identifier: AGPL-3.0-or-later
"""Space and costing, level 2: building costs, notional rent, and sharing costs between occupiers."""
from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.core.models import AccessArea, ModuleSettings
from apps.properties.models import Property, PropertyCost
from apps.space import costs
from apps.space.models import (BuildingCost, CostLine, CostSharing, FixedShare, Headcount, Occupation, Occupier,
                               Space)
from apps.space.seed import ensure_cost_lines

PASSWORD = "a-long-test-password"
YEAR = costs.year_of(date.today()) - 1  # last full financial year


@pytest.fixture
def setup(db):
    settings = ModuleSettings.load()
    settings.space_enabled = settings.space_costing_enabled = True
    settings.save()
    ensure_cost_lines()
    b = Property.objects.create(reference="CC1", name="Civic Centre", property_type="building",
                                nia_sqm=Decimal("1000"))
    floor = Space.objects.create(building=b, kind="floor", name="Ground", area_sqm=1000)
    Space.objects.create(building=b, kind="shared", name="Reception", floor=floor, area_sqm=100)
    a = Space.objects.create(building=b, kind="room", name="A", floor=floor, area_sqm=500, capacity=50)
    c = Space.objects.create(building=b, kind="room", name="C", floor=floor, area_sqm=300, capacity=30)
    housing = Occupier.objects.create(name="Housing")
    nhs = Occupier.objects.create(name="NHS clinic", level="external", external_kind="nhs")
    since = date(YEAR - 1, 4, 1)
    Occupation.objects.create(building=b, space=a, occupier=housing, starts=since)
    Occupation.objects.create(building=b, space=c, occupier=nhs, starts=since)
    Headcount.objects.create(building=b, occupier=housing, people=60, counted_on=since)
    Headcount.objects.create(building=b, occupier=nhs, people=20, counted_on=since)
    lines = {line.name: line for line in CostLine.objects.all()}
    for name, amount in (("Energy", 60000), ("Cleaning", 40000), ("Notional rent", 100000)):
        BuildingCost.objects.create(building=b, year_starting=YEAR, line=lines[name], amount=amount, source="Ledger")
    return {"building": b, "housing": housing, "nhs": nhs}


def test_year_of_runs_april_to_march():
    assert costs.year_of(date(2026, 3, 31)) == 2025 and costs.year_of(date(2026, 4, 1)) == 2026


def test_totals_with_and_without_notional_rent(setup):
    s = costs.share_out(setup["building"], YEAR)
    assert s.cash == Decimal("100000") and s.notional == Decimal("100000") and s.total == Decimal("200000")


def test_area_method_spreads_shared_space_and_leaves_vacant_with_landlord(setup):
    s = costs.share_out(setup["building"], YEAR)
    by = {x.label: x for x in s.shares}
    # Housing holds 500 of the 800 occupied, so 500 + 62.5 shared = 562.5 of 1000
    assert by["Housing"].percent == Decimal("56.3") and by["Housing"].cash == Decimal("56250.00")
    assert by["NHS clinic"].cash == Decimal("33750.00")
    vacant = [x for x in s.shares if x.occupier is None][0]
    assert vacant.cash == Decimal("10000.00") and "corporate landlord" in vacant.label
    assert sum(x.cash for x in s.shares) == s.cash


def test_headcount_method(setup):
    CostSharing.objects.create(building=setup["building"], method="headcount")
    by = {x.label: x for x in costs.share_out(setup["building"], YEAR).shares}
    assert by["Housing"].cash == Decimal("75000.00") and by["NHS clinic"].cash == Decimal("25000.00")
    assert by["Housing"].per_person == Decimal("2500")


def test_fixed_percentages_with_warnings(setup):
    sharing = CostSharing.objects.create(building=setup["building"], method="fixed")
    FixedShare.objects.create(sharing=sharing, occupier=setup["housing"], percent=70)
    s = costs.share_out(setup["building"], YEAR)
    by = {x.label: x for x in s.shares}
    assert by["Housing"].cash == Decimal("70000.00")
    assert any("NHS clinic" in w for w in s.warnings)
    assert [x for x in s.shares if x.occupier is None][0].cash == Decimal("30000.00")


def test_property_record_figures_are_used_when_no_lines_entered(setup):
    b = setup["building"]
    BuildingCost.objects.filter(building=b).delete()
    PropertyCost.objects.create(property=b, year_starting=YEAR, running_cost=50000, rates=20000)
    found = {c.line: c for c in costs.building_costs(b, YEAR)}
    assert found["Business rates"].origin == "property record" and found["Running costs"].amount == 50000


def test_entered_lines_win_over_property_record(setup):
    PropertyCost.objects.create(property=setup["building"], year_starting=YEAR, running_cost=50000, rates=20000)
    found = {c.line for c in costs.building_costs(setup["building"], YEAR)}
    assert "Running costs" not in found and "Business rates" in found


def test_repairs_from_maintenance_jobs(setup):
    from apps.maintenance.models import Job

    settings = ModuleSettings.load()
    settings.maintenance_enabled = True
    settings.save()
    Job.objects.create(property=setup["building"], title="Roof leak", completed_on=date(YEAR, 6, 1),
                       actual_cost=Decimal("1200"), responsibility="landlord", status="completed")
    Job.objects.create(property=setup["building"], title="Tenant's own", completed_on=date(YEAR, 6, 1),
                       actual_cost=Decimal("900"), responsibility="tenant", status="completed")
    found = {c.line: c for c in costs.building_costs(setup["building"], YEAR)}
    assert found["Repairs and maintenance"].amount == Decimal("1200")
    assert found["Repairs and maintenance"].origin == "maintenance jobs"


def test_estate_totals_by_occupier(setup):
    _sharings, rows, unshared = costs.estate(YEAR)
    assert [r.occupier.name for r in rows] == ["Housing", "NHS clinic"]
    assert rows[0].cash == Decimal("56250.00") and unshared == Decimal("20000.00")


def test_cost_pages_need_space_costs(client, make_user, setup):
    sue = make_user("sue", "Surveyors")
    sue.access_areas.set(AccessArea.objects.filter(code="estates"))
    client.login(username="sue", password=PASSWORD)
    page = client.get(reverse("space:building", args=[setup["building"].pk]))
    assert page.status_code == 200 and b"Shared between occupiers" not in page.content
    assert client.get(reverse("space:costs")).status_code == 403
    assert client.get(reverse("admin:space_buildingcost_changelist")).status_code == 403
    sue.access_areas.add(AccessArea.objects.get(code="finance"))
    page = client.get(reverse("space:building", args=[setup["building"].pk]) + f"?year={YEAR}")
    assert b"Shared between occupiers" in page.content and b"Notional" in page.content
    assert client.get(reverse("space:costs") + f"?year={YEAR}").status_code == 200


def test_costs_off_hides_costs_even_for_administrators(client, make_user, setup):
    settings = ModuleSettings.load()
    settings.space_costing_enabled = False
    settings.save()
    make_user("boss", "Administrators")
    client.login(username="boss", password=PASSWORD)
    page = client.get(reverse("space:building", args=[setup["building"].pk]) + f"?year={YEAR}")
    assert page.status_code == 200 and b"Shared between occupiers" not in page.content


def test_excel_for_finance(client, make_user, setup):
    from io import BytesIO

    from openpyxl import load_workbook

    make_user("boss", "Administrators")
    client.login(username="boss", password=PASSWORD)
    resp = client.get(reverse("space:costs") + f"?year={YEAR}&format=xlsx")
    wb = load_workbook(BytesIO(resp.content))
    assert wb.sheetnames == ["By occupier", "By building", "Costs and sources", "About"]
    assert wb["By occupier"]["A2"].value == "Housing"


def test_occupier_page_shows_costs(client, make_user, setup):
    make_user("boss", "Administrators")
    client.login(username="boss", password=PASSWORD)
    page = client.get(reverse("space:occupier", args=[setup["housing"].pk]) + f"?year={YEAR}").content
    assert b"What occupation costs" in page and b"56,250" in page


def test_one_figure_per_line_per_year(setup):
    from django.db import IntegrityError, transaction

    line = CostLine.objects.get(name="Energy")
    with pytest.raises(IntegrityError), transaction.atomic():
        BuildingCost.objects.create(building=setup["building"], year_starting=YEAR, line=line, amount=1)


def test_demo_costs(db):
    from apps.space import demo

    Property.objects.create(reference=demo.CIVIC, name="Civic", property_type="building", nia_sqm=Decimal("3300"))
    demo.load()
    s = costs.share_out(Property.objects.get(reference=demo.CIVIC), costs.year_of(date.today()) - 1)
    assert s.cash > 0 and s.notional > 0 and len([x for x in s.shares if x.occupier]) == 6
    assert all(x.people for x in s.shares if x.occupier)
