# SPDX-License-Identifier: AGPL-3.0-or-later
"""Limits on guessing passwords, and the address a request really came from.

Wrong passwords are counted for the account tried and for the connection they came from, over a rolling window.
Past the limit, sign-in is refused, even with the right password, until the window has passed. This covers the
sign-in page, the administration site and the API (which signs in with a password on every request), because
all of them check passwords through the same sign-in backend.

The counts are kept in the shared cache (a table in the database), so every web worker sees the same numbers.
"""
import hashlib
import time

from django.conf import settings
from django.core.cache import cache


def client_ip(request):
    """The address of the person making the request.

    The X-Forwarded-For header is only believed when PHAEMA runs behind the council's HTTPS proxy
    (BEHIND_HTTPS_PROXY), and then only the address the proxy itself added (the last one). Anything earlier in
    the header was sent by the browser and could be made up.
    """
    meta = getattr(request, "META", {}) or {}
    if getattr(settings, "PHAEMA_BEHIND_HTTPS_PROXY", False):
        forwarded = [part.strip() for part in meta.get("HTTP_X_FORWARDED_FOR", "").split(",") if part.strip()]
        if forwarded:
            return forwarded[-1]
    return meta.get("REMOTE_ADDR", "") or "unknown"


def _key(kind, value):
    return f"signin-fail:{kind}:" + hashlib.sha256(str(value).strip().lower().encode()).hexdigest()


def _recent(key):
    cutoff = time.time() - settings.PHAEMA_SIGNIN_WINDOW_SECONDS
    return [t for t in (cache.get(key) or []) if t > cutoff]


def _limits(username, request):
    out = []
    if username:
        out.append((_key("account", username), settings.PHAEMA_SIGNIN_MAX_PER_ACCOUNT))
    if request is not None:
        out.append((_key("ip", client_ip(request)), settings.PHAEMA_SIGNIN_MAX_PER_ADDRESS))
    return out


def blocked(username, request):
    """Whether sign-in for this account, or from this connection, is paused after too many wrong passwords."""
    return any(len(_recent(key)) >= limit for key, limit in _limits(username, request))


def record_failure(username, request):
    now = time.time()
    for key, _limit in _limits(username, request):
        cache.set(key, [*_recent(key), now][-200:], settings.PHAEMA_SIGNIN_WINDOW_SECONDS)


def clear(username):
    """A successful sign-in clears the account's count (not the connection's)."""
    if username:
        cache.delete(_key("account", username))


def minutes():
    return max(1, settings.PHAEMA_SIGNIN_WINDOW_SECONDS // 60)
