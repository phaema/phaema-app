# SPDX-License-Identifier: AGPL-3.0-or-later
"""Forgotten password: email a link that lets someone choose a new password.

The page gives the same answer whether or not an account was found, so it cannot be used to discover who has
a sign-in. The link works once and for a short time. Choosing a new password does not sign the person in, so
two-step sign-in still applies afterwards.
"""
import logging

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.cache import cache
from django.core.mail import send_mail
from django.shortcuts import render
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import base36_to_int, urlsafe_base64_encode
from django.utils.translation import gettext_lazy as _
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect

log = logging.getLogger(__name__)
REQUESTS_PER_HOUR = 5  # from one connection
EMAILS_PER_HOUR = 3  # to one account
CONSOLE_BACKEND = "django.core.mail.backends.console.EmailBackend"


class ResetTokenGenerator(PasswordResetTokenGenerator):
    """Reset links last minutes, not the days allowed for a new person's first "choose your password" link."""

    key_salt = "apps.core.password_reset.ResetTokenGenerator"

    def check_token(self, user, token):
        if not super().check_token(user, token):
            return False
        try:
            made = base36_to_int(token.split("-")[0])
        except ValueError:
            return False
        return self._num_seconds(self._now()) - made <= settings.PHAEMA_PASSWORD_RESET_MINUTES * 60


reset_tokens = ResetTokenGenerator()


class ForgotPasswordForm(forms.Form):
    identifier = forms.CharField(label=_("Email address or username"), max_length=254, strip=True)


def email_ready():
    """False when the site has no email service: reset emails would only be written to the server log."""
    return settings.EMAIL_BACKEND != CONSOLE_BACKEND


def accounts_for(identifier):
    """The active accounts a reset email may go to: the one with that username, or every one with that address."""
    User = get_user_model()
    users = User._default_manager.filter(is_active=True).exclude(email="")
    if settings.PHAEMA_DEMO_SITE:
        users = users.exclude(username__startswith="demo.")  # the shared demonstration people
    found = list(users.filter(username=identifier)[:1])
    if not found and "@" in identifier:
        found = list(users.filter(email__iexact=identifier)[:5])
    from apps.connectors import sso

    return [user for user in found if sso.password_allowed(user)]  # no use to people who must use the council sign-in


def reset_link(user):
    path = reverse("reset-password", args=[urlsafe_base64_encode(force_bytes(user.pk)), reset_tokens.make_token(user)])
    return settings.PHAEMA_BASE_URL.rstrip("/") + path


def send_reset(user):
    """Email one account its link. Returns True if an email was sent."""
    key = f"password-reset-user:{user.pk}"
    sent = cache.get(key, 0)
    if sent >= EMAILS_PER_HOUR:
        return False
    cache.set(key, sent + 1, 3600)
    minutes = settings.PHAEMA_PASSWORD_RESET_MINUTES
    body = (f"Hello {user.first_name or user.username},\n\n"
            f"Someone asked to reset the password for your PHAEMA sign-in at {settings.PHAEMA_BASE_URL.rstrip('/')}.\n\n"
            f"Your username: {user.username}\n\n"
            f"Choose a new password here (the link works once, within {minutes} minutes):\n{reset_link(user)}\n\n"
            f"If you did not ask for this, ignore this email: your password has not been changed.\n\n"
            f"{settings.PHAEMA_ORGANISATION_NAME}\n")
    try:
        send_mail("Reset your PHAEMA password", body, settings.DEFAULT_FROM_EMAIL, [user.email])
        return True
    except Exception:
        log.exception("Could not send a password reset email to user %s", user.pk)
        return False


def _client_ip(request):
    return request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get("REMOTE_ADDR", "")


@never_cache
@csrf_protect
def forgot_password(request):
    ready = email_ready()
    form = ForgotPasswordForm(request.POST or None)
    if ready and request.method == "POST" and form.is_valid():
        key = f"password-reset-ip:{_client_ip(request)}"
        count = cache.get(key, 0)
        if count >= REQUESTS_PER_HOUR:
            form.add_error(None, _("Too many requests from this connection. Please try again in an hour."))
        else:
            cache.set(key, count + 1, 3600)
            for user in accounts_for(form.cleaned_data["identifier"]):
                send_reset(user)
            return render(request, "registration/forgot_password_sent.html",
                          {"minutes": settings.PHAEMA_PASSWORD_RESET_MINUTES})
    return render(request, "registration/forgot_password.html", {"form": form, "email_ready": ready})
