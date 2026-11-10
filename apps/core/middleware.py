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


class TwoStepRequiredMiddleware:
    """People the council requires to use two-step sign-in must set it up before they can do anything else."""

    OPEN_PREFIXES = ("/account/two-step/", "/login/", "/logout/", "/health/", "/static/", "/text-size/", "/theme/",
                     "/style/", "/help/", "/open-data/", "/no-access/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (user is not None and user.is_authenticated and not request.path.startswith(self.OPEN_PREFIXES)):
            from django.shortcuts import redirect

            from apps.connectors import sso

            from . import two_step

            # People signed in with the council's own account have met the council's own sign-in rules.
            if (not sso.signed_in_with_sso(request) and two_step.is_required(user)
                    and not two_step.has_two_step(user)):
                if request.path.startswith("/api/"):
                    from django.http import JsonResponse

                    return JsonResponse({"detail": "Set up two-step sign-in before using the API."}, status=403)
                return redirect("two-step")
        return self.get_response(request)
