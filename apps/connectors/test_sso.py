# SPDX-License-Identifier: AGPL-3.0-or-later
"""Single sign-on: off by default, the sign-in itself, matching accounts, groups, passwords and two-step sign-in."""
import time
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from django.core import mail
from django.core.cache import cache
from django.urls import reverse

from apps.connectors import sso
from apps.connectors.models import SsoGroupMapping, SsoIdentity
from apps.core.models import AccessArea, AuditEntry, ModuleSettings
from apps.core.roles import ADMINISTRATORS, SURVEYORS, VIEWERS

ISSUER = "https://login.example.test/tenant/v2.0"
CLIENT = "phaema-client"
PASSWORD = "a-long-test-password"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class Provider:
    """A stand-in for the council's sign-in service."""

    def __init__(self):
        self.claims = {"sub": "abc-123", "email": "pat@council.example", "given_name": "Pat", "family_name": "Lee"}
        self.key = KEY
        self.token_requests = []
        self.nonce = None

    def fetch(self, url, data=None):
        if url.endswith("/.well-known/openid-configuration"):
            return {"issuer": ISSUER, "authorization_endpoint": ISSUER + "/authorize",
                    "token_endpoint": ISSUER + "/token", "jwks_uri": ISSUER + "/keys",
                    "id_token_signing_alg_values_supported": ["RS256"]}
        assert url == ISSUER + "/token"
        self.token_requests.append(data)
        now = int(time.time())
        claims = {"iss": ISSUER, "aud": CLIENT, "iat": now, "exp": now + 300, "nonce": self.nonce, **self.claims}
        return {"id_token": jwt.encode(claims, self.key, algorithm="RS256")}


@pytest.fixture
def provider(db, settings, monkeypatch):
    settings.PHAEMA_SSO_ISSUER = ISSUER
    settings.PHAEMA_SSO_CLIENT_ID = CLIENT
    settings.PHAEMA_SSO_CLIENT_SECRET = "secret"
    settings.PHAEMA_BASE_URL = "http://testserver"
    cache.clear()
    module = ModuleSettings.load()
    module.sso_enabled = True
    module.save()
    fake = Provider()
    monkeypatch.setattr(sso, "_fetch_json", fake.fetch)
    monkeypatch.setattr(sso, "_signing_key", lambda token: KEY.public_key())
    return fake


def sign_in(client, provider, next_url=""):
    """Go through the whole sign-in as a browser would. Returns the response to coming back from the service."""
    response = client.get(reverse("sso-login") + (f"?next={next_url}" if next_url else ""))
    assert response.status_code == 302 and response["Location"].startswith(ISSUER + "/authorize?")
    query = parse_qs(urlparse(response["Location"]).query)
    provider.nonce = query["nonce"][0]
    provider.sent = query
    return client.get(reverse("sso-callback"), {"code": "one-time-code", "state": query["state"][0]})


def messages_of(response):
    return " ".join(str(m) for m in response.context["messages"])


# Off unless both the installer and an administrator turn it on

def test_off_by_default(client, db):
    assert client.get(reverse("sso-login")).status_code == 404
    assert client.get(reverse("sso-callback")).status_code == 404
    assert b"Sign in with Microsoft" not in client.get(reverse("login")).content


def test_needs_the_administrators_switch_as_well(client, provider):
    module = ModuleSettings.load()
    module.sso_enabled = False
    module.save()
    assert client.get(reverse("sso-login")).status_code == 404
    assert b"Sign in with Microsoft" not in client.get(reverse("login")).content


def test_sign_in_page_offers_it_when_on(client, provider):
    page = client.get(reverse("login") + "?next=/leases/").content.decode()
    assert "Sign in with Microsoft" in page and "/login/sso/?next=/leases/" in page
    assert "Or sign in with a PHAEMA password" in page


# The sign-in itself

def test_existing_account_signs_in_and_is_linked(client, provider, make_user):
    pat = make_user("pat", SURVEYORS)
    pat.email = "Pat@Council.example"
    pat.save()
    response = sign_in(client, provider, "/leases/")
    assert response.status_code == 302 and response["Location"] == "/leases/"
    assert int(client.session["_auth_user_id"]) == pat.pk
    link = SsoIdentity.objects.get(user=pat)
    assert (link.issuer, link.subject) == (ISSUER, "abc-123") and link.last_sign_in
    assert AuditEntry.objects.filter(object_id=str(pat.pk), changes__has_key="sign-in").exists()
    # What was sent: PKCE, and the address the service must come back to.
    assert provider.sent["code_challenge_method"] == ["S256"] and provider.sent["response_type"] == ["code"]
    assert provider.sent["redirect_uri"] == ["http://testserver/login/sso/callback/"]
    sent = provider.token_requests[0]
    assert sso.challenge_for(sent["code_verifier"]) == provider.sent["code_challenge"][0]
    assert sent["client_secret"] == "secret" and sent["code"] == "one-time-code"


