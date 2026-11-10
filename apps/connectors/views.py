# SPDX-License-Identifier: AGPL-3.0-or-later
"""Signing in with the council's own account (single sign-on)."""
import hmac
import logging
import secrets
import time

from django.contrib import messages
from django.contrib.auth import login
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache

from . import sso

log = logging.getLogger(__name__)

PENDING = "sso_pending"
PENDING_SECONDS = 10 * 60


def _safe_next(request, url):
    if url and url_has_allowed_host_and_scheme(url, allowed_hosts={request.get_host()},
                                               require_https=request.is_secure()):
        return url
    return reverse("dashboard")


def _back_to_sign_in(request, message):
    request.session.pop(PENDING, None)
    messages.error(request, message)
    return redirect("login")


@never_cache
def sso_login(request):
    """Send the person to the council's sign-in service."""
    if not sso.enabled():
        raise Http404
    pending = {"state": secrets.token_urlsafe(32), "nonce": secrets.token_urlsafe(32),
               "verifier": sso.new_verifier(), "next": request.GET.get("next", ""), "started": time.time()}
    try:
        url = sso.authorization_url(pending["state"], pending["nonce"], pending["verifier"])
    except sso.SsoError as err:
        return _back_to_sign_in(request, str(err))
    request.session[PENDING] = pending
    return redirect(url)


@never_cache
def sso_callback(request):
    """The person comes back from the sign-in service with a one-time code."""
    if not sso.enabled():
        raise Http404
    pending = request.session.pop(PENDING, None)
    if not pending or time.time() - pending.get("started", 0) > PENDING_SECONDS:
        return _back_to_sign_in(request, "Sign-in took too long or was started somewhere else. Please try again.")
    if not hmac.compare_digest(request.GET.get("state", ""), pending["state"]):
        return _back_to_sign_in(request, "The sign-in did not match the one you started. Please try again.")
    if request.GET.get("error"):
        log.warning("Sign-in service returned an error: %s %s", request.GET.get("error"),
                    request.GET.get("error_description", "")[:300])
        return _back_to_sign_in(request, f"{sso.name()} did not sign you in. Please try again, or ask your "
                                         "PHAEMA administrator.")
    code = request.GET.get("code", "")
    if not code:
        return _back_to_sign_in(request, "The sign-in service did not confirm who you are. Please try again.")
    try:
        claims = sso.read_id_token(sso.exchange(code, pending["verifier"]), pending["nonce"])
        user = sso.find_user(claims)
        sso.sync_groups(user, claims)
    except sso.SsoError as err:
        return _back_to_sign_in(request, str(err))
    login(request, user, backend=sso.BACKEND)
    return redirect(_safe_next(request, pending.get("next")))
