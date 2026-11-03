# SPDX-License-Identifier: AGPL-3.0-or-later
"""Who pays for a repair, worked out from the lease repairing terms (the repair responsibility matrix)."""
from apps.leases.models import Lease

from .models import Category, Responsibility

R = Responsibility
# Parts a tenant on internal repairing terms looks after; the rest is the landlord's to repair.
INTERNAL = {Category.INTERNAL, Category.MECHANICAL, Category.ELECTRICAL}
LIVE = (Lease.Status.CURRENT, Lease.Status.HOLDING_OVER)


def leases_for(prop):
    """Current agreements letting this property to a tenant."""
    return Lease.objects.filter(properties=prop, direction=Lease.Direction.OUT, status__in=LIVE).distinct()


def _lets_below(prop):
    ids = prop._descendant_ids()
    return Lease.objects.filter(properties__in=ids, direction=Lease.Direction.OUT, status__in=LIVE).distinct()


def _in_service_charge(prop):
    from apps.servicecharges.models import Schedule

    ids = [prop.pk] + [a.pk for a in prop.ancestors()]
    return Schedule.objects.filter(active=True, properties__in=ids).exists()


def decide(prop, category):
    """(responsibility, reason, lease or None) for a repair of this category at this property."""
    leases = list(leases_for(prop).order_by("-term_start")[:2])
    if len(leases) == 1:
        lease = leases[0]
        terms = lease.repairing
        if terms == Lease.Repairing.FRI:
            return R.TENANT, f"{lease.reference} is on full repairing terms", lease
        recover = R.SERVICE_CHARGE if lease.service_charge_payable else R.LANDLORD
        if terms in (Lease.Repairing.IRI, Lease.Repairing.LIMITED):
            if category in INTERNAL:
                return R.TENANT, f"{lease.reference}: the tenant repairs the inside", lease
            return recover, f"{lease.reference}: the council repairs structure and exterior", lease
        if terms == Lease.Repairing.LANDLORD:
            return recover, f"{lease.reference}: the council repairs", lease
        return R.LANDLORD, f"Check {lease.reference}: repairing terms not recorded", lease
    if len(leases) > 1:
        return R.LANDLORD, "More than one current agreement: check which applies", None
    below = _lets_below(prop)
    if below.exists():
        if below.filter(service_charge_payable=True).exists() or _in_service_charge(prop):
            return R.SERVICE_CHARGE, "Common parts of a let building, recovered through the service charge", None
        return R.LANDLORD, "Common parts; the leases have no service charge", None
    # Not let itself, but part of something let as a whole.
    for parent in reversed(prop.ancestors()):
        if leases_for(parent).exists():
            return decide(parent, category)
    return R.LANDLORD, "Not let: the council's cost", None


def matrix(prop):
    return [(label, *decide(prop, value)[:2]) for value, label in Category.choices]