def test_linked_account_is_found_again_after_an_email_change(client, provider, make_user):
    pat = make_user("pat", SURVEYORS)
    SsoIdentity.objects.create(user=pat, issuer=ISSUER, subject="abc-123")
    provider.claims["email"] = "pat.newname@council.example"
    assert sign_in(client, provider).status_code == 302
    assert int(client.session["_auth_user_id"]) == pat.pk


def test_unsafe_next_address_is_ignored(client, provider, make_user):
    pat = make_user("pat", SURVEYORS)
    pat.email = "pat@council.example"
    pat.save()
    assert sign_in(client, provider, "https://evil.example/")["Location"] == reverse("dashboard")


def test_no_account_and_no_automatic_accounts(client, provider):
    response = sign_in(client, provider)
    assert response.status_code == 302 and response["Location"] == reverse("login")
    assert "_auth_user_id" not in client.session
    assert "There is no PHAEMA account for pat@council.example" in messages_of(client.get(reverse("login")))


def test_account_created_when_the_council_allows_it(client, provider):
    module = ModuleSettings.load()
    module.sso_create_accounts = True
    module.save()
    assert sign_in(client, provider).status_code == 302
    pat = SsoIdentity.objects.get(subject="abc-123").user
    assert (pat.username, pat.first_name, pat.last_name) == ("pat", "Pat", "Lee")
    assert not pat.has_usable_password() and not pat.groups.exists()
    assert client.get(reverse("dashboard")).status_code == 403  # no role yet, so they see nothing


def test_closed_account_cannot_sign_in(client, provider, make_user):
    pat = make_user("pat", SURVEYORS)
    SsoIdentity.objects.create(user=pat, issuer=ISSUER, subject="abc-123")
    pat.is_active = False
    pat.save()
    sign_in(client, provider)
    assert "_auth_user_id" not in client.session


def test_superuser_is_never_matched_by_email(client, provider, django_user_model):
    django_user_model.objects.create_superuser("root", "pat@council.example", PASSWORD)
    sign_in(client, provider)
    assert "_auth_user_id" not in client.session and not SsoIdentity.objects.exists()


def test_two_accounts_with_the_address_are_refused(client, provider, make_user):
    for name in ("pat", "pat2"):
        user = make_user(name, SURVEYORS)
        user.email = "pat@council.example"
        user.save()
    sign_in(client, provider)
    assert "_auth_user_id" not in client.session


def test_unverified_email_is_not_used(client, provider, make_user):
    pat = make_user("pat", SURVEYORS)
    pat.email = "pat@council.example"
    pat.save()
    provider.claims["email_verified"] = False
    sign_in(client, provider)
    assert "_auth_user_id" not in client.session


# Things that must be refused

def test_wrong_state_is_refused(client, provider, make_user):
    client.get(reverse("sso-login"))
    response = client.get(reverse("sso-callback"), {"code": "x", "state": "not-the-state"})
    assert response["Location"] == reverse("login") and not provider.token_requests
    assert "_auth_user_id" not in client.session


def test_callback_without_starting_is_refused(client, provider):
    response = client.get(reverse("sso-callback"), {"code": "x", "state": "anything"})
    assert response["Location"] == reverse("login") and not provider.token_requests


def test_token_signed_by_someone_else_is_refused(client, provider, make_user):
    pat = make_user("pat", SURVEYORS)
    pat.email = "pat@council.example"
    pat.save()
    provider.key = OTHER_KEY
    sign_in(client, provider)
    assert "_auth_user_id" not in client.session


@pytest.mark.parametrize("change", [{"aud": "another-app"}, {"iss": "https://elsewhere.example"},
                                    {"exp": 1000}, {"nonce": "replayed"}])
def test_token_for_another_app_service_time_or_sign_in_is_refused(client, provider, make_user, change):
    pat = make_user("pat", SURVEYORS)
    pat.email = "pat@council.example"
    pat.save()
    provider.claims.update(change)
    sign_in(client, provider)
    assert "_auth_user_id" not in client.session


def test_service_error_returns_to_sign_in(client, provider):
    client.get(reverse("sso-login"))
    state = client.session["sso_pending"]["state"]
    response = client.get(reverse("sso-callback"), {"error": "access_denied", "state": state})
    assert response["Location"] == reverse("login")
    assert "did not sign you in" in messages_of(client.get(reverse("login")))


def test_service_must_match_the_configured_address(provider, monkeypatch):
    monkeypatch.setattr(sso, "_fetch_json", lambda url, data=None: {"issuer": "https://elsewhere.example"})
    cache.clear()
    with pytest.raises(sso.SsoError):
        sso.discovery()


# Roles and access areas from groups

@pytest.fixture
def pat(make_user):
    user = make_user("pat", VIEWERS)
    user.email = "pat@council.example"
    user.save()
    return user


