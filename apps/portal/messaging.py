# SPDX-License-Identifier: AGPL-3.0-or-later
"""Messages between tenants and the estates team. A tenant's message goes to the managing surveyor of the
agreement's property and to anyone covering for them that day; if no one manages the property, to the
administrators. Emails only say there is a message: the text stays in PHAEMA."""
import logging
from datetime import date

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from apps.core import notify
from apps.core.audit import audited_update
from apps.core.models import Cover, ModuleSettings, OutgoingEmail

from .models import PortalAccount, PortalMessage

log = logging.getLogger(__name__)


def surveyors(lease):
    return {p.managing_surveyor for p in lease.properties.select_related("managing_surveyor")
            if p.managing_surveyor and p.managing_surveyor.is_active}


def answerers(lease, today=None):
    """Who should answer: the managing surveyors, anyone covering for them today, or else the administrators."""
    today = today or date.today()
    people = surveyors(lease)
    covers = Cover.objects.filter(covered__in=people, starts_on__lte=today, ends_on__gte=today).select_related("user")
    people |= {c.user for c in covers if c.user.is_active}
    if not people:
        people = set(get_user_model().objects.filter(is_active=True, groups__name="Administrators"))
    return people


def from_tenant(lease, account, text, case=None):
    message = PortalMessage.objects.create(lease=lease, case=case, direction=PortalMessage.Direction.FROM_TENANT,
                                           account=account, text=text)
    link = settings.PHAEMA_BASE_URL.rstrip("/") + reverse("leases:messages", args=[lease.pk])
    to = [u.email for u in answerers(lease) if u.email]
    if to:
        try:
            send_mail(f"Message from a tenant: {lease.reference} {lease.counterparty.name}",
                      f"{account.name} ({account.party.name}) has sent a message in the tenant portal about "
                      f"{lease.reference}.\n\nRead and answer it in PHAEMA: {link}\n",
                      settings.DEFAULT_FROM_EMAIL, to, fail_silently=False)
        except Exception:
            log.exception("Could not email staff about tenant message %s", message.pk)
    return message


def reply(lease, user, text, case=None):
    """Answer the tenant. Marks their earlier messages answered and tells them by email that there is a reply."""
    now = timezone.now()
    audited_update(lease.portal_messages.filter(direction=PortalMessage.Direction.FROM_TENANT,
                                                answered_at__isnull=True), answered_at=now)
    message = PortalMessage.objects.create(lease=lease, case=case, direction=PortalMessage.Direction.TO_TENANT,
                                           author=user, text=text)
    asked = set(lease.portal_messages.filter(direction="in").values_list("account_id", flat=True))
    accounts = PortalAccount.objects.filter(party_id=lease.counterparty_id, active=True)
    targets = [a for a in accounts if a.pk in asked] or list(accounts)
    modules = ModuleSettings.load()
    council = modules.organisation_name or settings.PHAEMA_ORGANISATION_NAME
    link = settings.PHAEMA_BASE_URL.rstrip("/") + reverse("portal:messages", args=[lease.pk])
    for account in targets:
        with translation.override(settings.LANGUAGE_CODE):
            subject = _("%(council)s: a reply about %(ref)s") % {"council": council, "ref": lease.reference}
            body = "\n".join([_("Dear %(name)s,") % {"name": account.name}, "",
                              _("The estates team has replied to your message about %(ref)s. Sign in to read it: "
                                "%(link)s") % {"ref": lease.reference, "link": link}, "", council])
        email = OutgoingEmail.objects.create(kind="portal_message", to=account.email, subject=subject[:250],
                                             body=body, lease=lease, created_by=user)
        notify.send(email)
    return message


def waiting_for(user, today=None):
    """Tenant messages not yet answered that this person should answer."""
    from apps.core.roles import is_administrator

    today = today or date.today()
    waiting = PortalMessage.objects.filter(direction="in", answered_at__isnull=True).select_related(
        "lease", "lease__counterparty", "account")
    covered = set(Cover.objects.filter(user=user, starts_on__lte=today, ends_on__gte=today)
                  .values_list("covered_id", flat=True))
    mine = Q(lease__properties__managing_surveyor=user) | Q(lease__properties__managing_surveyor__in=covered)
    if is_administrator(user):
        mine |= ~Q(lease__properties__managing_surveyor__isnull=False)
    return waiting.filter(mine).distinct()
