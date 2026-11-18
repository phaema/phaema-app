# SPDX-License-Identifier: AGPL-3.0-or-later
"""Estates strategy, step 1: the starting lists, and the property's strategy at a glance.

The council's holding purpose sub-categories and its asset strategies are lists administrators keep in Manage data.
These are the starting values, added once; a council's own changes are never overwritten.
"""
from datetime import date, timedelta

STARTING_STRATEGIES = [
    # (name, what it means, follow-on)
    ("Retain as is", "Keep the property for its present purpose with routine maintenance.", ""),
    ("Retain and invest", "Keep it and invest to improve its condition, suitability or energy use.", "development"),
    ("Remodel or share", "Change the layout or bring in other services or partners to use it better.",
     "development"),
    ("Release space", "Give up part of the property: a floor, a wing or surplus land.", ""),
    ("Dispose later", "No long-term need; dispose of it when the timing or market is right.", ""),
    ("Dispose now", "Surplus: start the disposal.", "disposal"),
    ("Community asset transfer", "Transfer to a community organisation to run.", "disposal"),
]

STARTING_CATEGORIES = {
    "operational": ["Offices", "Depots", "Libraries", "Leisure centres", "Car parks", "Schools", "Other operational"],
    "investment": ["Industrial", "Retail", "Offices", "Agricultural", "Ground leases", "Other investment"],
    "community": ["Community centres", "Parks and open space", "Allotments", "Sports grounds"],
    "surplus": [],
    "held_for_sale": [],
}

DUE_SOON_DAYS = 90


def ensure_lists(option_model, category_model):
    """Add the starting lists to an empty installation. Run by migration; safe to run again."""
    if not option_model.objects.exists():
        option_model.objects.bulk_create([
            option_model(name=name, description=text, follow_on=follow, order=i * 10)
            for i, (name, text, follow) in enumerate(STARTING_STRATEGIES)])
    if not category_model.objects.exists():
        category_model.objects.bulk_create([
            category_model(holding_purpose=purpose, name=name, order=i * 10)
            for purpose, names in STARTING_CATEGORIES.items() for i, name in enumerate(names)])


def review_state(prop, today=None):
    """"overdue", "due" (within 90 days) or "" for the property's strategy review date."""
    if not prop.purpose_review_date:
        return ""
    today = today or date.today()
    if prop.purpose_review_date < today:
        return "overdue"
    if prop.purpose_review_date <= today + timedelta(days=DUE_SOON_DAYS):
        return "due"
    return ""


def reviews_due(properties, today=None):
    """Properties whose strategy review is overdue or due within 90 days, soonest first."""
    today = today or date.today()
    return properties.filter(purpose_review_date__isnull=False,
                             purpose_review_date__lte=today + timedelta(days=DUE_SOON_DAYS),
                             disposed_on__isnull=True).order_by("purpose_review_date")


def latest_strategies():
    """{property id: AssetStrategy} for every property with a decision of its own: its newest."""
    from .models import AssetStrategy

    found = {}
    for d in AssetStrategy.objects.select_related("strategy").order_by("property_id", "-decided_on", "-created_at"):
        found.setdefault(d.property_id, d)
    return found


def effective_strategies():
    """{property id: (AssetStrategy, own)} for every property whose strategy is known, its own or the one it
    follows from the nearest property it is part of. Worked out for the whole register in two queries."""
    from .models import Property

    own = latest_strategies()
    parents = dict(Property.objects.values_list("pk", "parent_id"))
    result = {}

    def find(pk, seen=()):
        if pk in result:
            return result[pk]
        if pk in own:
            result[pk] = (own[pk], True)
        elif parents.get(pk) and pk not in seen:
            above = find(parents[pk], (*seen, pk))
            result[pk] = (above[0], False) if above else None
        else:
            result[pk] = None
        return result[pk]

    for pk in parents:
        find(pk)
    return {pk: v for pk, v in result.items() if v}


def latest_grades():
    """{property id: grade} from each property's newest suitability assessment."""
    from .models import SuitabilityAssessment

    found = {}
    for pk, grade in SuitabilityAssessment.objects.order_by("property_id", "-assessed_on", "-created_at") \
            .values_list("property_id", "grade"):
        found.setdefault(pk, grade)
    return found


def overview(today=None):
    """The figures for the Estate strategy page. Disposed-of properties are left out."""
    from django.db.models import Count

    from apps.cases.models import Case

    from .models import AssetStrategyOption, Property, PurposeCategory, SuitabilityAssessment

    today = today or date.today()
    live = Property.objects.filter(disposed_on__isnull=True)
    live_ids = set(live.values_list("pk", flat=True))
    purposes = []
    counts = dict(live.values_list("holding_purpose").annotate(n=Count("pk")))
    by_category = dict(live.exclude(purpose_category=None).values_list("purpose_category").annotate(n=Count("pk")))
    categories = list(PurposeCategory.objects.all())
    for value, label in [*Property.HoldingPurpose.choices, ("", "Not set")]:
        subs = [(c, by_category.get(c.pk, 0)) for c in categories if c.holding_purpose == value]
        purposes.append({"value": value, "label": label, "count": counts.get(value, 0),
                         "categories": [(c, n) for c, n in subs if n or c.active]})
    effective = {pk: v for pk, v in effective_strategies().items() if pk in live_ids}
    strategies = []
    for option in AssetStrategyOption.objects.all():
        own = sum(1 for d, is_own in effective.values() if is_own and d.strategy_id == option.pk)
        total = sum(1 for d, _o in effective.values() if d.strategy_id == option.pk)
        if own or option.active:
            strategies.append({"option": option, "own": own, "total": total})
    grades = {pk: g for pk, g in latest_grades().items() if pk in live_ids}
    return {
        "today": today, "total": len(live_ids), "purposes": purposes, "strategies": strategies,
        "without_strategy": len(live_ids) - len(effective),
        "overdue": live.filter(purpose_review_date__lt=today).count(),
        "due_soon": live.filter(purpose_review_date__gte=today,
                                purpose_review_date__lte=today + timedelta(days=DUE_SOON_DAYS)).count(),
        "due_year": live.filter(purpose_review_date__gte=today,
                                purpose_review_date__lte=today + timedelta(days=365)).count(),
        "challenges": list(Case.objects.filter(case_type__asset_challenge=True).exclude(status=Case.Status.CLOSED)
                           .select_related("property", "owner", "proposed_strategy").order_by("received_on")),
        "grades": [(value, label, sum(1 for g in grades.values() if g == value))
                   for value, label in SuitabilityAssessment.Grade.choices],
        "graded": len(grades),
    }
