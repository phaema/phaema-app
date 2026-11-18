# SPDX-License-Identifier: AGPL-3.0-or-later
"""Demonstration estate strategy: sub-categories, asset strategies with their history, suitability grades and one
Asset Challenge in progress. Dates are relative to the day the data is loaded, so some reviews are due."""
from datetime import date, timedelta

from .models import AssetStrategy, AssetStrategyOption, Property, PurposeCategory, SuitabilityAssessment

CATEGORIES = {
    "DM-S02": "Offices", "DM-S30": "Offices", "DM-S04": "Depots", "DM-N03": "Libraries", "DM-S03": "Car parks",
    "DM-N11": "Car parks", "DM-E01": "Industrial", "DM-N01": "Industrial", "DM-S01": "Retail", "DM-N02": "Retail",
    "DM-N09": "Retail", "DM-S10": "Agricultural", "DM-N10": "Agricultural", "DM-S05": "Community centres",
    "DM-N05": "Community centres", "DM-S08": "Allotments", "DM-N08": "Sports grounds",
}

# reference, strategy, days ago, decided by, minute reference, reason
STRATEGIES = [
    ("DM-S04", "Retain as is", 6 * 365 + 30, "Cabinet", "CAB/2020/41",
     "Needed for the waste and highways fleets; no alternative site in the district."),
    ("DM-E01", "Retain as is", 2 * 365, "Cabinet", "CAB/2024/57",
     "Fully let, strong income and low voids. Keep as part of the investment estate."),
    ("DM-N01", "Retain and invest", 365, "Asset Management Board", "AMB/2025/12",
     "Demand for small units is high. Invest in phase 2 to add units and improve energy performance."),
    ("DM-S06", "Dispose now", 430, "Cabinet", "CAB/2025/31",
     "No service need since the school closed. Sell for housing on the open market."),
    ("DM-N06", "Dispose later", 5 * 365 - 60, "Head of Estates", "",
     "Contaminated; dispose once remediation costs are known and the market for the site improves."),
    ("DM-S30", "Remodel or share", 240, "Asset Management Board", "AMB/2026/03",
     "Space is under-used on the second floor. Bring in partners under One Public Estate and release vacant space."),
]

# reference, grade, days ago, notes
SUITABILITY = [
    ("DM-N03", "B", 5 * 365, "Good location; layout fits the service."),
    ("DM-N03", "C", 60, "Poor access for wheelchair users at the rear; children's library too small."),
    ("DM-S30", "B", 200, "Open-plan floors suit modern working; meeting space short."),
    ("DM-S02", "C", 400, "Listed building: cellular rooms limit open-plan working; no lift to the second floor."),
    ("DM-S04", "C", 90, "Workshop too small for electric vehicles; yard congested at shift change."),
    ("DM-S05", "D", 150, "Hall too small for current bookings; no accessible toilet."),
    ("DM-N04", "B", 300, "Pool and sports hall suit the service; changing rooms dated."),
]


def load(today=None):
    today = today or date.today()
    props = {p.reference: p for p in Property.objects.filter(reference__in=(
        set(CATEGORIES) | {r for r, *_x in STRATEGIES} | {r for r, *_x in SUITABILITY}))}
    for ref, name in CATEGORIES.items():
        prop = props.get(ref)
        category = PurposeCategory.objects.filter(name=name, holding_purpose=prop.holding_purpose).first() \
            if prop else None
        if category:
            Property.objects.filter(pk=prop.pk).update(purpose_category=category)
    options = {o.name: o for o in AssetStrategyOption.objects.all()}
    for ref, name, days, by, minute, reason in STRATEGIES:
        if ref in props and name in options and not props[ref].strategies.exists():
            AssetStrategy.objects.create(property=props[ref], strategy=options[name],
                                         decided_on=today - timedelta(days=days), decided_by=by,
                                         minute_reference=minute, reason=reason, source=AssetStrategy.Source.DIRECT)
    for ref, grade, days, notes in SUITABILITY:
        if ref in props and not props[ref].suitability.filter(grade=grade, notes=notes).exists():
            SuitabilityAssessment.objects.create(property=props[ref], grade=grade, notes=notes,
                                                 assessed_on=today - timedelta(days=days))
    _challenge(props.get("DM-S04"), options.get("Remodel or share"), today)


def _challenge(prop, proposal, today):
    """An Asset Challenge at the depot, part way through: its strategy is overdue for review."""
    from apps.cases import workflow
    from apps.cases.models import Case, CaseNote, CaseType

    kind = CaseType.objects.filter(code="asset_challenge").first()
    if prop is None or kind is None or Case.objects.filter(crm_reference="DEMO-AC-1").exists():
        return
    case = workflow.open_case(kind, title="Asset Challenge: Mill Lane depot", property=prop,
                              received_on=today - timedelta(days=40), how_received=Case.Received.OTHER,
                              crm_reference="DEMO-AC-1")
    case.stage, case.proposed_strategy = "assessing", proposal
    case.save(update_fields=["stage", "proposed_strategy", "updated_at"])
    for task in case.tasks.filter(description__regex=r"^(Strategic purpose|Opportunities|Performance)"):
        task.done_on, task.done_by = today - timedelta(days=20), case.owner
        task.save(update_fields=["done_on", "done_by"])
    CaseNote.objects.create(case=case, text=(
        "Fleet services confirm the depot is still needed, but only about two-thirds of the yard. Highways and the "
        "county's fire service have asked about sharing. Option appraisal under way: share the site, or release "
        "the eastern yard for light industrial units."))
