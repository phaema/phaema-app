# SPDX-License-Identifier: AGPL-3.0-or-later
"""Demo tenant portal accounts. Sign in at /tenant/ with one of these addresses; on a test site with
PHAEMA_PORTAL_SHOW_CODES the code is shown on screen."""
from apps.leases.models import Lease

from .models import PortalAccount

DOMAIN = "@portal.example"
ACCOUNTS = [  # (agreement, name, email, finance, facilities)
    ("DL-0506", "Mark Davies", "mark" + DOMAIN, True, True),
    ("DL-0514", "Bakery accounts", "bakery" + DOMAIN, True, False),
]


def load():
    for ref, name, email, finance, facilities in ACCOUNTS:
        lease = Lease.objects.filter(reference=ref).select_related("counterparty").first()
        if lease is None:
            continue
        PortalAccount.objects.update_or_create(email=email, defaults={
            "party": lease.counterparty, "name": name, "finance": finance, "facilities": facilities, "active": True})
        lease.documents.filter(document_type="lease").update(shared_with_tenant=True)


def remove():
    PortalAccount.objects.filter(email__endswith=DOMAIN).delete()
