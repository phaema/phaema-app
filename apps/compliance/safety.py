# SPDX-License-Identifier: AGPL-3.0-or-later
"""What anyone visiting a property should know first (RICS Surveying safely): site hazards, the asbestos
register, open remedial actions and Golden Thread tier."""
from apps.core.models import ModuleSettings


def info(prop):
    if prop is None:
        return None
    chain = [*prop.ancestors(), prop]
    hazards = [(p, p.site_hazards.strip()) for p in chain if (p.site_hazards or "").strip()]
    result = {"property": prop, "hazards": hazards, "asbestos": None, "actions": [], "tier_a": False,
              "compliance": ModuleSettings.load().compliance_enabled}
    if result["compliance"]:
        from .models import Action, BuildingDocument, BuildingSafety, Requirement

        ids = [p.pk for p in chain]
        req = (Requirement.objects.filter(property__in=ids, kind__code="asbestos", active=True)
               .select_related("property", "kind").order_by("-property_id").first())
        register = (BuildingDocument.objects.filter(property__in=ids, category="asbestos", superseded_by__isnull=True)
                    .order_by("-document_date").first())
        cert = req.certificates.order_by("-issued_on").first() if req else None
        result["asbestos"] = {"requirement": req, "certificate": cert, "register": register}
        result["actions"] = list(Action.objects.filter(certificate__requirement__property__in=ids,
                                                       done_on__isnull=True).select_related(
            "certificate__requirement__kind")[:5])
        result["tier_a"] = BuildingSafety.objects.filter(property__in=ids, tier="A").exists()
    return result
