# SPDX-License-Identifier: AGPL-3.0-or-later
"""The three roles: Administrators change anything, Surveyors their own properties, Viewers nothing."""
import pytest
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.urls import reverse

from apps.core.roles import ADMINISTRATORS, SURVEYORS, VIEWERS, can_edit, role_of
from apps.leases.models import Lease, Party
from apps.properties.models import Property, Title


@pytest.fixture
def demo(db):
    call_command("load_demo_data", verbosity=0)


@pytest.fixture
def admin_user(make_user):
    return make_user("ann", ADMINISTRATORS)


@pytest.fixture
def surveyor(make_user):
    return make_user("sue", SURVEYORS)


@pytest.fixture
def viewer(make_user):
    return make_user("vic", VIEWERS)


@pytest.fixture
def own_and_other(demo, surveyor):
    own = Property.objects.get(reference="DM-S06")
    own.managing_surveyor = surveyor
    own.save()
    other = Property.objects.get(reference="DM-E01-U01")  # managed by demo surveyor Alex Morgan
    return own, other


def test_groups_created_with_permissions(db):
    assert set(Group.objects.values_list("name", flat=True)) >= {ADMINISTRATORS, SURVEYORS, VIEWERS}
    viewers = Group.objects.get(name=VIEWERS)
    assert all(p.codename.startswith("view_") for p in viewers.permissions.all())
    assert Group.objects.get(name=SURVEYORS).permissions.filter(codename="change_property").exists()
    assert not Group.objects.get(name=SURVEYORS).permissions.filter(codename="delete_property").exists()
    assert Group.objects.get(name=ADMINISTRATORS).permissions.filter(codename="change_user").exists()


def test_staff_status_follows_role(make_user):
    user = make_user("x", VIEWERS)
    assert not user.is_staff and role_of(user) == VIEWERS
    user.groups.add(Group.objects.get(name=SURVEYORS))
    user.refresh_from_db()
    assert user.is_staff
    Group.objects.get(name=SURVEYORS).user_set.remove(user)  # reverse side
    user.refresh_from_db()
    assert not user.is_staff


def test_user_without_role_sees_nothing(client, make_user, demo):
    client.force_login(make_user("nobody"))
    resp = client.get(reverse("properties:list"))
    assert resp.status_code == 403 and b"not been given a role" in resp.content
    assert client.get("/api/properties/").status_code == 403


def test_can_edit_rules(own_and_other, admin_user, surveyor, viewer):
    own, other = own_and_other
    assert can_edit(admin_user, other) and can_edit(surveyor, own)
    assert not can_edit(surveyor, other) and not can_edit(viewer, own)
    lease_other = Lease.objects.get(reference="DL-0001")
    assert not can_edit(surveyor, lease_other) and can_edit(admin_user, lease_other)
    assert not can_edit(surveyor, Title.objects.first())
    assert can_edit(surveyor, Party.objects.first())


def test_viewer_is_read_only_everywhere(client, viewer, own_and_other):
    own, _other = own_and_other
    client.force_login(viewer)
    html = client.get(own.get_absolute_url()).content.decode()
    assert "Edit this property" not in html and "Manage data" not in html and "(viewer)" in html
    assert client.get(reverse("admin:index")).status_code == 302  # not staff: sent to admin login
    assert client.get(reverse("properties:boundary", args=[own.pk])).status_code == 403
    assert client.get(reverse("properties:import")).status_code == 403
    assert client.patch(f"/api/properties/{own.pk}/", {"name": "x"}, content_type="application/json").status_code == 403


