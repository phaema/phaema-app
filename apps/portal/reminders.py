# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reminding tenants, by email through GOV.UK Notify, about certificates they must provide (for example a gas
safety record on a tenant-repairing lease) that are missing, run out, or run out within 30 days. Each certificate
is reminded about at most once every 30 days. Only tenants with a portal account with facilities rights are emailed,
so the reminder can point to the portal to send the new certificate."""
from datetime import date, timedelta

from django.conf import settings
from django.urls import reverse
from django.utils import translation
from django.utils.translation import gettext as _

from apps.core import notify
from apps.core.models import ModuleSettings, OutgoingEmail

AHEAD = 30
EVERY = timedelta(days=30)


def _due(req, today):
    cert = req.certificates.order_by("-issued_on", "-pk").first()
    if cert is None:
        return True, None
    return cert.expires_on <= today + timedelta(days=AHEAD), cert.expires_on


def send_certificate_reminders(today=None):
    from apps.compliance.models import Requirement
    from apps.leases.models import Lease

    from .access import agreements_for
    from .models import PortalAccount

    today = today or date.today()
    modules = ModuleSettings.load()
    if not (modules.tenant_portal_enabled and modules.compliance_enabled):
        return 0
    council = modules.organisation_name or settings.PHAEMA_ORGANISATION_NAME
    sent = 0
    reqs = (Requirement.objects.filter(responsible="tenant", active=True)
            .select_related("kind", "property"))
    for req in reqs:
        if req.tenant_reminded_on and today - req.tenant_reminded_on < EVERY:
            continue
        due, expires = _due(req, today)
        if not due:
            continue
        leases = Lease.objects.filter(properties=req.property, direction=Lease.Direction.OUT,
                                      status__in=(Lease.Status.CURRENT, Lease.Status.HOLDING_OVER)).distinct()
        accounts = [a for a in PortalAccount.objects.filter(party__leases__in=leases, active=True, facilities=True)
                    .select_related("party").distinct()]
        emailed = False
        for account in accounts:
            lease = agreements_for(account, today).filter(pk__in=leases).first()
            if lease is None:
                continue
            link = settings.PHAEMA_BASE_URL.rstrip("/") + reverse("portal:certificate", args=[lease.pk, req.pk])
            with translation.override(settings.LANGUAGE_CODE):
                if expires is None:
                    state = _("We do not have a copy of your %(kind)s for %(place)s.")
                elif expires < today:
                    state = _("Your %(kind)s for %(place)s ran out on %(date)s.")
                else:
                    state = _("Your %(kind)s for %(place)s runs out on %(date)s.")
                state = state % {"kind": req.kind.name, "place": req.property.name,
                                 "date": expires.strftime("%-d %B %Y") if expires else ""}
                subject = _("%(council)s: %(kind)s for %(place)s") % {
                    "council": council, "kind": req.kind.name, "place": req.property.name}
                body = "\n".join([
                    _("Dear %(name)s,") % {"name": account.name}, "", state, "",
                    _("Under your agreement %(ref)s you arrange this and send the council a copy. When you have "
                      "the new certificate, send it here: %(link)s") % {"ref": lease.reference, "link": link}, "",
                    council])
            email = OutgoingEmail.objects.create(kind="certificate_reminder", to=account.email, subject=subject[:250],
                                                 body=body, lease=lease)
            notify.send(email)
            sent += 1
            emailed = True
        if emailed:
            Requirement.objects.filter(pk=req.pk).update(tenant_reminded_on=today)
    return sent
