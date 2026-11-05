# SPDX-License-Identifier: AGPL-3.0-or-later
"""Makes the signed-in user available to the audit trail."""
from contextvars import ContextVar

_current_user = ContextVar("phaema_current_user", default=None)


def get_current_user():
    user = _current_user.get()
    if user is not None and getattr(user, "is_authenticated", False):
        return user
    return None


class CurrentUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = _current_user.set(getattr(request, "user", None))
        try:
            return self.get_response(request)
        finally:
            _current_user.reset(token)


class RoleRequiredMiddleware:
    """Signed-in users must have a PHAEMA role (or be a superuser) to see anything."""

    OPEN_PREFIXES = ("/login/", "/logout/", "/health/", "/static/", "/text-size/", "/theme/", "/no-access/", "/help/",
                     "/open-data/", "/request-account/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.shortcuts import render

        from .roles import has_role

        user = getattr(request, "user", None)
        if (user is not None and user.is_authenticated and not has_role(user)
                and not request.path.startswith(self.OPEN_PREFIXES)):
            return render(request, "core/no_access.html", status=403)
        return self.get_response(request)
