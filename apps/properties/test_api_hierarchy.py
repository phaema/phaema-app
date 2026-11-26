# SPDX-License-Identifier: AGPL-3.0-or-later
"""The API runs the same checks as the screens: no property can be part of itself, directly or round a loop."""
import pytest
from django.contrib.auth.models import Group, User
from django.test import Client

from apps.properties.models import Property


@pytest.fixture
def api(db):
    user = User.objects.create_user("ann", password="a-long-test-password")
    user.groups.add(Group.objects.get(name="Administrators"))
    client = Client(HTTP_HOST="localhost")
    client.force_login(user)
    return client


@pytest.fixture
def estate(db):
    site = Property.objects.create(reference="S-1", name="Business park")
    block = Property.objects.create(reference="S-1-B1", name="Block A", parent=site)
    unit = Property.objects.create(reference="S-1-B1-U1", name="Unit 1", parent=block)
    return site, block, unit


def _patch(api, prop, data):
    return api.patch(f"/api/properties/{prop.pk}/", data, content_type="application/json")


def test_a_property_cannot_be_its_own_parent(api, estate):
    site, _block, _unit = estate
    response = _patch(api, site, {"parent": site.pk})
    assert response.status_code == 400
    assert "part of itself" in response.json()["parent"][0]
    site.refresh_from_db()
    assert site.parent_id is None


def test_no_loop_through_the_api(api, estate):
    site, block, unit = estate
    assert _patch(api, site, {"parent": unit.pk}).status_code == 400   # site -> unit -> block -> site
    assert _patch(api, block, {"parent": unit.pk}).status_code == 400  # block -> unit -> block
    site.refresh_from_db()
    block.refresh_from_db()
    assert site.parent_id is None and block.parent_id == site.pk


def test_new_and_moved_properties_still_work(api, estate):
    site, block, unit = estate
    response = api.post("/api/properties/", {"reference": "S-1-B2", "name": "Block B", "property_type": "building", "parent": site.pk},
                        content_type="application/json")
    assert response.status_code == 201, response.json()
    assert _patch(api, unit, {"parent": response.json()["id"]}).status_code == 200


def test_other_model_checks_run_too(api, estate):
    site, _block, _unit = estate
    response = _patch(api, site, {"easting": 450000})  # easting without northing
    assert response.status_code == 400


def test_walking_the_tree_stops_even_if_a_loop_got_into_the_database(estate):
    site, block, unit = estate
    Property.objects.filter(pk=site.pk).update(parent=unit)  # bad data, bypassing every check
    site.refresh_from_db()
    assert {p.pk for p, _depth in site.descendants()} == {block.pk, unit.pk}
    assert [p.pk for p in site.ancestors()] == [block.pk, unit.pk]
