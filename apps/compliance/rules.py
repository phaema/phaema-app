# SPDX-License-Identifier: AGPL-3.0-or-later
"""Who holds each certificate, and which Golden Thread tier a building falls in."""
from decimal import Decimal

from apps.leases.models import Lease
from apps.maintenance.responsibility import leases_for

from .models import BuildingSafety, Requirement

BUILDING_TYPES = ("building", "unit")


def responsible(prop):
    """(council or tenant, reason). A tenant on full repairing terms of the whole property holds its certificates;
    the council holds them for common parts and anything not let that way."""
    leases = list(leases_for(prop)[:2])
    if len(leases) == 1 and leases[0].repairing == Lease.Repairing.FRI:
        return Requirement.Responsible.TENANT, f"{leases[0].reference} is on full repairing terms: obtain a copy"
    if leases:
        return Requirement.Responsible.COUNCIL, "Let, but the council keeps the building's certificates"
    return Requirement.Responsible.COUNCIL, "Not let, or common parts"


def suggested_tier(prop, screening=None):
    """(tier, reason). Higher-risk in England: at least 18 metres or at least 7 storeys, with at least two
    residential units (Building Safety Act 2022). An officer confirms."""
    if prop.property_type not in BUILDING_TYPES:
        return BuildingSafety.Tier.C, "Land or a site without its own buildings"
    s = screening
    if s is None:
        return BuildingSafety.Tier.B, "Not screened yet: best practice by default"
    tall = (s.height_m is not None and s.height_m >= Decimal("18")) or (s.storeys or 0) >= 7
    if tall and s.residential_units >= 2:
        return BuildingSafety.Tier.A, "18 metres or 7 storeys or more, with two or more homes"
    if s.country == BuildingSafety.Country.WALES and s.residential_units >= 2:
        return BuildingSafety.Tier.B, ("Wales: buildings with two or more homes may fall under the Welsh building "
                                       "safety regime: check and confirm")
    return BuildingSafety.Tier.B, "Covered by the Fire Safety Order: best practice"
