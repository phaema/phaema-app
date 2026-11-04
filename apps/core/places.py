# SPDX-License-Identifier: AGPL-3.0-or-later
"""Building and managing surveyor filters, shared by the list pages.

?building=<id> keeps records on that estate, site or building or any part of it.
?surveyor=me | none | <user id> keeps records on properties that surveyor manages.
"""
from django.contrib.auth import get_user_model
from django.db.models import Q

from apps.properties.models import Property

BUILDING_TYPES = ("estate", "site", "building")


def buildings():
    return Property.objects.filter(property_type__in=BUILDING_TYPES).order_by("reference")


def surveyors():
    return (get_user_model().objects.filter(is_active=True, managed_properties__isnull=False).distinct()
            .order_by("first_name", "last_name", "username"))


def subtree(pk):
    prop = Property.objects.filter(pk=pk).first()
    return [] if prop is None else [prop.pk, *prop._descendant_ids()]


def apply(qs, get, user, *paths):
    """Filter a queryset by building and surveyor. Each path leads to a Property (e.g. "property",
    "lease__properties"); a record matches if any path matches."""
    building = get.get("building", "")
    if building.isdigit():
        ids = subtree(int(building))
        cond = Q()
        for path in paths:
            cond |= Q(**{f"{path}__in": ids})
        qs = qs.filter(cond)
    who = get.get("surveyor", "")
    if who:
        cond = Q()
        for path in paths:
            if who == "me":
                cond |= Q(**{f"{path}__managing_surveyor": user})
            elif who == "none":
                cond |= Q(**{f"{path}__isnull": False, f"{path}__managing_surveyor__isnull": True})
            elif who.isdigit():
                cond |= Q(**{f"{path}__managing_surveyor_id": int(who)})
        qs = qs.filter(cond)
    if building or who:
        qs = qs.distinct()
    return qs


def keep(prop, get, user):
    """The same test for one property, for lists built in Python."""
    building = get.get("building", "")
    if building.isdigit() and (prop is None or prop.pk not in set(subtree(int(building)))):
        return False
    who = get.get("surveyor", "")
    if who == "me":
        return prop is not None and prop.managing_surveyor_id == user.pk
    if who == "none":
        return prop is not None and prop.managing_surveyor_id is None
    if who.isdigit():
        return prop is not None and prop.managing_surveyor_id == int(who)
    return True


def filters(get):
    """Rows for a list page's filter panel: (name, label, choices, current, any)."""
    return [
        ("building", "Building or estate", [(str(p.pk), f"{p.reference} {p.name}") for p in buildings()],
         get.get("building", ""), True),
        ("surveyor", "Managing surveyor", [("me", "Mine"), ("none", "Nobody")]
         + [(str(u.pk), u.get_full_name() or u.username) for u in surveyors()], get.get("surveyor", ""), True),
    ]
