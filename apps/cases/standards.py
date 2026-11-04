# SPDX-License-Identifier: AGPL-3.0-or-later
"""Checks from the professional standards that sit on a case: MEES before a letting (Energy Efficiency
(Private Rented Property) Regulations 2015), dilapidations (Pre-Action Protocol for Claims for Damages in
Relation to the Physical State of Commercial Property at Termination of a Tenancy) and conflicts of interest
(RICS Conflicts of interest professional standard)."""
from datetime import date

from django.utils.translation import gettext as _

from apps.core.models import ModuleSettings

LETTING_TYPES = {"new_letting", "renewal"}
DILAPS_TYPES = {"dilapidations", "expiry"}


def mees(case, today=None):
    """Warnings about the EPC for the property being let. Warning only: exemptions may apply."""
    if case.case_type.code not in LETTING_TYPES or not ModuleSettings.load().compliance_enabled:
        return []
    prop = case.property or (case.lease.property if case.lease_id else None)
    if prop is None:
        return []
    from apps.compliance.models import Certificate

    today = today or date.today()
    chain = [prop, *reversed(prop.ancestors())]  # nearest first: a unit's own EPC, then its building's
    for p in chain:
        cert = (Certificate.objects.filter(requirement__property=p, requirement__kind__code="epc")
                .order_by("-issued_on", "-pk").first())
        if cert is None:
            continue
        band = (cert.rating or "").strip().upper()[:1]
        warnings = []
        if band in ("F", "G"):
            warnings.append(_("The EPC for %(ref)s is rated %(band)s. A letting below E breaks the minimum energy "
                              "efficiency standard unless an exemption is registered on the PRS Exemptions "
                              "Register.") % {"ref": p.reference, "band": band})
        if cert.expires_on and cert.expires_on < today:
            warnings.append(_("The EPC for %(ref)s expired on %(d)s. A valid EPC is needed before marketing or "
                              "letting.") % {"ref": p.reference, "d": cert.expires_on.strftime("%-d %b %Y")})
        return warnings
    return [_("There is no EPC recorded for %(ref)s. Check whether one is needed before letting.")
            % {"ref": prop.reference}]


def dilaps(case):
    if case.case_type.code not in DILAPS_TYPES:
        return None
    gap = None
    if case.dilaps_schedule_value is not None and case.dilaps_settlement_value is not None:
        gap = case.dilaps_schedule_value - case.dilaps_settlement_value
    return {"lease": case.lease, "gap": gap}


def conflict_missing(case):
    return not case.conflict