def test_surveyor_can_change_own_property_only(client, surveyor, own_and_other):
    own, other = own_and_other
    client.force_login(surveyor)
    assert "Edit this property or add photos" in client.get(own.get_absolute_url()).content.decode()
    assert "Edit this property" not in client.get(other.get_absolute_url()).content.decode()

    change_own = reverse("admin:properties_property_change", args=[own.pk])
    change_other = reverse("admin:properties_property_change", args=[other.pk])
    assert b'name="name"' in client.get(change_own).content           # editable form
    assert b'name="name"' not in client.get(change_other).content     # read-only view
    resp = client.post(change_other, {"name": "Hacked"})
    other.refresh_from_db()
    assert resp.status_code == 403 and other.name == "Unit 1"

    # API: own yes, other no, and cannot reassign the surveyor
    url = f"/api/properties/{own.pk}/"
    assert client.patch(url, {"name": "Oak Street site"}, content_type="application/json").status_code == 200
    assert client.patch(f"/api/properties/{other.pk}/", {"name": "x"}, content_type="application/json").status_code == 403
    assert client.patch(url, {"managing_surveyor": None}, content_type="application/json").status_code == 403
    assert client.delete(url).status_code == 403
    assert client.post("/api/properties/", {"reference": "N1", "name": "N", "property_type": "site"},
                       content_type="application/json").status_code == 403
    # boundary tool on own property only
    assert client.get(reverse("properties:boundary", args=[own.pk])).status_code == 200
    assert client.get(reverse("properties:boundary", args=[other.pk])).status_code == 403
    assert client.get(reverse("properties:import")).status_code == 403


def test_surveyor_new_property_becomes_theirs_and_parent_must_be_own(client, surveyor, own_and_other):
    own, other = own_and_other
    client.force_login(surveyor)
    add = reverse("admin:properties_property_add")
    base = {"reference": "S-1", "name": "New store", "property_type": "building",
            "photos-TOTAL_FORMS": "0", "photos-INITIAL_FORMS": "0",
            "Title_properties-TOTAL_FORMS": "0", "Title_properties-INITIAL_FORMS": "0"}
    resp = client.post(add, {**base, "parent": other.pk})
    assert resp.status_code == 200 and b"only add parts to properties you manage" in resp.content
    resp = client.post(add, {**base, "parent": own.pk})
    assert resp.status_code == 302, resp.content[:2000]
    assert Property.objects.get(reference="S-1").managing_surveyor == surveyor


def test_surveyor_leases_limited_to_own_properties(client, surveyor, own_and_other):
    own, other = own_and_other
    client.force_login(surveyor)
    party = Party.objects.first()
    data = {"reference": "S-L1", "direction": "out", "agreement_type": "licence", "status": "current",
            "counterparty": party.pk, "term_start": "2026-01-01", "annual_rent": "100",
            "rent_frequency": "annually", "security_of_tenure": "na", "review_basis": "none",
            "breaks-TOTAL_FORMS": "0", "breaks-INITIAL_FORMS": "0"}
    resp = client.post(reverse("admin:leases_lease_add"), {**data, "properties": [other.pk]})
    assert resp.status_code == 200 and b"only add leases on properties you manage" in resp.content
    resp = client.post(reverse("admin:leases_lease_add"), {**data, "properties": [own.pk]})
    assert resp.status_code == 302
    lease = Lease.objects.get(reference="S-L1")
    assert can_edit(surveyor, lease)
    assert client.get(reverse("admin:leases_lease_change", args=[Lease.objects.get(reference="DL-0001").pk])
                      ).status_code == 200  # can view others' leases read-only


def test_administrator_can_change_anything_but_not_make_superusers(client, admin_user, make_user, own_and_other):
    _own, other = own_and_other
    client.force_login(admin_user)
    assert "Assign surveyors" in client.get(reverse("properties:list")).content.decode()
    assert client.get(reverse("properties:import")).status_code == 200
    assert client.patch(f"/api/properties/{other.pk}/", {"name": "Unit One"},
                        content_type="application/json").status_code == 200
    target = make_user("newbie")
    resp = client.get(reverse("admin:auth_user_change", args=[target.pk])).content.decode()
    assert 'name="is_superuser"' not in resp and 'name="groups"' in resp
    root = make_user("root", is_superuser=True, is_staff=True)
    assert b'name="username"' not in client.get(reverse("admin:auth_user_change", args=[root.pk])).content
