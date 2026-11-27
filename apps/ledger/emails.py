# SPDX-License-Identifier: AGPL-3.0-or-later
"""Emailing a demand run to tenants: one email per agreement, listing its charges in the run, the balance on the
account and a "Pay now" link to the council's payment page. Sent through GOV.UK Notify (apps.core.notify)."""
from collections import OrderedDict
from dataclasses import dataclass, field
from decimal import Decimal
from urllib.parse import quote

from django.conf import settings as django_settings
from django.utils import translation
from django.utils.formats import date_format
from django.utils.translation import gettext as _

from apps.core import notify
from apps.core.models import ModuleSettings, OutgoingEmail

from . import billing

KIND = "demand"


@dataclass
class Demand:
    lease: object
    to: str
    charges: list = field(default_factory=list)
    already: OutgoingEmail | None = None  # the email sent or recorded for this run earlier, if any

    @property
    def total(self):
        return sum((c.gross for c in self.charges), Decimal("0"))

    @property
    def reference(self):
        """What the tenant quotes when paying: the charge's number if there is one charge, otherwise the agreement."""
        return self.charges[0].reference if len(self.charges) == 1 else self.lease.reference


def demands(run):
    """The agreements in a demand run with a positive amount to ask for, and where each email would go."""
    by_lease = OrderedDict()
    for c in run.charges.select_related("lease", "lease__counterparty").order_by("lease__reference", "due_date", "pk"):
        by_lease.setdefault(c.lease_id, []).append(c)
    earlier = {e.lease_id: e for e in run.emails.filter(kind=KIND).order_by("created_at")}
    out = []
    for charges in by_lease.values():
        lease = charges[0].lease
        demand = Demand(lease, lease.billing["email"], charges, earlier.get(lease.pk))
        if demand.total > 0:
            out.append(demand)
    return out


def _money(amount):
    return f"£{amount:,.2f}"


def pay_link(settings, demand):
    if not settings.payment_link:
        return ""
    values = {"reference": demand.reference, "amount": f"{demand.total:.2f}", "account": demand.lease.reference}
    link = settings.payment_link
    for key, value in values.items():
        link = link.replace("{" + key + "}", quote(str(value), safe=""))
    return link


def compose(demand, settings=None):
    """The subject and body of the email for one agreement, in the site's main language (not the language of the
    person pressing send)."""
    with translation.override(django_settings.LANGUAGE_CODE):
        return _compose(demand, settings or ModuleSettings.load())


def _compose(demand, settings):
    lease = demand.lease
    council = settings.organisation_name or _("The council")
    premises = lease.premises_description or ", ".join(p.name for p in lease.properties.all()) or lease.reference
    name = lease.billing["name"] or lease.counterparty.name
    lines = [_("Dear %(name)s,") % {"name": name}, "",
             _("%(council)s has issued the following charges for %(premises)s (agreement %(ref)s):") % {
                 "council": council, "premises": premises, "ref": lease.reference}, ""]
    for c in demand.charges:
        lines.append(_("%(ref)s: %(what)s, due %(due)s: %(amount)s") % {
            "ref": c.reference, "what": c.description, "due": date_format(c.due_date, "j F Y"),
            "amount": _money(c.gross)})
    lines += ["", _("Total: %(amount)s") % {"amount": _money(demand.total)}]
    acc = billing.account(lease)
    if acc.overdue > 0:
        lines.append(_("Your account also shows %(amount)s overdue from earlier charges.") % {
            "amount": _money(acc.overdue)})
    lines.append("")
    link = pay_link(settings, demand)
    if link:
        lines += [_("Pay now: %(link)s") % {"link": link}, ""]
    lines += [_("Please quote %(ref)s when you pay.") % {"ref": demand.reference}, ""]
    contact = " · ".join(x for x in (settings.department, settings.letter_email, settings.letter_phone) if x)
    if contact:
        lines += [_("If you have a question about these charges, contact %(contact)s.") % {"contact": contact}, ""]
    lines.append(council)
    subject = _("%(council)s: charges for %(premises)s, %(amount)s") % {
        "council": council, "premises": premises, "amount": _money(demand.total)}
    return subject[:250], "\n".join(lines)


def send_run(run, user, again=False):
    """Email every agreement in the run that has an email address. Agreements already emailed for this run are
    skipped, unless `again` is set, in which case only those whose email failed are tried again."""
    settings = ModuleSettings.load()
    made = []
    for demand in demands(run):
        if not demand.to:
            continue
        if demand.already and not (again and demand.already.status == OutgoingEmail.Status.FAILED):
            continue
        subject, body = compose(demand, settings)
        email = OutgoingEmail.objects.create(kind=KIND, to=demand.to, subject=subject, body=body,
                                             lease=demand.lease, demand_run=run, created_by=user)
        made.append(notify.send(email))
    return made  # each OutgoingEmail is itself the record of what was sent, to whom, by whom and when
