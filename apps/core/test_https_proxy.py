# SPDX-License-Identifier: AGPL-3.0-or-later
"""PHAEMA behind a reverse proxy that ends HTTPS: settings come from the environment and sign-in works."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.contrib.auth.models import User
from django.test import Client

BASE_DIR = Path(__file__).resolve().parent.parent.parent
HOST = "phaema.example.gov.uk"


def _settings_with(**env):
    """Load phaema.settings in a fresh Python with these environment variables."""
    code = ("import django, json; django.setup(); from django.conf import settings as s; "
            "print(json.dumps([s.CSRF_TRUSTED_ORIGINS, getattr(s, 'SECURE_PROXY_SSL_HEADER', None)]))")
    environment = {**os.environ, "DJANGO_SETTINGS_MODULE": "phaema.settings", **env}
    for name in ("BEHIND_HTTPS_PROXY", "CSRF_TRUSTED_ORIGINS", "PHAEMA_BASE_URL"):
        if name not in env:
            environment.pop(name, None)
    out = subprocess.run([sys.executable, "-c", code], cwd=BASE_DIR, env=environment,
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_local_defaults_trust_no_proxy():
    origins, header = _settings_with()
    assert origins == [] and header is None


def test_https_base_url_is_trusted_and_proxy_header_used():
    origins, header = _settings_with(BEHIND_HTTPS_PROXY="True", PHAEMA_BASE_URL=f"https://{HOST}/",
                                     CSRF_TRUSTED_ORIGINS="https://other.example.gov.uk")
    assert origins == ["https://other.example.gov.uk", f"https://{HOST}"]
    assert header == ["HTTP_X_FORWARDED_PROTO", "https"]


@pytest.mark.django_db
def test_sign_in_through_https_proxy(settings):
    settings.ALLOWED_HOSTS = [HOST]
    settings.SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    settings.CSRF_TRUSTED_ORIGINS = [f"https://{HOST}"]
    User.objects.create_superuser("proxy.admin", "a@example.org", "proxy-pass-12345")
    client = Client(enforce_csrf_checks=True, HTTP_HOST=HOST, HTTP_X_FORWARDED_PROTO="https")

    page = client.get("/login/")
    token = page.cookies["csrftoken"].value
    response = client.post("/login/", {"username": "proxy.admin", "password": "proxy-pass-12345",
                                       "csrfmiddlewaretoken": token},
                           HTTP_ORIGIN=f"https://{HOST}", HTTP_REFERER=f"https://{HOST}/login/")
    assert response.status_code == 302


@pytest.mark.django_db
def test_sign_in_refused_without_the_fix(settings):
    """Without the proxy header setting, the https origin does not match and Django refuses the form."""
    settings.ALLOWED_HOSTS = [HOST]
    settings.CSRF_TRUSTED_ORIGINS = []
    if hasattr(settings, "SECURE_PROXY_SSL_HEADER"):
        settings.SECURE_PROXY_SSL_HEADER = None
    client = Client(enforce_csrf_checks=True, HTTP_HOST=HOST)
    token = client.get("/login/").cookies["csrftoken"].value
    response = client.post("/login/", {"username": "x", "password": "y", "csrfmiddlewaretoken": token},
                           HTTP_ORIGIN=f"https://{HOST}")
    assert response.status_code == 403
