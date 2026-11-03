# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from django.contrib.gis.geos import MultiPolygon, Polygon
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.core.middleware import _current_user
from apps.core.models import AuditEntry, ModuleSettings
from apps.properties.models import Property, Title


@pytest.fixture
def user(make_user):
    return make_user("officer", "Administrators")


@pytest.fixture
def estate(db):
    return Property.objects.create(reference="E001", name="Riverside Industrial Estate", property_type="estate")


def test_uprn_must_be_numeric(db):
    p = Property(reference="X1", name="Test", property_type="site", uprn="ABC123")
    with pytest.raises(ValidationError):
        p.full_clean()


def test_postcode_is_normalised(db):
    p = Property(reference="X2", name="Test", property_type="site", postcode="ox49 5aa ")
    p.full_clean()
    assert p.postcode == "OX49 5AA"


def test_property_cannot_be_its_own_ancestor(estate):
    unit = Property.objects.create(reference="U1", name="Unit 1", property_type="unit", parent=estate)
    estate.parent = unit
    with pytest.raises(ValidationError):
        estate.full_clean()


def test_easting_northing_derived_from_boundary(db):
    square = Polygon(((460000, 195000), (460100, 195000), (460100, 195100), (460000, 195100), (460000, 195000)), srid=27700)
    p = Property.objects.create(reference="L1", name="Field", property_type="land", boundary=MultiPolygon(square, srid=27700))
    assert (p.easting, p.northing) == (460050, 195050)


def test_title_number_format(db):
    t = Title(title_number="on 123456", tenure="freehold")
    t.full_clean()
    assert t.title_number == "ON123456"
    with pytest.raises(ValidationError):
        Title(title_number="123", tenure="freehold").full_clean()


def test_audit_trail_records_create_and_change_with_user(user, estate):
    token = _current_user.set(user)
    try:
        estate.name = "Riverside Business Park"
        estate.save()
    finally:
        _current_user.reset(token)
    entries = AuditEntry.objects.filter(object_id=str(estate.pk)).order_by("timestamp")
    assert [e.action for e in entries] == ["create", "update"]
    assert entries[1].user == user
    assert entries[1].changes["name"] == ["Riverside Industrial Estate", "Riverside Business Park"]
    estate.refresh_from_db()
    assert estate.updated_by == user


def test_audit_entries_are_immutable(estate):
    entry = AuditEntry.objects.first()
    with pytest.raises(ValueError):
        entry.save()
    with pytest.raises(ValueError):
        entry.delete()


def test_module_settings_is_single_row(db):
    a = ModuleSettings.load()
    ModuleSettings(maintenance_enabled=True).save()
    assert ModuleSettings.objects.count() == 1
    assert ModuleSettings.load().maintenance_enabled and a.pk == 1


def test_pages_require_sign_in(client, estate):
    assert client.get(reverse("properties:list")).status_code == 302
    assert client.get(reverse("dashboard")).status_code == 302


def test_register_search_and_detail(client, user, estate):
    Property.objects.create(reference="U7", name="Unit 7", property_type="unit", parent=estate, postcode="OX49 5AA")
    client.force_login(user)
    resp = client.get(reverse("properties:list"), {"q": "OX49 5AA"})
    assert resp.status_code == 200
    assert b"Unit 7" in resp.content and b"E001" not in resp.content
    resp = client.get(reverse("properties:list"), {"property_type": "estate"})
    assert b"Riverside" in resp.content and b"Unit 7" not in resp.content
    resp = client.get(estate.get_absolute_url())
    assert resp.status_code == 200 and b"Unit 7" in resp.content
    assert client.get(reverse("dashboard")).status_code == 200


def test_api_requires_auth_and_lists(client, user, estate):
    assert client.get("/api/properties/").status_code == 403
    client.force_login(user)
    data = client.get("/api/properties/?property_type=estate").json()
    assert data["count"] == 1 and data["results"][0]["reference"] == "E001"
    assert client.get("/api/schema/").status_code == 200


def test_health(client, db):
    assert client.get("/health/").json() == {"status": "ok"}


def test_demo_data_loads_valid_records_and_is_repeatable(db):
    from django.core.management import call_command

    call_command("load_demo_data", verbosity=0)
    first_count = Property.objects.count()
    assert first_count > 30
    for p in Property.objects.all():
        p.full_clean()
    for t in Title.objects.all():
        t.full_clean()
    assert Property.objects.get(reference="DM-E01-U03").parent.parent.reference == "DM-E01"
    assert Property.objects.filter(exclude_from_publication=True).count() == 1
    assert ModuleSettings.load().organisation_name == "Demonstration District Council"

    call_command("load_demo_data", verbosity=0)  # running again must not duplicate
    assert Property.objects.count() == first_count
    assert Title.objects.count() == 8

    Property.objects.create(reference="REAL-1", name="A real council record", property_type="site")
    call_command("load_demo_data", "--reset", verbosity=0)  # reset leaves real records alone
    assert Property.objects.filter(reference="REAL-1").exists()
    assert Property.objects.count() == first_count + 1
