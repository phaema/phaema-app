# SPDX-License-Identifier: AGPL-3.0-or-later
"""Single sign-on with the council's own accounts, using OpenID Connect.

Works with Microsoft Entra ID (Microsoft 365), Keycloak and any other service that follows the standard. PHAEMA
uses the authorisation code flow with PKCE, checks the signature, issuer, audience, expiry and nonce of the ID
token, and reads nothing but the person's name, email address and groups.

The installer puts the service's address, client ID and secret in the server's settings file; an administrator
then turns it on in Module settings. With either missing, PHAEMA behaves exactly as it does without this module.
"""
import base64
import hashlib
import hmac
import json
import logging
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

log = logging.getLogger(__name__)

BACKEND = "apps.connectors.sso.SsoBackend"
SAFE_ALGORITHMS = {"RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512"}
TIMEOUT = 10


class SsoError(Exception):
    """A sign-in that cannot go ahead. The message is shown to the person, so it must be safe to show."""


class SsoBackend(ModelBackend):
    """Marks a session as signed in through the council's sign-in service. It never checks a password."""

    def authenticate(self, request, **kwargs):
        return None


# Is it on?

def configured():
    return bool(settings.PHAEMA_SSO_ISSUER and settings.PHAEMA_SSO_CLIENT_ID and settings.PHAEMA_SSO_CLIENT_SECRET)


def enabled():
    from apps.core.models import ModuleSettings

    return configured() and ModuleSettings.load().sso_enabled


def name():
    return settings.PHAEMA_SSO_NAME or "your council account"


def signed_in_with_sso(request):
    from django.contrib.auth import BACKEND_SESSION_KEY

    return request.session.get(BACKEND_SESSION_KEY) == BACKEND


def password_allowed(user):
    """Whether this person may still sign in with a PHAEMA password."""
    from apps.core.models import ModuleSettings
    from apps.core.roles import is_administrator

    from .models import SsoIdentity

    if not configured():
        return True
    module = ModuleSettings.load()
    if not module.sso_enabled or module.sso_passwords == ModuleSettings.SsoPasswords.EVERYONE:
        return True
    if user.is_superuser or is_administrator(user):
        return True  # the fallback if the sign-in service is unavailable
    return not SsoIdentity.objects.filter(user=user).exists()


# Talking to the sign-in service

def _fetch_json(url, data=None):
    """GET, or POST a form when data is given. Only https addresses (http is allowed for a local test service)."""
    if not url.startswith("https://") and not (settings.DEBUG and url.startswith("http://")):
        raise SsoError("The sign-in service address must start with https://.")
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    request = urllib.request.Request(url, data=body, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310 (scheme checked above)
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", "replace")[:500]
        log.warning("Sign-in service refused %s: %s %s", url, err.code, detail)
        raise SsoError("The sign-in service refused the request. Ask your PHAEMA administrator to check the "
                       "single sign-on settings.") from err
    except (urllib.error.URLError, TimeoutError, ValueError) as err:
        log.warning("Could not reach the sign-in service at %s: %s", url, err)
        raise SsoError("The sign-in service could not be reached. Please try again in a few minutes.") from err


def discovery():
    """The service's published settings (its sign-in, token and key addresses). Kept for an hour."""
    issuer = settings.PHAEMA_SSO_ISSUER.rstrip("/")
    key = "sso-discovery:" + hashlib.sha256(issuer.encode()).hexdigest()
    found = cache.get(key)
    if found is None:
        found = _fetch_json(issuer + "/.well-known/openid-configuration")
        if str(found.get("issuer", "")).rstrip("/") != issuer:
            raise SsoError("The sign-in service does not match the address in the single sign-on settings.")
        for needed in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
            if not found.get(needed):
                raise SsoError("The sign-in service did not publish the settings PHAEMA needs.")
        cache.set(key, found, 3600)
    return found


def redirect_uri():
    return settings.PHAEMA_BASE_URL.rstrip("/") + reverse("sso-callback")


def new_verifier():
    return secrets.token_urlsafe(48)


def challenge_for(verifier):
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")


def authorization_url(state, nonce, verifier):
    query = {
        "client_id": settings.PHAEMA_SSO_CLIENT_ID, "response_type": "code", "scope": "openid profile email",
        "redirect_uri": redirect_uri(), "state": state, "nonce": nonce,
        "code_challenge": challenge_for(verifier), "code_challenge_method": "S256",
    }
    endpoint = discovery()["authorization_endpoint"]
    return endpoint + ("&" if "?" in endpoint else "?") + urllib.parse.urlencode(query)


def exchange(code, verifier):
    """Swap the one-time code for the person's ID token."""
    reply = _fetch_json(discovery()["token_endpoint"], {
        "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri(),
        "client_id": settings.PHAEMA_SSO_CLIENT_ID, "client_secret": settings.PHAEMA_SSO_CLIENT_SECRET,
        "code_verifier": verifier,
    })
    token = reply.get("id_token")
    if not token:
        raise SsoError("The sign-in service did not confirm who you are. Please try again.")
    return token


def _signing_key(token):
    import jwt

    return jwt.PyJWKClient(discovery()["jwks_uri"], cache_keys=True, timeout=TIMEOUT).get_signing_key_from_jwt(token).key


def read_id_token(token, nonce):
    """Check the ID token and return what it says about the person."""
    import jwt

    found = discovery()
    algorithms = sorted(SAFE_ALGORITHMS & set(found.get("id_token_signing_alg_values_supported") or ["RS256"]))
    try:
        claims = jwt.decode(
            token, _signing_key(token), algorithms=algorithms or ["RS256"],
            audience=settings.PHAEMA_SSO_CLIENT_ID, issuer=found["issuer"], leeway=60,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]})
    except jwt.PyJWTError as err:
        log.warning("ID token refused: %s", err)
        raise SsoError("The sign-in service's answer could not be checked. Please try again.") from err
    if not nonce or not hmac.compare_digest(str(claims.get("nonce", "")), nonce):
        raise SsoError("The sign-in did not match the one you started. Please try again.")
    return claims


