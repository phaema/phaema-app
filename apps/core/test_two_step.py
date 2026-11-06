# SPDX-License-Identifier: AGPL-3.0-or-later
"""Two-step sign-in: codes, signing in, setting up, the council's rule, the admin reset and the API."""
import base64

import pytest
from django.urls import reverse

from apps.core import two_step
from apps.core.models import AuditEntry, ModuleSettings, RecoveryCode, TwoStepDevice
from apps.core.roles import ADMINISTRATORS, SURVEYORS

PASSWORD = "a-long-test-password"


def now_code(secret):
    return two_step.code_at(secret, two_step.current_step())


def test_rfc6238_test_vector():
    # RFC 6238 appendix B, SHA-1: secret "12345678901234567890", time 59 -> 94287082 (8 digits; we use the last 6).
    secret = base64.b32encode(b"12345678901234567890").decode()
    assert two_step.code_at(secret, two_step.current_step(59)) == "287082"
    assert two_step.code_at(secret, two_step.current_step(1111111109)) == "081804"


def test_code_accepted_within_drift_and_only_once():
    secret = two_step.new_secret()
    step = two_step.current_step()
    assert two_step.matching_step(secret, two_step.code_at(secret, step - 1)) == step - 1
    assert two_step.matching_step(secret, two_step.code_at(secret, step - 3)) is None
    assert two_step.matching_step(secret, two_step.code_at(secret, step), after_step=step) is None
    assert two_step.matching_step(secret, "12 34") is None


@pytest.fixture
def sue(make_user):
    return make_user("sue", SURVEYORS)


@pytest.fixture
def sue_with_app(sue):
    secret = two_step.new_secret()
    TwoStepDevice.objects.create(user=sue, secret=secret)
    codes = two_step.new_recovery_codes(sue)
    return sue, secret, codes


def sign_in(client, username):
    return client.post(reverse("login"), {"username": username, "password": PASSWORD})


def test_without_two_step_password_signs_in(client, sue):
    response = sign_in(client, "sue")
    assert response.status_code == 302
    assert "_auth_user_id" in client.session


def test_with_two_step_password_alone_does_not_sign_in(client, sue_with_app):
    sue, secret, _codes = sue_with_app
    response = sign_in(client, "sue")
    assert response.url == reverse("login-code")
    assert "_auth_user_id" not in client.session
    assert client.get(reverse("dashboard")).status_code == 302  # still signed out

    response = client.post(reverse("login-code"), {"code": now_code(secret)})
    assert response.status_code == 302
    assert client.session["_auth_user_id"] == str(sue.pk)


def test_code_cannot_be_reused(client, sue_with_app):
    _sue, secret, _codes = sue_with_app
    code = now_code(secret)
    sign_in(client, "sue")
    client.post(reverse("login-code"), {"code": code})
    client.logout()
    sign_in(client, "sue")
    response = client.post(reverse("login-code"), {"code": code})
    assert response.status_code == 200
    assert "_auth_user_id" not in client.session


def test_recovery_code_works_once(client, sue_with_app):
    _sue, _secret, codes = sue_with_app
    sign_in(client, "sue")
    client.post(reverse("login-code"), {"code": codes[0].upper()})
    assert "_auth_user_id" in client.session
    assert two_step.recovery_codes_left(_sue) == 9
    client.logout()
    sign_in(client, "sue")
    client.post(reverse("login-code"), {"code": codes[0]})
    assert "_auth_user_id" not in client.session


def test_too_many_wrong_codes_restarts_sign_in(client, sue_with_app):
    sign_in(client, "sue")
    for _ in range(4):
        assert client.post(reverse("login-code"), {"code": "000000"}).status_code == 200
    response = client.post(reverse("login-code"), {"code": "000000"})
    assert response.url == reverse("login")
    assert client.get(reverse("login-code")).url == reverse("login")


def test_code_step_without_password_step_goes_to_sign_in(client):
    assert client.get(reverse("login-code")).url == reverse("login")


def test_next_is_kept_and_checked(client, sue_with_app):
    _sue, secret, _codes = sue_with_app
    client.post(reverse("login"), {"username": "sue", "password": PASSWORD, "next": "/properties/"})
    assert client.post(reverse("login-code"), {"code": now_code(secret)}).url == "/properties/"


