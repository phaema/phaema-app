# SPDX-License-Identifier: AGPL-3.0-or-later
"""Occupier contacts: people in occupying departments who see their own buildings in PHAEMA.

A property liaison (Occupier.liaison) and read-only contacts such as the head of service (Occupier.readers) need no
PHAEMA role. They see only /occupier/ pages, and only for the occupiers they are named on and those below them
(sub-teams). Liaisons may record headcount; read-only contacts change nothing. Everything else in PHAEMA stays
closed to them: RoleRequiredMiddleware lets them reach /occupier/ and their own account pages only.

In a building several occupiers share, the stacking plan names every occupier, but figures (people, capacity, use)
are shown only for the contact's own occupiers.

Needs the space module switched on for the council. See claude/design-occupier-liaison.md in the project notes.
"""
from datetime import date

from django.db.models import Q

PATHS = ("/occupier/", "/account/password/", "/account/two-step/")


def _module_on():
    from apps.core.access import switched_on

    return switched_on("space")


def named_on(user):
    """Occupiers this person is named on, as liaison or read-only contact (active ones only)."""
    from .models import Occupier

    if not getattr(user, "is_authenticated", False):
        return Occupier.objects.none()
    return Occupier.objects.filter(Q(liaison=user) | Q(readers=user), active=True).distinct()


def is_contact(user):
    """True if this person is an occupier contact and the space module is on."""
    return getattr(user, "is_authenticated", False) and _module_on() and named_on(user).exists()


def occupiers_for(user):
    """Every occupier this person may see: those they are named on and every occupier below them."""
    seen = {}
    for occupier in named_on(user):
        for member in occupier.family():
            seen[member.pk] = member
    return list(seen.values())


def editable_for(user):
    """Occupier ids whose figures this person may record: those they are the liaison for, and those below."""
    from .models import Occupier

    ids = set()
    for occupier in Occupier.objects.filter(liaison=user, active=True):
        ids.update(o.pk for o in occupier.family())
    return ids


def buildings_for(user, on=None):
    """Buildings where any of this person's occupiers is in occupation today."""
    from apps.properties.models import Property

    from .models import Occupation

    on = on or date.today()
    ids = {o.pk for o in occupiers_for(user)}
    building_ids = {o.building_id for o in Occupation.objects.filter(occupier_id__in=ids) if o.current(on)}
    return Property.objects.filter(pk__in=building_ids).select_related("managing_surveyor").order_by("reference")