# Matching the person to a PHAEMA account

def email_of(claims):
    if claims.get("email_verified") is False:
        return ""
    for key in ("email", "preferred_username", "upn"):
        value = str(claims.get(key) or "").strip()
        if "@" in value and " " not in value:
            return value
    return ""


def _new_username(email):
    User = get_user_model()
    base = re.sub(r"[^a-z0-9.]+", ".", email.split("@")[0].lower()).strip(".")[:30] or "user"
    username, n = base, 1
    while User._default_manager.filter(username=username).exists():
        n += 1
        username = f"{base}{n}"
    return username


@transaction.atomic
def find_user(claims):
    """The PHAEMA account for this person, linking or creating it where the council's settings allow."""
    from apps.core import audit
    from apps.core.models import ModuleSettings

    from .models import SsoIdentity

    User = get_user_model()
    issuer, subject, email = str(claims["iss"]), str(claims["sub"]), email_of(claims)
    link = SsoIdentity.objects.select_related("user").filter(issuer=issuer, subject=subject).first()
    if link is None:
        if not email:
            raise SsoError("The sign-in service did not give PHAEMA your email address, so your account could "
                           "not be found. Ask your PHAEMA administrator for help.")
        matches = list(User._default_manager.filter(email__iexact=email, is_active=True, is_superuser=False,
                                                    sso_identity__isnull=True)[:2])
        if len(matches) > 1:
            raise SsoError(f"More than one PHAEMA account has the email address {email}. Ask your PHAEMA "
                           "administrator to correct this.")
        if matches:
            user = matches[0]
        elif User._default_manager.filter(email__iexact=email).exists():
            raise SsoError(f"The PHAEMA account for {email} cannot be used with {name()} sign-in. Sign in with "
                           "your PHAEMA password, or ask your PHAEMA administrator.")
        elif ModuleSettings.load().sso_create_accounts:
            user = User(username=_new_username(email), email=email)
            user.set_unusable_password()
            user.save()
            audit._record(user, "create", {"sign-in": [None, f"created at first {name()} sign-in"]})
        else:
            raise SsoError(f"There is no PHAEMA account for {email}. Ask your PHAEMA administrator to add you.")
        link = SsoIdentity.objects.create(user=user, issuer=issuer, subject=subject, email=email)
        audit._record(user, "update", {"sign-in": [None, f"linked to {name()} sign-in ({email})"]})
    user = link.user
    if not user.is_active:
        raise SsoError("Your PHAEMA account is closed. Ask your PHAEMA administrator.")
    changed = []
    for field, value in (("first_name", claims.get("given_name")), ("last_name", claims.get("family_name"))):
        if value and not getattr(user, field):
            setattr(user, field, str(value)[:150])
            changed.append(field)
    if changed:
        user.save(update_fields=changed)
    link.last_sign_in = timezone.now()
    if email:
        link.email = email
    link.save(update_fields=["last_sign_in", "email"])
    return user


def groups_of(claims):
    """The person's groups and app roles, or None when the service could not list them (too many to send)."""
    names = claims.get("_claim_names")
    if claims.get("hasgroups") or (isinstance(names, dict) and "groups" in names):
        return None
    found = set()
    for key in ("groups", "roles"):
        value = claims.get(key) or []
        found.update(str(v) for v in ([value] if isinstance(value, str) else value))
    return found


def sync_groups(user, claims):
    """Set the person's roles and access areas from their groups, for the roles and areas that are mapped.

    Roles and areas that no mapping mentions are left as an administrator set them. With no mappings at all,
    nothing changes. Returns False if the groups could not be read, when nothing is changed either."""
    from apps.core import audit
    from apps.core.roles import sync_staff_status

    from .models import SsoGroupMapping

    mappings = list(SsoGroupMapping.objects.select_related("access_area"))
    if not mappings:
        return True
    theirs = groups_of(claims)
    if theirs is None:
        log.warning("User %s is in too many groups for the sign-in service to list; roles left unchanged.", user.pk)
        return False
    mapped_roles = {m.role for m in mappings if m.role}
    wanted_roles = {m.role for m in mappings if m.role and m.group in theirs}
    has_roles = set(user.groups.filter(name__in=mapped_roles).values_list("name", flat=True))
    for role in wanted_roles - has_roles:
        user.groups.add(Group.objects.get(name=role))
    for role in has_roles - wanted_roles:
        user.groups.remove(Group.objects.get(name=role))
    if wanted_roles != has_roles:
        audit._record(user, "update", {"role": [", ".join(sorted(has_roles)) or None,
                                                ", ".join(sorted(wanted_roles)) or "none (from sign-in groups)"]})
    mapped_areas = {m.access_area for m in mappings if m.access_area}
    wanted_areas = {m.access_area for m in mappings if m.access_area and m.group in theirs}
    has_areas = set(user.access_areas.filter(pk__in=[a.pk for a in mapped_areas]))
    if wanted_areas - has_areas:
        user.access_areas.add(*(wanted_areas - has_areas))
    if has_areas - wanted_areas:
        user.access_areas.remove(*(has_areas - wanted_areas))
    sync_staff_status(user)
    return True
