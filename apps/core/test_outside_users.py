# SPDX-License-Identifier: AGPL-3.0-or-later
"""Outside users: a marker, and an access end date that is enforced everywhere."""
from datetime import date, timedelta

import pytest
from django.urls import reverse

from apps.core import outside
from apps.core.dates import add_months
from apps.core.models import ModuleSettings, StaffProfile

PASSWORD = "a-long-test-password"


@pytest.fixture
def consultant(make_user):
    user = make_user("consultant", "Viewers", email="c@firm.example")
    StaffProfile.objects.create(user=user, is_external=True, organisation="Acme Surveyors")
    return user


def test_outside_user_gets_default_end_date(consultant):
    settings = ModuleSettings.load()
    assert consultant.staff_profile.access_ends == add_months(date.today(), settings.outside_access_months)
    assert settings.outside_access_months == 6


def test_default_period_follows_module_settings(make_user):
    settings = ModuleSettings.load()
    settings.outside_access_months = 3
    settings.save()
    user = make_user("agent", "Viewers")
    profile = StaffProfile.objects.create(user=user, is_external=True)
    assert profile.access_ends == add_months(date.today(), 3)


def test_administrator_can_set_own_date_and_staff_need_none(make_user):
    chosen = date.today() + timedelta(days=40)
    agent = make_user("agent2", "Viewers")
    assert StaffProfile.objects.create(user=agent, is_external=True, access_ends=chosen).access_ends == chosen
    staff = make_user("officer", "Surveyors")
    assert StaffProfile.objects.create(user=staff).access_ends is None
    assert not outside.access_ended(staff)


def _end(user, days_from_today):
    profile = user.staff_profile
    profile.access_ends = date.today() + timedelta(days=days_from_today)
    profile.save()


def test_last_day_still_works_and_day_after_is_refused(client, consultant):
    _end(consultant, 0)
    assert client.login(username="consultant", password=PASSWORD)
    client.logout()
    _end(consultant, -1)
    assert not client.login(username="consultant", password=PASSWORD)
    resp = client.post(reverse("login"), {"username": "c@firm.example", "password": PASSWORD})
    assert "_auth_user_id" not in client.session
    assert resp.status_code == 200


def test_signed_in_person_is_signed_out_when_access_ends(client, consultant):
    assert client.login(username="consultant", password=PASSWORD)
    _end(consultant, -1)
    resp = client.get(reverse("dashboard"))
    assert resp.status_code == 403
    assert b"Your access to PHAEMA has ended" in resp.content
    assert "_auth_user_id" not in client.session


def test_api_refuses_ended_access(client, consultant, settings):
    import base64

    settings.PHAEMA_API_PASSWORD_SIGN_IN = True

    _end(consultant, -1)
    token = base64.b64encode(f"consultant:{PASSWORD}".encode()).decode()
    resp = client.get("/api/", HTTP_AUTHORIZATION=f"Basic {token}")
    assert resp.status_code in (401, 403)


def test_warning_banner_in_last_fortnight(client, consultant):
    _end(consultant, 10)
    client.login(username="consultant", password=PASSWORD)
    resp = client.get(reverse("dashboard"))
    assert b"Your access to PHAEMA ends after" in resp.content
    _end(consultant, 60)
    assert b"Your access to PHAEMA ends after" not in client.get(reverse("dashboard")).content


def test_daily_housekeeping_closes_ended_accounts(consultant, make_user):
    _end(consultant, -1)
    other = make_user("still-ok", "Viewers")
    StaffProfile.objects.create(user=other, is_external=True)
    assert outside.close_ended() == 1
    consultant.refresh_from_db()
    other.refresh_from_db()
    assert not consultant.is_active and other.is_active


def test_ending_soon_lists_soonest_first(consultant, make_user):
    _end(consultant, 5)
    later = make_user("later", "Viewers")
    StaffProfile.objects.create(user=later, is_external=True, access_ends=date.today() + timedelta(days=12))
    assert [u.username for u in outside.ending_soon()] == ["consultant", "later"]


def test_user_list_shows_outside_users(client, make_user, consultant):
    make_user("boss", "Administrators")
    client.login(username="boss", password=PASSWORD)
    resp = client.get(reverse("admin:auth_user_changelist"))
    assert b"Acme Surveyors" in resp.content
