# SPDX-License-Identifier: AGPL-3.0-or-later
"""Outside users (consultants, contractors, tenants' agents) and the date their access ends.

Anyone can have an access end date; outside users always get one. On and after the day after it:
- signing in with a password, the API, or the council's own sign-in is refused;
- anyone still signed in is signed out at their next click;
- the daily housekeeping closes the account (``is_active`` off), so administrators can see it has ended.
"""
from datetime import date, timedelta

from .dates import add_months

WARN_DAYS = 14


def default_end(today=None):
    from .models import ModuleSettings

    return add_months(today or date.today(), ModuleSettings.load().outside_access_months)


def profile_of(user):
    try:
        return user.staff_profile
    except Exception:  # no profile (RelatedObjectDoesNotExist) or not a real user
        return None


def ends_on(user):
    profile = profile_of(user)
    return profile.access_ends if profile else None


def is_external(user):
    profile = profile_of(user)
    return bool(profile and profile.is_external)


def access_ended(user, today=None):
    """True from the day after the access end date."""
    end = ends_on(user)
    return bool(end and end < (today or date.today()))


def close_ended(today=None):
    """Close the accounts of everyone whose access has ended. Returns how many were closed."""
    from django.contrib.auth import get_user_model

    from . import audit

    today = today or date.today()
    closed = 0
    for user in get_user_model()._default_manager.filter(is_active=True, staff_profile__access_ends__lt=today):
        user.is_active = False
        user.save(update_fields=["is_active"])
        audit._record(user, "update", {"access": [None, f"closed: access ended {user.staff_profile.access_ends:%d %b %Y}"]})
        closed += 1
    return closed


def ending_soon(today=None, days=WARN_DAYS):
    """Active people whose access ends within ``days``, soonest first."""
    from django.contrib.auth import get_user_model

    today = today or date.today()
    return (get_user_model()._default_manager
            .filter(is_active=True, staff_profile__access_ends__gte=today,
                    staff_profile__access_ends__lte=today + timedelta(days=days))
            .select_related("staff_profile").order_by("staff_profile__access_ends"))
