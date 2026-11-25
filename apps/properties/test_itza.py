# SPDX-License-Identifier: AGPL-3.0-or-later
"""Retail zoning: the ITZA calculator, saving it on the property, and the rent per m² Zone A."""
from datetime import date
from decimal import Decimal

import pytest

from apps.leases.models import Lease, Party
from apps.properties import itza
from apps.properties.models import Property

D = Decimal


def test_rectangle_is_zoned_and_halved_back():
    # 6 m wide, 22 m deep, zones of 6.1 m: A 36.6, B 36.6 at a half, C 36.6 at a quarter, and the last 3.7 m
    # (22.2 m²) at an eighth.
    result = itza.calculate({"zone_depth": "6.1", "mode": "rectangle", "width": "6", "depth": "22"})
    assert result.ok
    assert [(r.label, r.area, r.itza) for r in result.rows] == [
        ("Zone A", D("36.60"), D("36.60")), ("Zone B", D("36.60"), D("18.30")), ("Zone C", D("36.60"), D("9.15")),
        ("Remainder", D("22.20"), D("2.78"))]
    assert result.total == D("66.83") and result.ground_floor == D("132.00")


def test_shallow_shop_has_only_the_zones_it_reaches():
    result = itza.calculate({"mode": "rectangle", "width": "5", "depth": "8"})  # default 6.1 m zones
    assert [(r.label, r.area) for r in result.rows] == [("Zone A", D("30.50")), ("Zone B", D("9.50"))]
    assert result.total == D("35.25")


def test_measured_zones_other_areas_and_a_trial_rate():
    result = itza.calculate({
        "zone_depth": "6.1", "mode": "zones", "zones": ["40", "35", "20", ""],
        "others": [{"label": "First floor sales", "area": "60", "divisor": "8"},
                   {"label": "Storage", "area": "30", "divisor": "10"}, {}],
        "zone_a_rate": "250"})
    assert result.ok
    # 40 + 17.5 + 5 + 7.5 (60/8) + 3 (30/10)
    assert result.total == D("73.00")
    assert result.rows[-2].fraction_text == "A/8" and result.rows[-1].itza == D("3.00")
    assert result.rent_at_rate == D("18250.00")


def test_problems_are_explained():
    assert "Enter the internal width." in itza.calculate({"mode": "rectangle", "depth": "10"}).errors
    result = itza.calculate({"mode": "zones", "zones": ["20"], "others": [{"label": "Store", "area": "10"}]})
    assert any("fraction of Zone A for Store" in e for e in result.errors)


@pytest.fixture
def surveyor(make_user):
    return make_user("sue", "Surveyors", email="sue@example.org")


@pytest.fixture
def shop(db, surveyor):
    unit = Property.objects.create(reference="S1", name="1 High Street", property_type="unit",
                                   managing_surveyor=surveyor)
    tenant = Party.objects.create(name="Bakery Ltd", party_type="company")
    lease = Lease.objects.create(reference="L-S1", agreement_type="lease", counterparty=tenant,
                                 term_start=date(2024, 1, 1), annual_rent=D("16707.50"))
    lease.properties.add(unit)
    return unit


def test_calculator_saves_the_itza_and_the_rent_per_m2_zone_a_shows(shop, surveyor, client):
    client.force_login(surveyor)
    response = client.post(f"/properties/{shop.pk}/itza/", {
        "zone_depth": "6.1", "mode": "rectangle", "width": "6", "depth": "22", "save": "1",
        "notes": "Measured on site", "other_divisor_0": ""})
    assert response.status_code == 302
    shop.refresh_from_db()
    assert shop.itza_sqm == D("66.83") and shop.itza_zone_depth_m == D("6.10")
    assert shop.itza_workings["width"] == "6" and shop.itza_notes == "Measured on site"
    lease, rate = shop.zone_a_rent()
    assert rate == D("250.00")  # 16,707.50 ÷ 66.83
    page = client.get(shop.get_absolute_url()).content.decode()
    assert "ITZA 66.83 m²" in page and "£250.00" in page
    assert "per m² Zone A" in client.get(lease.get_absolute_url()).content.decode()
    # The saved workings are shown again.
    assert 'value="22"' in client.get(f"/properties/{shop.pk}/itza/").content.decode()


def test_viewers_can_calculate_but_not_save(shop, make_user, client):
    client.force_login(make_user("vic", "Viewers"))
    data = {"zone_depth": "6.1", "mode": "rectangle", "width": "6", "depth": "22"}
    assert "Total ITZA" in client.post(f"/properties/{shop.pk}/itza/", {**data, "calculate": "1"}).content.decode()
    assert client.post(f"/properties/{shop.pk}/itza/", {**data, "save": "1"}).status_code == 403


def test_no_zone_a_rent_for_a_lease_over_several_units(shop):
    shop.itza_sqm = D("50")
    shop.save()
    other = Property.objects.create(reference="S2", name="2 High Street", property_type="unit")
    shop.leases.first().properties.add(other)
    assert shop.zone_a_rent() is None