@pytest.mark.own_areas
def test_groups_set_roles_and_access_areas(client, provider, pat):
    finance = AccessArea.objects.create(code="fin-test", name="Finance test", modules=["ledger"])
    other = AccessArea.objects.create(code="other-test", name="Other test")
    pat.access_areas.add(other)
    SsoGroupMapping.objects.create(group="g-surveyors", role=SURVEYORS, access_area=finance)
    SsoGroupMapping.objects.create(group="g-admins", role=ADMINISTRATORS)
    provider.claims["groups"] = ["g-surveyors", "g-unrelated"]
    sign_in(client, provider)
    pat.refresh_from_db()
    # Surveyor comes from the group; Viewer was set by hand and no mapping mentions it, so it stays.
    assert set(pat.groups.values_list("name", flat=True)) == {SURVEYORS, VIEWERS}
    assert set(pat.access_areas.all()) == {finance, other} and pat.is_staff

    # Moved out of the group: the mapped role and area go at the next sign-in; the hand-set ones stay.
    client.logout()
    provider.claims["groups"] = ["g-unrelated"]
    sign_in(client, provider)
    pat.refresh_from_db()
    assert set(pat.groups.values_list("name", flat=True)) == {VIEWERS}
    assert set(pat.access_areas.all()) == {other} and not pat.is_staff
    assert AuditEntry.objects.filter(object_id=str(pat.pk), changes__has_key="role").count() == 2


def test_app_roles_count_as_groups(client, provider, pat):
    SsoGroupMapping.objects.create(group="Phaema.Admin", role=ADMINISTRATORS)
    provider.claims["roles"] = ["Phaema.Admin"]
    sign_in(client, provider)
    assert pat.groups.filter(name=ADMINISTRATORS).exists()


def test_no_mappings_leaves_roles_alone(client, provider, pat):
    provider.claims["groups"] = ["anything"]
    sign_in(client, provider)
    assert set(pat.groups.values_list("name", flat=True)) == {VIEWERS}


def test_too_many_groups_to_list_leaves_roles_alone(client, provider, pat):
    SsoGroupMapping.objects.create(group="g-viewers", role=VIEWERS)
    provider.claims["_claim_names"] = {"groups": "src1"}
    sign_in(client, provider)
    assert int(client.session["_auth_user_id"]) == pat.pk
    assert pat.groups.filter(name=VIEWERS).exists()


# PHAEMA passwords alongside

def link(user):
    return SsoIdentity.objects.create(user=user, issuer=ISSUER, subject=f"sub-{user.pk}")


def password_works(client, user):
    client.logout()
    return client.login(username=user.username, password=PASSWORD)


def test_password_rule(client, provider, make_user, django_user_model):
    staff, consultant, admin = make_user("staff", SURVEYORS), make_user("valuer", SURVEYORS), make_user("boss", ADMINISTRATORS)
    root = django_user_model.objects.create_superuser("root", "root@council.example", PASSWORD)
    for user in (staff, consultant, admin):
        user.set_password(PASSWORD)
        user.save()
    link(staff)
    link(admin)
    assert not password_works(client, staff)  # has a council account, so must use it
    assert password_works(client, consultant)  # outside consultant: PHAEMA sign-in
    assert password_works(client, admin) and password_works(client, root)  # the fallback

    module = ModuleSettings.load()
    module.sso_passwords = ModuleSettings.SsoPasswords.EVERYONE
    module.save()
    assert password_works(client, staff)

    module.sso_passwords = ModuleSettings.SsoPasswords.UNLINKED
    module.sso_enabled = False
    module.save()
    assert password_works(client, staff)  # single sign-on switched off: passwords work again


def test_no_reset_email_for_people_who_must_use_the_council_sign_in(client, provider, make_user, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    staff, consultant = make_user("staff", SURVEYORS), make_user("valuer", SURVEYORS)
    staff.email, consultant.email = "staff@council.example", "valuer@firm.example"
    staff.save()
    consultant.save()
    link(staff)
    client.post(reverse("forgot-password"), {"identifier": "staff@council.example"})
    assert not mail.outbox
    client.post(reverse("forgot-password"), {"identifier": "valuer@firm.example"})
    assert len(mail.outbox) == 1


# Two-step sign-in

@pytest.mark.two_step
def test_council_sign_in_is_not_asked_for_phaema_two_step(client, provider, make_user):
    module = ModuleSettings.load()
    module.two_step_required = ModuleSettings.TwoStep.EVERYONE
    module.save()
    pat = make_user("pat", SURVEYORS)
    pat.email = "pat@council.example"
    pat.set_password(PASSWORD)
    pat.save()
    sign_in(client, provider)
    assert client.get(reverse("dashboard")).status_code == 200  # the council's own sign-in rules apply instead

    # The same person on a PHAEMA password (where that is allowed) must still set up two-step sign-in.
    module.sso_passwords = ModuleSettings.SsoPasswords.EVERYONE
    module.save()
    assert password_works(client, pat)
    assert client.get(reverse("dashboard"))["Location"] == reverse("two-step")


# Administration

def test_administrator_can_manage_mappings_and_unlink(client, provider, make_user):
    admin = make_user("boss", ADMINISTRATORS)
    pat = make_user("pat", SURVEYORS)
    link(pat)
    client.force_login(admin)
    assert client.get("/admin/connectors/ssogroupmapping/add/").status_code == 200
    assert "Council sign-in" in client.get(f"/admin/auth/user/{pat.pk}/change/").content.decode()
    assert client.get("/admin/core/modulesettings/1/change/").status_code == 200
