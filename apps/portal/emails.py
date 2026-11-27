# SPDX-License-Identifier: AGPL-3.0-or-later
"""Emails from the tenant portal: invitations and sign-in codes, sent through GOV.UK Notify like demands."""
from django.conf import settings
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from apps.core import notify
from apps.core.models import ModuleSettings, OutgoingEmail

from .models import SignInCode


def _council():
    return ModuleSettings.load().organisation_name or settings.PHAEMA_ORGANISATION_NAME or _("The council")


def portal_url():
    return settings.PHAEMA_BASE_URL.rstrip("/") + reverse("portal:sign-in")


def invite(account, user):
    with translation.override(settings.LANGUAGE_CODE):
        council = _council()
        subject = _("%(council)s: your tenant portal account") % {"council": council}
        body = "\n".join([
            _("Dear %(name)s,") % {"name": account.name}, "",
            _("%(council)s has given you an account on its tenant portal for %(tenant)s. You can see your rent "
              "account, demands, key dates and documents the council shares with you.") % {
                "council": council, "tenant": account.party.name}, "",
            _("To sign in, go to %(url)s and enter this email address. We will email you a code each time.") % {
                "url": portal_url()}, "",
            _("If you were not expecting this, you can ignore this email."), "", council])
    email = OutgoingEmail.objects.create(kind="portal_invite", to=account.email, subject=subject, body=body,
                                         created_by=user)
    notify.send(email)
    account.invited_by, account.invited_at = user, timezone.now()
    account.save(update_fields=["invited_by", "invited_at", "updated_at"])
    return email


def send_code(account):
    """Email a new sign-in code. The record keeps the email without the code. Returns (email, code)."""
    _row, code = SignInCode.issue(account)
    with translation.override(settings.LANGUAGE_CODE):
        council = _council()
        subject = _("%(council)s tenant portal: your sign-in code") % {"council": council}
        lines = [_("Your sign-in code is %(code)s"), "",
                 _("It works once, for %(minutes)s minutes.") % {"minutes": SignInCode.MINUTES}, "",
                 _("If you did not try to sign in, you can ignore this email."), "", council]
        template = "\n".join(lines)
    email = OutgoingEmail.objects.create(kind="portal_code", to=account.email, subject=subject,
                                         body=template.replace("%(code)s", "••••••"))
    notify.send(email, body=template.replace("%(code)s", code))
    return email, code
