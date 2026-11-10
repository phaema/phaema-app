# SPDX-License-Identifier: AGPL-3.0-or-later
"""Signing in with an email address as well as a username."""
import pytest
from django.contrib.auth import authenticate, get_user_model
from django.urls import reverse

pytestmark = pytest.mark.django_db


@pytest.fixture
def pat():
    return get_user_model().objects.create_user("pat.surveyor", email="Pat@Council.example", password="correct-horse-9")


def test_sign_in_with_username_or_email(client, pat):
    for name in ("pat.surveyor", "pat@council.example", "PAT@COUNCIL.EXAMPLE", " pat@council.example "):
        client.logout()
        resp = client.post(reverse("login"), {"username": name, "password": "correct-horse-9"})
        assert resp.status_code == 302, name
        assert int(client.session["_auth_user_id"]) == pat.pk
    assert b"Username or email address" in client.get(reverse("login")).content


def test_wrong_password_or_unknown_email_is_refused(client, pat):
    assert authenticate(username="pat@council.example", password="wrong") is None
    assert authenticate(username="nobody@council.example", password="correct-horse-9") is None
    resp = client.post(reverse("login"), {"username": "pat@council.example", "password": "wrong"})
    assert resp.status_code == 200 and b"There is a problem" in resp.content


def test_inactive_and_shared_addresses_cannot_use_email(pat):
    User = get_user_model()
    User.objects.create_user("pat.second", email="pat@council.example", password="correct-horse-9")
    assert authenticate(username="pat@council.example", password="correct-horse-9") is None  # two people share it
    assert authenticate(username="pat.surveyor", password="correct-horse-9") == pat  # usernames still work
    User.objects.filter(username="pat.second").delete()
    pat.is_active = False
    pat.save()
    assert authenticate(username="pat@council.example", password="correct-horse-9") is None


def test_username_wins_over_someone_elses_email(pat):
    odd = get_user_model().objects.create_user("pat@council.example", email="odd@council.example", password="other-pass-77")
    assert authenticate(username="pat@council.example", password="other-pass-77") == odd


def test_email_sign_in_still_goes_through_two_step(client, pat):
    from apps.core import two_step
    from apps.core.models import TwoStepDevice

    TwoStepDevice.objects.create(user=pat, secret=two_step.new_secret())
    resp = client.post(reverse("login"), {"username": "pat@council.example", "password": "correct-horse-9"})
    assert resp.status_code == 302 and resp.url == reverse("login-code")
    assert "_auth_user_id" not in client.session
