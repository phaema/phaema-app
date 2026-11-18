# SPDX-License-Identifier: AGPL-3.0-or-later
"""Space and costing, level 1: occupiers, floors, rooms and shared space, occupation, headcount and public use."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.core.models import AccessArea, ModuleSettings
from apps.properties.models import Property
from apps.space import summary
from apps.space.models import Headcount, Occupation, Occupier, Space, UseFigure, UseMeasure

PASSWORD = "a-long-test-password"
TODAY = date.today()


@pytest.fixture
def module_on(db):
    settings = ModuleSettings.load()
    settings.space_enabled = True
    settings.save()
    return settings


@pytest.fixture
def civic(db):
    building = Property.objects.create(reference="CC1", name="Civic Centre", property_type="building",
                                       holding_purpose="operational", nia_sqm=Decimal("2000"))
    place = Occupier.objects.create(name="Place", level="directorate")
    housing = Occupier.objects.create(name="Housing", parent=place)
    planning = Occupier.objects.create(name="Planning", parent=place)
    nhs = Occupier.objects.create(name="Community Health", level="external", external_kind="nhs")
    ground = Space.objects.create(building=building, kind="floor", name="Ground floor", level=0, area_sqm=1000)
    first = Space.objects.create(building=building, kind="floor", name="First floor", level=1, area_sqm=1000)
    Space.objects.create(building=building, kind="shared", name="Reception", floor=ground, area_sqm=100)
    office = Space.objects.create(building=building, kind="room", name="Office", floor=first, area_sqm=800,
                                  capacity=80)
    clinic = Space.objects.create(building=building, kind="room", name="Clinic", floor=ground, area_sqm=400,
                                  capacity=10)
    since = TODAY - timedelta(days=365)
    Occupation.objects.create(building=building, space=office, occupier=housing, share_percent=50, starts=since)
    Occupation.objects.create(building=building, space=office, occupier=planning, share_sqm=300, starts=since)
    Occupation.objects.create(building=building, space=clinic, occupier=nhs, starts=since)
    Headcount.objects.create(building=building, occupier=housing, people=50, counted_on=TODAY - timedelta(days=30))
    return {"building": building, "housing": housing, "planning": planning, "nhs": nhs, "place": place,
            "office": office, "ground": ground}


def test_share_by_percent_or_area(civic):
    housing, planning = (Occupation.objects.get(occupier=civic[k]) for k in ("housing", "planning"))
    assert housing.area() == Decimal("400.00") and housing.percent() == Decimal("50")
    assert planning.area() == Decimal("300") and planning.percent() == Decimal("37.5")


def test_cannot_give_both_percent_and_area(civic):
    o = Occupation(building=civic["building"], space=civic["office"], occupier=civic["housing"], share_percent=10,
                   share_sqm=10)
    with pytest.raises(ValidationError):
        o.full_clean()


def test_area_larger_than_space_is_refused(civic):
    o = Occupation(building=civic["building"], space=civic["office"], occupier=civic["housing"], share_sqm=900)
    with pytest.raises(ValidationError):
        o.full_clean()


def test_shares_over_100_percent_are_warned(civic):
    Occupation.objects.create(building=civic["building"], space=civic["office"], occupier=civic["place"],
                              share_percent=40)
    warnings = [w for r in summary.stacking(civic["building"]) for w in r.warnings]
    assert any("more than the whole space" in w for w in warnings)


def test_stacking_shows_top_floor_first_with_shared_and_vacant(civic):
    rows = summary.stacking(civic["building"])
    assert [r.name for r in rows] == ["First floor", "Ground floor"]
    first = {b.label: b.area for b in rows[0].blocks}
    assert first == {"Housing": Decimal("400.00"), "Planning": Decimal("300"), "Vacant": Decimal("300.00")}
    ground = {b.label: (b.kind, b.area) for b in rows[1].blocks}
    assert ground["Reception"] == ("shared", Decimal("100.00"))
    assert ground["Community Health"][0] == "occupier"
    assert ground["Vacant"] == ("vacant", Decimal("500.00"))


def test_holdings_share_out_shared_space_and_work_out_use(civic):
    held = {h.occupier.name: h for h in summary.holdings(civic["building"])}
    total_held = Decimal("400") + Decimal("300") + Decimal("400")
    assert held["Housing"].shared == (Decimal("100") * Decimal("400") / total_held).quantize(Decimal("0.01"))
    assert held["Housing"].capacity == 40  # half the office's 80 desks
    assert held["Housing"].people == 50 and held["Housing"].utilisation == 125
    assert held["Planning"].people is None and held["Planning"].utilisation is None


def test_ended_occupation_is_not_current_but_kept(civic):
    o = Occupation.objects.get(occupier=civic["planning"])
    o.ends = TODAY - timedelta(days=1)
    o.save()
    assert "Planning" not in {h.occupier.name for h in summary.holdings(civic["building"])}
    assert "Planning" in {h.occupier.name for h in summary.holdings(civic["building"], TODAY - timedelta(days=2))}


def test_whole_building_occupation(civic, db):
    library = Property.objects.create(reference="LIB", name="Library", property_type="building",
                                      nia_sqm=Decimal("600"))
    Occupation.objects.create(building=library, occupier=civic["housing"])
    rows = summary.stacking(library)
    assert rows[0].name == "Whole building" and rows[0].blocks[0].area == Decimal("600")


def test_directorate_includes_departments(civic):
    places = summary.occupier_buildings(civic["place"])
    assert len(places) == 1
    assert places[0][1].area == Decimal("700.00")


def test_room_floor_must_be_in_same_building(civic):
    other = Property.objects.create(reference="X", name="Other", property_type="building")
    room = Space(building=other, kind="room", name="R", floor=civic["ground"])
    with pytest.raises(ValidationError):
        room.full_clean()


def test_outside_organisation_cannot_sit_in_council_structure(civic):
    o = Occupier(name="Police", level="external", external_kind="police", parent=civic["place"])
    with pytest.raises(ValidationError):
        o.full_clean()


def test_public_use_figure_and_starting_measures(civic):
    from apps.space.seed import ensure_measures

    ensure_measures()
    hours = UseMeasure.objects.get(name="Hours used")
    figure = UseFigure.objects.create(building=civic["building"], measure=hours, period_start=date(2025, 4, 1),
                                      period_end=date(2026, 3, 31), value=1500, available=2000, source="Bookings")
    assert figure.percent() == Decimal("75.0")
    assert set(UseMeasure.objects.values_list("name", flat=True)) >= {"Visits", "Bookings", "Registered members"}


def test_module_off_hides_pages(client, make_user, civic):
    make_user("boss", "Administrators")
    client.login(username="boss", password=PASSWORD)
    resp = client.get(reverse("space:home"))
    assert resp.status_code == 404 and b"switched off" in resp.content
    assert b"Space and occupiers" not in client.get(civic["building"].get_absolute_url()).content


def test_pages_render_for_administrator(client, make_user, civic, module_on):
    make_user("boss", "Administrators")
    client.login(username="boss", password=PASSWORD)
    for url in (reverse("space:home"), reverse("space:building", args=[civic["building"].pk]),
                reverse("space:occupiers"), reverse("space:occupier", args=[civic["place"].pk])):
        resp = client.get(url)
        assert resp.status_code == 200, url
    page = client.get(reverse("space:building", args=[civic["building"].pk])).content.decode()
    assert "Stacking plan" in page and "Community Health" in page and "One Public Estate" in page
    assert b"Space and occupiers" in client.get(civic["building"].get_absolute_url()).content


def test_access_area_opens_the_module(client, make_user, civic, module_on):
    viewer = make_user("val", "Viewers")
    viewer.access_areas.clear()  # new people join the standard areas; Estates opens space
    client.login(username="val", password=PASSWORD)
    assert client.get(reverse("space:home")).status_code == 403
    area = AccessArea.objects.create(code="space-test", name="Space", modules=["space"])
    area.members.add(viewer)
    assert client.get(reverse("space:home")).status_code == 200


def test_surveyor_edits_spaces_only_for_own_buildings(make_user, civic):
    from apps.core.roles import can_edit

    sue = make_user("sue", "Surveyors")
    assert sue.has_perm("space.add_occupation") and not sue.has_perm("space.add_occupier")
    occupation = Occupation.objects.filter(building=civic["building"]).first()
    assert not can_edit(sue, occupation)
    civic["building"].managing_surveyor = sue
    civic["building"].save()
    occupation.building.refresh_from_db()
    assert can_edit(sue, Occupation.objects.get(pk=occupation.pk))


def test_changes_are_recorded_with_who(civic):
    from apps.core.models import AuditEntry

    assert AuditEntry.objects.filter(object_repr__startswith="Housing in").exists()


def test_demo_loads_and_removes(db):
    from apps.space import demo

    Property.objects.create(reference=demo.CIVIC, name="Exampleton Civic Centre", property_type="building",
                            nia_sqm=Decimal("3300"))
    assert demo.load() > 0
    civic = Property.objects.get(reference=demo.CIVIC)
    held = {h.occupier.name for h in summary.holdings(civic)}
    assert "Exampleton Community Health (NHS)" in held and len(held) == 6
    assert not [w for r in summary.stacking(civic) for w in r.warnings]
    demo.remove()
    assert not Space.objects.filter(building=civic).exists()
    assert not Occupier.objects.filter(name__in=demo.DEMO_NAMES).exists()
