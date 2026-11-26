# SPDX-License-Identifier: AGPL-3.0-or-later
"""API tokens: made and shown once, limited by access and parts, end dates, cancelling, and the change log."""
import base64
from datetime import date, timedelta

import pytest
from django.urls import reverse

from apps.core.models import ApiToken, AuditEntry
from apps.core.roles import ADMINISTRATORS, SURVEYORS, VIEWERS
from apps.properties.models import Property

PASSWORD = "a-long-test-password"


@pytest.fixture
def ann(make_user):
    return make_user("ann", ADMINISTRATORS)


@pytest.fixture
def sue(make_user):
    return make_user("sue", SURVEYORS)


def make_token(user, access=ApiToken.Access.READ, resources=(), days=30, **extra):
    token = ApiToken(name="Test system", user=user, access=access, resources=list(resources),
                     expires_on=date.today() + timedelta(days=days), **extra)
    key = token.issue()
    token.save()
    return token, key


def bearer(key):
    return {"HTTP_AUTHORIZATION": f"Bearer {key}"}


@pytest.fixture
def prop(sue):
    return Property.objects.create(reference="T-1", name="Test unit", property_type="unit", managing_surveyor=sue)


def test_key_is_kept_only_as_a_hash(sue):
    token, key = make_token(sue)
    assert key.startswith("phaema_") and len(key) > 40
    assert token.key_hash == ApiToken.hash(key) and key not in token.key_hash
    assert token.prefix == key[:12]


def test_read_token_reads(client, sue, prop):
    _token, key = make_token(sue)
    resp = client.get("/api/properties/", **bearer(key))
    assert resp.status_code == 200
    assert resp.json()["count"] >= 1


def test_wrong_or_missing_token_refused(client, sue):
    make_token(sue)
    resp = client.get("/api/properties/", **bearer("phaema_not-a-real-token"))
    assert resp.status_code in (401, 403) and resp.json()["detail"] == "That token is not valid."
    assert client.get("/api/properties/").status_code in (401, 403)


def test_read_only_token_cannot_change(client, sue, prop):
    _token, key = make_token(sue)
    resp = client.patch(f"/api/properties/{prop.pk}/", {"name": "Renamed"}, content_type="application/json",
                        **bearer(key))
    assert resp.status_code == 403
    assert "read only" in resp.json()["detail"]
    prop.refresh_from_db()
    assert prop.name == "Test unit"


def test_change_token_changes_and_is_named_in_the_change_log(client, sue, prop):
    token, key = make_token(sue, access=ApiToken.Access.CHANGE)
    resp = client.patch(f"/api/properties/{prop.pk}/", {"name": "Renamed"}, content_type="application/json",
                        **bearer(key))
    assert resp.status_code == 200
    entry = AuditEntry.objects.filter(object_id=str(prop.pk), action="update").latest("timestamp")
    assert entry.user == sue
    assert entry.via == f"API token: {token}"


def test_token_never_exceeds_its_accounts_role(client, make_user, prop):
    viewer = make_user("val", VIEWERS)
    _token, key = make_token(viewer, access=ApiToken.Access.CHANGE)
    resp = client.patch(f"/api/properties/{prop.pk}/", {"name": "Renamed"}, content_type="application/json",
                        **bearer(key))
    assert resp.status_code == 403


def test_token_limited_to_parts_of_the_api(client, sue):
    _token, key = make_token(sue, resources=["property"])
    assert client.get("/api/properties/", **bearer(key)).status_code == 200
    resp = client.get("/api/leases/", **bearer(key))
    assert resp.status_code == 403
    assert "cannot use this part" in resp.json()["detail"]


def test_ended_and_cancelled_tokens_refused(client, sue):
    from django.utils import timezone

    ended, ended_key = make_token(sue, days=-1)
    resp = client.get("/api/properties/", **bearer(ended_key))
    assert resp.status_code in (401, 403) and "end date" in resp.json()["detail"]
    cancelled, key = make_token(sue)
    assert client.get("/api/properties/", **bearer(key)).status_code == 200
    cancelled.revoked_at = timezone.now()
    cancelled.save()
    assert client.get("/api/properties/", **bearer(key)).status_code in (401, 403)


def test_token_stops_when_the_account_stops(client, sue):
    _token, key = make_token(sue)
    sue.is_active = False
    sue.save()
    assert client.get("/api/properties/", **bearer(key)).status_code in (401, 403)


def test_token_stops_when_outside_access_ends(client, sue):
    from apps.core.models import StaffProfile

    _token, key = make_token(sue)
    StaffProfile.objects.update_or_create(user=sue, defaults={"access_ends": date.today() - timedelta(days=1)})
    sue.refresh_from_db()
    assert client.get("/api/properties/", **bearer(key)).status_code in (401, 403)


