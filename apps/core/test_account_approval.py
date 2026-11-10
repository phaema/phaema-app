# SPDX-License-Identifier: AGPL-3.0-or-later
"""Approving a test account request creates the sign-in and emails the person a link to choose a password."""
import re

import pytest
from django.contrib.auth.models import User
from django.core import mail
from django.urls import reverse

from apps.core.account_requests import approve
from apps.core.models import AccessArea, AccountRequest
from apps.core.roles import ADMINISTRATORS, SURVEYORS


@pytest.fixture
def req(db):
    return AccountRequest.objects.create(name="Jo Bloggs", email="Jo.Bloggs@example.gov.uk", organisation="Example DC")


def test_approve_creates_user_and_emails_link(req, settings):
    settings.PHAEMA_ACCOUNT_REQUEST_EMAIL = "stuart@phaema.co.uk"
    user, created, link, emailed = approve(req, SURVEYORS)
    assert created and emailed
    assert user.username == "jo.bloggs" and user.first_name == "Jo" and user.last_name == "Bloggs"
    assert list(user.groups.values_list("name", flat=True)) == [SURVEYORS]
    assert user.access_areas.count() == AccessArea.objects.count() > 0
    assert not user.has_usable_password()
    req.refresh_from_db()
    assert req.done
    message = mail.outbox[-1]
    assert message.to == ["Jo.Bloggs@example.gov.uk"]
    assert message.reply_to == ["stuart@phaema.co.uk"]
    assert "jo.bloggs" in message.body and link in message.body


def test_link_sets_password_once_and_then_signs_in(client, req):
    user, _created, link, _emailed = approve(req, SURVEYORS)
    path = re.sub(r"^https?://[^/]+", "", link)
    response = client.get(path)  # redirects to the same view without the token in the URL
    form_url = response.url
    assert client.get(form_url).context["validlink"]
    response = client.post(form_url, {"new_password1": "correct horse battery staple",
                                      "new_password2": "correct horse battery staple"})
    assert response.url == reverse("set-password-done")
    assert client.login(username="jo.bloggs", password="correct horse battery staple")
    client.logout()
    again = client.get(path, follow=True)
    assert not again.context["validlink"]  # used once


def test_approving_again_reuses_the_account(req):
    first, *_ = approve(req, SURVEYORS)
    second, created, _link, _emailed = approve(req, ADMINISTRATORS)
    assert not created and first.pk == second.pk
    assert list(second.groups.values_list("name", flat=True)) == [ADMINISTRATORS]


def test_username_does_not_clash_or_look_like_demo_people(db, make_user):
    make_user("jo.bloggs")
    req = AccountRequest.objects.create(name="Jo", email="jo.bloggs@other.org")
    user, *_ = approve(req, SURVEYORS)
    assert user.username == "jo.bloggs2"
    demo = AccountRequest.objects.create(name="Demo", email="demo.person@x.org")
    assert approve(demo, SURVEYORS)[0].username == "t.demo.person"


def test_failed_email_still_creates_account(req, settings, monkeypatch):
    def broken(*args, **kwargs):
        raise OSError("mail server down")

    monkeypatch.setattr("django.core.mail.EmailMessage.send", broken)
    user, created, link, emailed = approve(req, SURVEYORS)
    assert created and not emailed and link.startswith(settings.PHAEMA_BASE_URL.rstrip("/"))


def test_admin_action(client, make_user, req):
    client.force_login(make_user("ann", ADMINISTRATORS))
    response = client.post(reverse("admin:core_accountrequest_changelist"),
                           {"action": "approve_surveyor", "_selected_action": [req.pk]}, follow=True)
    assert User.objects.filter(email="Jo.Bloggs@example.gov.uk").exists()
    assert b"emailed" in response.content
    assert len(mail.outbox) == 1


def test_change_password(client, make_user):
    client.force_login(make_user("sue", SURVEYORS))
    response = client.post(reverse("change-password"), {"old_password": "a-long-test-password",
                                                        "new_password1": "another long test phrase",
                                                        "new_password2": "another long test phrase"})
    assert response.url == reverse("change-password-done")