def test_set_up_and_turn_off(client, sue):
    client.force_login(sue)
    client.post(reverse("two-step"), {"action": "start"})
    page = client.get(reverse("two-step"))
    assert b"<svg" in page.content
    secret = client.session["two_step_setup_secret"]

    wrong = client.post(reverse("two-step"), {"action": "confirm", "code": "000000"})
    assert b"did not match" in wrong.content
    client.post(reverse("two-step"), {"action": "confirm", "code": now_code(secret)})
    shown = client.get(reverse("two-step"))
    assert shown.content.count(b"<li><code>") == 10
    assert TwoStepDevice.objects.filter(user=sue).exists()
    assert RecoveryCode.objects.filter(user=sue).count() == 10
    assert b"<li><code>" not in client.get(reverse("two-step")).content  # codes shown once only
    assert AuditEntry.objects.filter(object_id=str(sue.pk), changes__has_key="two-step sign-in").exists()

    device = TwoStepDevice.objects.get(user=sue)
    next_code = two_step.code_at(secret, device.last_step + 1)
    client.post(reverse("two-step"), {"action": "turn-off", "password": PASSWORD, "code": next_code})
    assert not TwoStepDevice.objects.filter(user=sue).exists()
    assert not RecoveryCode.objects.filter(user=sue).exists()


def test_turning_off_needs_password_and_code(client, sue_with_app):
    sue, secret, _codes = sue_with_app
    client.force_login(sue)
    client.post(reverse("two-step"), {"action": "turn-off", "password": "wrong", "code": now_code(secret)})
    client.post(reverse("two-step"), {"action": "turn-off", "password": PASSWORD, "code": "000000"})
    assert TwoStepDevice.objects.filter(user=sue).exists()


@pytest.mark.two_step
def test_administrators_must_set_it_up_by_default(client, make_user, sue):
    ann = make_user("ann", ADMINISTRATORS)
    assert ModuleSettings.load().two_step_required == ModuleSettings.TwoStep.ADMINISTRATORS
    client.force_login(ann)
    assert client.get(reverse("dashboard")).url == reverse("two-step")
    assert client.get(reverse("two-step")).status_code == 200
    assert client.get("/api/properties/").status_code == 403
    client.force_login(sue)
    assert client.get(reverse("dashboard")).status_code == 200


@pytest.mark.two_step
def test_required_for_everyone_and_cannot_be_turned_off(client, sue_with_app):
    sue, secret, _codes = sue_with_app
    settings_row = ModuleSettings.load()
    settings_row.two_step_required = ModuleSettings.TwoStep.EVERYONE
    settings_row.save()
    assert two_step.is_required(sue)
    client.force_login(sue)
    client.post(reverse("two-step"), {"action": "turn-off", "password": PASSWORD, "code": now_code(secret)})
    assert TwoStepDevice.objects.filter(user=sue).exists()


@pytest.mark.two_step
def test_never_required_on_the_public_test_site(settings, make_user):
    settings.PHAEMA_DEMO_SITE = True
    assert not two_step.is_required(make_user("ann", ADMINISTRATORS))


def test_admin_sign_in_goes_through_phaema_sign_in(client):
    response = client.get("/admin/login/?next=/admin/")
    assert response.url.startswith(reverse("login"))


def test_administrator_can_reset_a_lost_phone(client, make_user, sue_with_app):
    sue, _secret, _codes = sue_with_app
    ann = make_user("ann", ADMINISTRATORS)
    client.force_login(ann)
    client.post(reverse("admin:auth_user_changelist"),
                {"action": "reset_two_step", "_selected_action": [sue.pk]})
    assert not TwoStepDevice.objects.filter(user=sue).exists()


def test_api_password_sign_in_refused_with_two_step(client, sue, sue_with_app):
    auth = "Basic " + base64.b64encode(f"sue:{PASSWORD}".encode()).decode()
    assert client.get("/api/properties/", HTTP_AUTHORIZATION=auth).status_code in (401, 403)


def test_api_password_sign_in_still_works_without_two_step(client, sue):
    auth = "Basic " + base64.b64encode(f"sue:{PASSWORD}".encode()).decode()
    assert client.get("/api/properties/", HTTP_AUTHORIZATION=auth).status_code == 200
