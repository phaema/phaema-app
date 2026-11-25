# SPDX-License-Identifier: AGPL-3.0-or-later
"""Dealings with agreements: assignments, underleases, sharing and charges.

A consent case for an assignment, underletting or sharing opens a dealing on the agreement, and the case's decision
moves it on (consent given, refused or withdrawn). Completing an assignment makes the assignee the tenant on the
agreement. The former tenant is kept on the dealing, so the history of who held the lease is never lost, and a
former tenant who gave an authorised guarantee agreement (AGA) is shown as still liable on the party's page.
"""
from django.db import transaction
from django.utils import timezone

from .models import Dealing, Lease

CASE_KINDS = {"assignment": Dealing.Kind.ASSIGNMENT, "underletting": Dealing.Kind.UNDERLEASE,
              "sharing": Dealing.Kind.SHARING}


def from_case(case):
    """Open or update the dealing for a consent case. Returns the dealing, or None for other case types."""
    kind = CASE_KINDS.get(case.case_type.code)
    if kind is None or case.lease_id is None:
        return None
    from apps.cases.models import Case

    dealing = Dealing.objects.filter(case=case).first()
    if dealing is None:
        dealing = Dealing(lease=case.lease, kind=kind, case=case)
    if dealing.status == Dealing.Status.COMPLETED:
        return dealing
    decision = case.decision
    if decision in (Case.Decision.APPROVED, Case.Decision.CONDITIONS):
        dealing.status = Dealing.Status.CONSENTED
        dealing.consent_on = case.decision_on
    elif decision == Case.Decision.REFUSED:
        dealing.status = Dealing.Status.REFUSED
    elif decision == Case.Decision.WITHDRAWN:
        dealing.status = Dealing.Status.WITHDRAWN
    else:
        dealing.status = Dealing.Status.PROPOSED
    dealing.save()
    return dealing


def rent_owed(lease):
    """What is owed on the agreement's rent account, when the rent ledger is on (else None)."""
    from apps.core.models import ModuleSettings

    if not ModuleSettings.load().rent_ledger_enabled:
        return None
    from apps.ledger import billing

    return billing.account(lease).balance


@transaction.atomic
def complete(dealing, completed_on=None, to_party=None, guarantor=None, aga=None):
    """Record a dealing as completed. For an assignment, the assignee becomes the tenant on the agreement and the
    new guarantor (if any) replaces the old one."""
    if to_party is not None:
        dealing.to_party = to_party
    if guarantor is not None:
        dealing.guarantor = guarantor
    if aga is not None:
        dealing.aga = aga
    if dealing.to_party_id is None and dealing.kind != Dealing.Kind.CHANGE_OF_CONTROL:
        raise ValueError("Say who the dealing is with before recording it as completed.")
    lease = Lease.objects.select_for_update().get(pk=dealing.lease_id)
    if dealing.kind == Dealing.Kind.ASSIGNMENT:
        if dealing.to_party_id == lease.counterparty_id:
            raise ValueError("The assignee is already the tenant.")
        dealing.from_party_id = lease.counterparty_id
        lease.counterparty_id = dealing.to_party_id
        lease.guarantor_id = dealing.guarantor_id
        lease.save()
    dealing.status = Dealing.Status.COMPLETED
    dealing.completed_on = completed_on or timezone.localdate()
    dealing.save()
    return dealing


def tenants(lease):
    """Who has held the agreement, oldest first: [(party, from date, to date, gave an AGA)]."""
    done = list(lease.dealings.filter(kind=Dealing.Kind.ASSIGNMENT, status=Dealing.Status.COMPLETED)
                .select_related("from_party", "to_party").order_by("completed_on", "pk"))
    if not done:
        return [(lease.counterparty, lease.term_start, None, False)]
    rows, start = [], lease.term_start
    for d in done:
        rows.append((d.from_party, start, d.completed_on, d.aga))
        start = d.completed_on
    rows.append((done[-1].to_party, start, None, False))
    return rows


def liable_former_tenants(lease):
    """Former tenants still liable under an AGA: only the one who assigned to the current tenant."""
    last = (lease.dealings.filter(kind=Dealing.Kind.ASSIGNMENT, status=Dealing.Status.COMPLETED)
            .select_related("from_party").order_by("-completed_on", "-pk").first())
    return [last.from_party] if last and last.aga and last.to_party_id == lease.counterparty_id else []
