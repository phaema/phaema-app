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
            f"Add them under Manage data, Users, then tick the request as done under Test account requests.\n")
    try:
        send_mail(f"PHAEMA test account request: {req.name}", body, settings.DEFAULT_FROM_EMAIL, [to])
    except Exception:  # the request is kept in Manage data even if email is not working
        log.exception("Could not email the test account request")
