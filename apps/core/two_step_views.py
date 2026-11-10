# SPDX-License-Identifier: AGPL-3.0-or-later
"""Signing in with two-step sign-in, and setting it up."""
import time

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters

from . import two_step

PENDING = "two_step_pending"
SETUP_SECRET = "two_step_setup_secret"
SHOW_CODES = "two_step_show_codes"
MAX_ATTEMPTS = 5
PENDING_SECONDS = 5 * 60


class PhaemaLoginView(LoginView):
    """The password step. People with two-step sign-in go on to the code step before they are signed in."""

    def get_context_data(self, **kwargs):
        from apps.connectors import sso

        context = super().get_context_data(**kwargs)
        if sso.enabled():
            context["sso_name"] = sso.name()
        return context

    def form_valid(self, form):
        user = form.get_user()
        if not two_step.has_two_step(user):
            return super().form_valid(form)
        self.request.session.cycle_key()
        self.request.session[PENDING] = {
            "user": user.pk, "backend": user.backend, "next": self.get_redirect_url(), "started": time.time(),
            "attempts": 0,
        }
        return redirect("login-code")


def _safe_next(request, url):
    if url and url_has_allowed_host_and_scheme(url, allowed_hosts={request.get_host()},
                                               require_https=request.is_secure()):
        return url
    return reverse("dashboard")


@never_cache
@csrf_protect
@sensitive_post_parameters("code")
def login_code(request):
    pending = request.session.get(PENDING)
    if not pending or time.time() - pending.get("started", 0) > PENDING_SECONDS:
        request.session.pop(PENDING, None)
        if pending:
            messages.info(request, "Sign-in took too long. Sign in with your password again.")
        return redirect("login")
    user = get_user_model().objects.filter(pk=pending["user"], is_active=True).first()
    if user is None:
        request.session.pop(PENDING, None)
        return redirect("login")
    error = ""
    if request.method == "POST":
        how = two_step.verify(user, request.POST.get("code", ""))
        if how:
            request.session.pop(PENDING, None)
            user.backend = pending["backend"]
            login(request, user, backend=pending["backend"])
            if how == "recovery":
                left = two_step.recovery_codes_left(user)
                messages.warning(request, f"You signed in with a recovery code. You have {left} left. "
                                          "Make new ones under Two-step sign-in if you are running low.")
            return redirect(_safe_next(request, pending.get("next")))
        pending["attempts"] = pending.get("attempts", 0) + 1
        if pending["attempts"] >= MAX_ATTEMPTS:
            request.session.pop(PENDING, None)
            messages.error(request, "Too many wrong codes. Sign in with your password again.")
            return redirect("login")
        request.session[PENDING] = pending
        error = "Enter the 6-digit code from your authenticator app, or one of your recovery codes."
    return render(request, "registration/login_code.html", {"error": error})


@login_required
@never_cache
@sensitive_post_parameters("code", "password")
def security(request):
    """A person's own two-step sign-in: set it up, make new recovery codes, or turn it off."""
    user = request.user
    has = two_step.has_two_step(user)
    required = two_step.is_required(user)
    errors = []
    action = request.POST.get("action", "") if request.method == "POST" else ""

    if action == "start" and not has:
        request.session[SETUP_SECRET] = two_step.new_secret()
        return redirect("two-step")
    if action == "confirm" and not has:
        secret = request.session.get(SETUP_SECRET)
        codes = two_step.turn_on(user, secret, request.POST.get("code", "")) if secret else None
        if codes:
            request.session.pop(SETUP_SECRET, None)
            request.session[SHOW_CODES] = codes
            return redirect("two-step")
        errors.append(("code", "That code did not match. Enter the 6-digit code your app shows now."))
    if action == "cancel":
        request.session.pop(SETUP_SECRET, None)
        return redirect("two-step")
    if action in ("new-codes", "turn-off") and has:
        if not user.check_password(request.POST.get("password", "")):
            errors.append(("password", "Enter your password."))
        elif two_step.verify(user, request.POST.get("code", "")) is None:
            errors.append(("code", "Enter a current code from your authenticator app."))
        elif action == "new-codes":
            request.session[SHOW_CODES] = two_step.new_recovery_codes(user)
            return redirect("two-step")
        elif required:
            errors.append(("code", "Your council requires two-step sign-in for you, so it cannot be turned off. "
                                   "To move to a new phone, ask an administrator to reset it."))
        else:
            two_step.turn_off(user)
            messages.success(request, "Two-step sign-in is turned off.")
            return redirect("two-step")

    context = {"has": two_step.has_two_step(user), "required": required, "errors": errors,
               "codes": request.session.pop(SHOW_CODES, None)}
    secret = request.session.get(SETUP_SECRET)
    if secret and not context["has"]:
        context.update(secret=two_step.spaced(secret), qr=two_step.qr_svg(two_step.setup_uri(secret, user.username)))
    if context["has"]:
        context["codes_left"] = two_step.recovery_codes_left(user)
    return render(request, "core/two_step.html", context)


def admin_login_redirect(request):
    """The admin site signs in through PHAEMA's own sign-in, so two-step sign-in cannot be bypassed."""
    from urllib.parse import urlencode

    target = reverse("login")
    nxt = request.GET.get("next", reverse("admin:index"))
    return redirect(f"{target}?{urlencode({'next': nxt})}")
