# SPDX-License-Identifier: AGPL-3.0-or-later
"""Limits on guessing passwords, the client address, the secret key check and the idle sign-out."""
import base64
import subprocess
import sys
from pathlib import Path

import pytest
from django.test import RequestFactory

from apps.core import throttle
from apps.core.roles import SURVEYORS

PASSWORD = "a-long-test-password"
ROOT = str(Path(__file__).resolve().parents[2])


def _login(client, username, password):
    return client.post("/login/", {"username": username, "password": password})


def test_wrong_passwords_pause_sign_in_for_the_account(client, make_user, settings):
    settings.PHAEMA_SIGNIN_MAX_PER_ACCOUNT = 3
    make_user("pat", SURVEYORS)
    for _ in range(3):
        _login(client, "pat", "wrong")
    response = _login(client, "pat", PASSWORD)  # right password, but paused
    assert "_auth_user_id" not in client.session
    assert "Too many wrong passwords" in response.content.decode()


def test_a_right_password_clears_the_count(client, make_user, settings):
    settings.PHAEMA_SIGNIN_MAX_PER_ACCOUNT = 3
    make_user("pat", SURVEYORS)
    for _ in range(2):
        _login(client, "pat", "wrong")
    _login(client, "pat", PASSWORD)
    assert "_auth_user_id" in client.session
    client.logout()
    for _ in range(2):
        _login(client, "pat", "wrong")
    _login(client, "pat", PASSWORD)
    assert "_auth_user_id" in client.session


def test_one_connection_trying_many_accounts_is_paused(client, make_user, settings):
    settings.PHAEMA_SIGNIN_MAX_PER_ADDRESS = 4
    make_user("pat", SURVEYORS)
    for name in ("a", "b", "c", "d"):
        _login(client, name, "wrong")
    _login(client, "pat", PASSWORD)
    assert "_auth_user_id" not in client.session


def test_api_password_guessing_is_limited_too(client, make_user, settings):
    settings.PHAEMA_SIGNIN_MAX_PER_ACCOUNT = 3
    settings.PHAEMA_API_PASSWORD_SIGN_IN = True

    def api(password):
        token = base64.b64encode(f"pat:{password}".encode()).decode()
        return client.get("/api/properties/", HTTP_AUTHORIZATION=f"Basic {token}")

    make_user("pat", SURVEYORS)
    assert api(PASSWORD).status_code == 200
    for _ in range(3):
        assert api("wrong").status_code in (401, 403)
    assert api(PASSWORD).status_code in (401, 403)


def test_forwarded_address_believed_only_behind_the_proxy(settings):
    request = RequestFactory().get("/", REMOTE_ADDR="10.0.0.2", HTTP_X_FORWARDED_FOR="1.2.3.4, 203.0.113.9")
    settings.PHAEMA_BEHIND_HTTPS_PROXY = False
    assert throttle.client_ip(request) == "10.0.0.2"
    settings.PHAEMA_BEHIND_HTTPS_PROXY = True
    assert throttle.client_ip(request) == "203.0.113.9"  # the address the proxy added, not the one sent


def test_idle_sessions_are_signed_out(client, make_user, settings):
    make_user("pat", SURVEYORS)
    client.login(username="pat", password=PASSWORD)
    assert client.get("/").status_code == 200
    session = client.session
    session["phaema_last_seen"] -= settings.PHAEMA_IDLE_MINUTES * 60 + 1
    session.save()
    response = client.get("/leases/")
    assert response.status_code == 302 and response["Location"].startswith("/login/")
    assert "_auth_user_id" not in client.session


@pytest.mark.parametrize("key", ["", "insecure-development-key-change-me", "short"])
def test_server_refuses_to_start_without_a_proper_secret_key(key):
    env = {"SECRET_KEY": key, "DEBUG": "False", "DJANGO_SETTINGS_MODULE": "phaema.settings", "PATH": "/usr/bin:/bin"}
    result = subprocess.run([sys.executable, "-c", "import django; django.setup()"], env=env, cwd=ROOT,
                            capture_output=True, text=True)
    assert result.returncode != 0 and "SECRET_KEY" in result.stderr


def test_a_long_random_secret_key_is_accepted():
    env = {"SECRET_KEY": "x" * 50, "DEBUG": "False", "DJANGO_SETTINGS_MODULE": "phaema.settings", "PATH": "/usr/bin:/bin"}
    result = subprocess.run([sys.executable, "-c", "import django; django.setup()"], env=env,
                            cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
