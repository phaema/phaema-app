# SPDX-License-Identifier: AGPL-3.0-or-later
"""Forgotten password: a reset link by email."""
import re

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.urls import reverse

from apps.core import password_reset

pytestmark = pytest.mark.django_db
NEW = "four-unrelated-words-77"


@pytest.fixture(autouse=True)
def _clean(settings):
    settings.PHAEMA_BASE_URL = "http://testserver"
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def pat():
    return get_user_model().objects.create_user("pat.surveyor", email="Pat@Council.example", password="correct-horse-9",
                                                first_name="Pat")


def ask(client, identifier):
    return client.post(reverse("forgot-password"), {"identifier": identifier})


def link_in(message):
    return re.search(r"http://testserver(/account/reset-password/\S+)", message.body).group(1)


def test_sign_in_page_links_to_the_form(client):
    assert reverse("forgot-password").encode() in client.get(reverse("login")).content
    assert b"Email me a link" in client.get(reverse("forgot-password")).content


def test_reset_by_email_or_username(client, pat):
    for identifier in ("pat@council.example", "pat.surveyor"):
        mail.outbox.clear()
        resp = ask(client, identifier)
        assert b"Check your email" in resp.content
        assert len(mail.outbox) == 1 and mail.outbox[0].to == [pat.email]
        assert "pat.surveyor" in mail.outbox[0].body
    path = link_in(mail.outbox[0])
    page = client.get(path, follow=True)
    assert b"Choose your password" in page.content
    done = client.post(page.redirect_chain[-1][0], {"new_password1": NEW, "new_password2": NEW})
    assert done.status_code == 302
    pat.refresh_from_db()
    assert pat.check_password(NEW)
    assert "_auth_user_id" not in client.session  # choosing a password does not sign you in
    assert b"This link has expired" in client.get(path, follow=True).content  # the link works once


def test_same_answer_and_no_email_for_unknown_closed_or_addressless_accounts(client, pat):
    User = get_user_model()
    User.objects.create_user("no.email", password="correct-horse-9")
    User.objects.create_user("gone", email="gone@council.example", password="correct-horse-9", is_active=False)
    for identifier in ("nobody@council.example", "nobody", "no.email", "gone", "gone@council.example"):
        assert b"Check your email" in ask(client, identifier).content, identifier
    assert mail.outbox == []


def test_link_stops_working_after_the_time_limit(client, pat, settings):
    ask(client, "pat.surveyor")
    path = link_in(mail.outbox[0])
    settings.PHAEMA_PASSWORD_RESET_MINUTES = 0
    real_now = password_reset.reset_tokens._now

    class Later(password_reset.ResetTokenGenerator):
        def _now(self):
            from datetime import timedelta
            return real_now() + timedelta(minutes=5)

    token = path.rstrip("/").split("/")[-1]
    assert not Later().check_token(pat, token)
    settings.PHAEMA_PASSWORD_RESET_MINUTES = 60
    assert Later().check_token(pat, token)
    assert not Later().check_token(pat, "abc-def")


def test_first_password_links_and_reset_links_are_not_interchangeable(client, pat):
    from django.contrib.auth.tokens import default_token_generator

    assert not password_reset.reset_tokens.check_token(pat, default_token_generator.make_token(pat))
    assert not default_token_generator.check_token(pat, password_reset.reset_tokens.make_token(pat))


def test_requests_are_limited(client, pat):
    for _ in range(password_reset.EMAILS_PER_HOUR + 1):
        ask(client, "pat.surveyor")
    assert len(mail.outbox) == password_reset.EMAILS_PER_HOUR  # per account
    for _ in range(password_reset.REQUESTS_PER_HOUR):
        resp = ask(client, "pat.surveyor")
    assert b"Too many requests" in resp.content  # per connection


def test_shared_address_emails_each_account_its_own_link(client, pat):
    get_user_model().objects.create_user("pat.second", email="pat@council.example", password="correct-horse-9")
    ask(client, "pat@council.example")
    assert sorted(re.search(r"Your username: (\S+)", m.body).group(1) for m in mail.outbox) == ["pat.second", "pat.surveyor"]


def test_two_step_still_applies_after_a_reset(client, pat):
    from apps.core.models import TwoStepDevice

    TwoStepDevice.objects.create(user=pat, secret="JBSWY3DPEHPK3PXP")
    ask(client, "pat.surveyor")
    page = client.get(link_in(mail.outbox[0]), follow=True)
    client.post(page.redirect_chain[-1][0], {"new_password1": NEW, "new_password2": NEW})
    resp = client.post(reverse("login"), {"username": "pat.surveyor", "password": NEW})
    assert resp.status_code == 302 and resp.url == reverse("login-code")
    assert "_auth_user_id" not in client.session


def test_site_without_email_says_so(client, pat, settings):
    settings.EMAIL_BACKEND = password_reset.CONSOLE_BACKEND
    page = client.get(reverse("forgot-password"))
    assert b"not set up to send email" in page.content and b"Email me a link" not in page.content
    assert b"not set up to send email" in ask(client, "pat.surveyor").content


def test_demonstration_people_cannot_be_reset_on_a_test_site(client, settings):
    settings.PHAEMA_DEMO_SITE = True
    get_user_model().objects.create_user("demo.surveyor", email="demo@council.example", password="correct-horse-9")
    ask(client, "demo.surveyor")
    assert mail.outbox == []
