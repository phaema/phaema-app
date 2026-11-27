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
    from apps.core.models import ModuleSettings

    modules = ModuleSettings.load()
    if not modules.tenant_portal_enabled:  # so the demo accounts can be tried on a test site
        modules.tenant_portal_enabled = True
        modules.save(update_fields=["tenant_portal_enabled"])
    accounts = {}
    for ref, name, email, finance, facilities in ACCOUNTS:
        lease = Lease.objects.filter(reference=ref).select_related("counterparty").first()
        if lease is None:
            continue
        accounts[ref], _c = PortalAccount.objects.update_or_create(email=email, defaults={
            "party": lease.counterparty, "name": name, "finance": finance, "facilities": facilities, "active": True})
        lease.documents.filter(document_type="lease").update(shared_with_tenant=True)
    if "DL-0506" in accounts:
        _activity(Lease.objects.get(reference="DL-0506"), accounts["DL-0506"])


def _activity(lease, account):
    """A repair report, a request, a message and a contact change from the tenant, so the queues have something in
    them on a test site."""
    from apps.cases import workflow
    from apps.cases.models import Case, CaseType, Correspondence
    from apps.maintenance.models import RepairReport

    from .models import ContactChange, PortalMessage

    prop = lease.properties.first()
    if prop is not None and not RepairReport.objects.filter(portal_account=account).exists():
        RepairReport.objects.create(
            property=prop, lease=lease, source="tenant", portal_account=account, reporter_name=account.name,
            contact_phone="07700 900506", location="Workshop roof, back corner", danger=True,
            description="Rain is coming through onto the main bench when it rains heavily. Started on Monday.")
    alterations = CaseType.objects.filter(code="alterations").first()
    if alterations and not Case.objects.filter(portal_account=account).exists():
        case = workflow.open_case(alterations, title="New extraction system for the spray booth", lease=lease,
                                  how_received="portal", portal_account=account)
        Correspondence.objects.create(case=case, direction="in", method="online",
                                      correspondent=f"{account.name} ({lease.counterparty.name})",
                                      subject=case.title,
                                      summary="We want to replace the extraction in the spray booth with a larger "
                                              "unit and a new flue through the rear wall.")
    if not PortalMessage.objects.filter(account=account).exists():
        PortalMessage.objects.create(lease=lease, direction="in", account=account,
                                     text="Could someone ring me about renewing the lease? It ends next year.")
    if not ContactChange.objects.filter(account=account).exists():
        ContactChange.objects.create(lease=lease, account=account, contact_name="Northfield Joinery accounts",
                                     email="accounts@northfield-joinery.example", phone=lease.counterparty.phone,
                                     address=lease.counterparty.address, note="Please send demands to our accounts team.")


def remove():
    from apps.cases.models import Case
    from apps.maintenance.models import RepairReport

    demo = PortalAccount.objects.filter(email__endswith=DOMAIN)
    RepairReport.objects.filter(portal_account__in=demo).delete()
    Case.objects.filter(portal_account__in=demo).delete()
    demo.delete()
