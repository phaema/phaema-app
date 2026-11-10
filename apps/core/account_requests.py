# SPDX-License-Identifier: AGPL-3.0-or-later
"""The public "request a test account" form on a test site."""
import logging

from django import forms
from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail
from django.http import Http404
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _

from apps.leases.forms import GovukMixin

from .models import AccountRequest

log = logging.getLogger(__name__)
LIMIT_PER_HOUR = 5


class AccountRequestForm(GovukMixin, forms.ModelForm):
    # Left empty by people; bots that fill every box are quietly ignored.
    website = forms.CharField(required=False, label=_("Leave this empty"))

    class Meta:
        model = AccountRequest
        fields = ["name", "email", "organisation", "reason"]
        labels = {"name": _("Your name"), "reason": _("What would you like to try?")}
        help_texts = {"organisation": _("For example, the council you work for."),
                      "reason": _("For example, leases and rent reviews, or the projects module.")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].widget.attrs.update({"class": "govuk-input govuk-!-width-two-thirds", "autocomplete": "name"})
        self.fields["email"].widget.attrs.update({"class": "govuk-input govuk-!-width-two-thirds",
                                                  "autocomplete": "email", "spellcheck": "false"})
        self.fields["organisation"].widget.attrs.update({"class": "govuk-input govuk-!-width-two-thirds",
                                                         "autocomplete": "organization"})
        self.fields["reason"].widget.attrs["rows"] = 4
        self.fields["website"].widget.attrs.update({"tabindex": "-1", "autocomplete": "off"})


def _client_ip(request):
    return request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get("REMOTE_ADDR", "")


def request_account(request):
    if not settings.PHAEMA_DEMO_SITE:
        raise Http404
    form = AccountRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if form.cleaned_data.get("website"):
            return render(request, "core/account_request_sent.html")  # a bot: say nothing, keep nothing
        key = f"account-request:{_client_ip(request)}"
        count = cache.get(key, 0)
        if count >= LIMIT_PER_HOUR:
            form.add_error(None, _("Too many requests from this connection. Please try again in an hour."))
        else:
            cache.set(key, count + 1, 3600)
            req = form.save()
            _notify(req)
            return render(request, "core/account_request_sent.html", {"req": req})
    return render(request, "core/account_request.html", {"form": form})


def _notify(req):
    to = settings.PHAEMA_ACCOUNT_REQUEST_EMAIL
    if not to:
        return
    body = (f"Someone has asked for a sign-in to the PHAEMA test site at {settings.PHAEMA_BASE_URL}.\n\n"
            f"Name: {req.name}\nEmail: {req.email}\nOrganisation: {req.organisation or '-'}\n"
            f"Would like to try: {req.reason or '-'}\n\n"
            f"To approve it, open Manage data, Test account requests, tick the request and choose "
            f"\"Approve as surveyor\" (or administrator). PHAEMA creates the sign-in and emails them a link to "
            f"choose their password.\n")
    try:
        send_mail(f"PHAEMA test account request: {req.name}", body, settings.DEFAULT_FROM_EMAIL, [to])
    except Exception:  # the request is kept in Manage data even if email is not working
        log.exception("Could not email the test account request")


# Approving a request: create the sign-in and email the person a link to choose their password

def _username_for(email):
    import re

    from django.contrib.auth import get_user_model

    base = re.sub(r"[^a-z0-9.]+", ".", email.split("@")[0].lower()).strip(".")[:30] or "tester"
    if base.startswith("demo."):
        base = "t." + base  # "demo." usernames are the demonstration people, recreated at every reset
    username, n = base, 1
    while get_user_model().objects.filter(username=username).exists():
        n += 1
        username = f"{base}{n}"
    return username


def set_password_link(user):
    from django.contrib.auth.tokens import default_token_generator
    from django.urls import reverse
    from django.utils.encoding import force_bytes
    from django.utils.http import urlsafe_base64_encode

    path = reverse("set-password", args=[urlsafe_base64_encode(force_bytes(user.pk)),
                                         default_token_generator.make_token(user)])
    return settings.PHAEMA_BASE_URL.rstrip("/") + path


def approve(req, role):
    """Create (or find) the person's sign-in with the given role and all access areas, email them a link to choose
    a password, and mark the request done. Returns (user, created, link, emailed)."""
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Group

    from .models import AccessArea

    User = get_user_model()
    user = User.objects.filter(email__iexact=req.email).exclude(username__startswith="demo.").first()
    created = user is None
    if created:
        first, _, last = req.name.strip().partition(" ")
        user = User(username=_username_for(req.email), email=req.email, first_name=first[:150], last_name=last[:150])
        user.set_unusable_password()
        user.save()
    user.is_active = True
    user.save(update_fields=["is_active"])
    user.groups.set(Group.objects.filter(name=role))
    user.access_areas.set(AccessArea.objects.all())
    link = set_password_link(user)
    emailed = _send_welcome(req, user, link, role)
    req.done = True
    req.save(update_fields=["done"])
    return user, created, link, emailed


def _send_welcome(req, user, link, role):
    days = max(1, settings.PASSWORD_RESET_TIMEOUT // 86400)
    body = (f"Hello {req.name.split()[0] if req.name.strip() else ''},\n\n"
            f"Your sign-in to the PHAEMA test site is ready.\n\n"
            f"Your username: {user.username}\n"
            f"Your role: {role[:-1] if role.endswith('s') else role}\n\n"
            f"Choose your password here (the link works once, within {days} days):\n{link}\n\n"
            f"Then sign in at {settings.PHAEMA_BASE_URL.rstrip('/')}/login/\n\n"
            f"The test site holds fictional data for two demonstration districts. Everything you enter is reset "
            f"every {getattr(settings, 'PHAEMA_DEMO_RESET_HOURS', 48)} hours, so please do not enter real or personal "
            f"information. Your sign-in is kept when the data is reset.\n\n"
            f"To find your way around, try the training courses and the user manual at https://phaema.co.uk, "
            f"or the Help link inside PHAEMA. Questions and feedback are very welcome: just reply to this email.\n\n"
            f"PHAEMA project\n")
    reply_to = [settings.PHAEMA_ACCOUNT_REQUEST_EMAIL] if settings.PHAEMA_ACCOUNT_REQUEST_EMAIL else None
    try:
        from django.core.mail import EmailMessage

        EmailMessage("Your PHAEMA test site sign-in", body, settings.DEFAULT_FROM_EMAIL, [user.email],
                     reply_to=reply_to).send()
        return True
    except Exception:
        log.exception("Could not email the new test account to %s", user.email)
        return False