def test_token_works_for_an_account_with_two_step(client, sue):
    from apps.core import two_step
    from apps.core.models import TwoStepDevice

    TwoStepDevice.objects.create(user=sue, secret=two_step.new_secret())
    _token, key = make_token(sue)
    assert client.get("/api/properties/", **bearer(key)).status_code == 200


def test_last_use_recorded_without_a_change_log_entry(client, sue):
    token, key = make_token(sue)
    before = AuditEntry.objects.count()
    client.get("/api/properties/", **bearer(key), REMOTE_ADDR="192.0.2.7")
    token.refresh_from_db()
    assert token.last_used_at is not None
    assert token.last_used_from == "192.0.2.7"
    assert AuditEntry.objects.count() == before


def test_password_sign_in_off_by_default(client, sue, settings):
    auth = "Basic " + base64.b64encode(f"sue:{PASSWORD}".encode()).decode()
    assert client.get("/api/properties/", HTTP_AUTHORIZATION=auth).status_code in (401, 403)
    settings.PHAEMA_API_PASSWORD_SIGN_IN = True
    assert client.get("/api/properties/", HTTP_AUTHORIZATION=auth).status_code == 200


def test_password_sign_in_changes_are_named_in_the_change_log(client, sue, prop, settings):
    settings.PHAEMA_API_PASSWORD_SIGN_IN = True
    auth = "Basic " + base64.b64encode(f"sue:{PASSWORD}".encode()).decode()
    client.patch(f"/api/properties/{prop.pk}/", {"name": "Renamed"}, content_type="application/json",
                 HTTP_AUTHORIZATION=auth)
    entry = AuditEntry.objects.filter(object_id=str(prop.pk), action="update").latest("timestamp")
    assert entry.user == sue
    assert entry.via == "API: username and password"


# ------------------------------------------------------------------ Manage data

def _add(client, user, **overrides):
    data = {"name": "GIS layers", "user": user.pk, "access": "read", "resources": ["property", "lease"],
            "expires_on": (date.today() + timedelta(days=365)).isoformat()}
    data.update(overrides)
    return client.post(reverse("admin:core_apitoken_add"), data)


def test_administrator_makes_a_token_and_sees_the_key_once(client, ann, sue):
    client.force_login(ann)
    resp = _add(client, sue)
    assert resp.status_code == 200
    token = ApiToken.objects.get()
    key = resp.context["key"]
    assert ApiToken.hash(key) == token.key_hash
    assert key.encode() in resp.content
    assert "no-store" in resp["Cache-Control"]
    assert token.created_by == ann and token.resources == ["property", "lease"]
    page = client.get(reverse("admin:core_apitoken_change", args=[token.pk]))
    assert key.encode() not in page.content
    entry = AuditEntry.objects.filter(object_repr=str(token), action="create").get()
    assert "key_hash" not in entry.changes


def test_end_date_limited_to_two_years(client, ann, sue):
    client.force_login(ann)
    resp = _add(client, sue, expires_on=(date.today() + timedelta(days=800)).isoformat())
    assert resp.status_code == 200 and not ApiToken.objects.exists()
    assert b"at most two years" in resp.content


def test_only_administrators_see_tokens(client, sue):
    make_token(sue)
    client.force_login(sue)
    assert client.get(reverse("admin:core_apitoken_changelist")).status_code == 403
    assert client.get(reverse("admin:core_apitoken_add")).status_code == 403


def test_cancelling_stops_the_token_and_is_logged(client, ann, sue):
    token, key = make_token(sue)
    client.force_login(ann)
    client.post(reverse("admin:core_apitoken_changelist"),
                {"action": "cancel_tokens", "_selected_action": [token.pk]})
    token.refresh_from_db()
    assert token.revoked_at is not None and token.revoked_by == ann
    assert AuditEntry.objects.filter(object_repr=str(token), action="update").exists()
    client.logout()
    assert client.get("/api/properties/", **bearer(key)).status_code in (401, 403)


def test_tokens_cannot_be_deleted(client, ann, sue):
    token, _key = make_token(sue)
    client.force_login(ann)
    assert client.post(reverse("admin:core_apitoken_delete", args=[token.pk]), {"post": "yes"}).status_code == 403
    assert ApiToken.objects.filter(pk=token.pk).exists()


def test_token_ending_soon_shown_to_the_administrator_who_made_it(ann, sue):
    from apps.core import mywork

    make_token(sue, days=10, created_by=ann)
    make_token(sue, days=200, created_by=ann)
    data = mywork.build(ann)
    items = [i for i in data["ahead"] if i.kind == "API token ends"]
    assert len(items) == 1
