# SPDX-License-Identifier: AGPL-3.0-or-later
from django.conf import settings
from django.db import DatabaseError
from django.utils.translation import gettext as gettext_now
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop

from .models import ModuleSettings
from .views import SKINS, TEXT_SIZES, THEMES

# How each role is shown beside the person's name in the header.
ROLE_LABELS = {"Administrators": _("administrator"), "Surveyors": _("surveyor"), "Contributors": _("contributor"),
               "Viewers": _("viewer")}

# Words the page scripts show, translated on the server and read by static/js from the page (see base.html).
SCRIPT_TEXT = [
    gettext_noop("Hide"), gettext_noop("Show"), gettext_noop("Hide all"), gettext_noop("Show all"),
    gettext_noop("Background map"), gettext_noop("Not found"), gettext_noop("Photo %(n)s of %(total)s"),
    gettext_noop("%(n)s of %(total)s"),
]


def phaema(request):
    try:
        modules = ModuleSettings.load()
        org = modules.organisation_name or settings.PHAEMA_ORGANISATION_NAME
    except DatabaseError:  # e.g. before the first migration has run
        modules, org = None, settings.PHAEMA_ORGANISATION_NAME
    size = request.COOKIES.get("phaema_text_size", "standard")
    from .roles import ADMINISTRATORS, role_of

    role = role_of(request.user) if hasattr(request, "user") else None
    from .access import ModulesForUser, can_do_finance

    user = getattr(request, "user", None)
    return {
        "role": role,
        "is_administrator": role == ADMINISTRATORS,
        "can_finance": bool(user is not None and can_do_finance(user)),
        "can_arrange_cover": _lazy_cover(user),
        # Each *_enabled flag is true only if the council has the module on AND this person can open it.
        "modules": ModulesForUser(modules, user) if modules is not None and user is not None else modules,
        "organisation_name": org,
        "text_size": size if size in TEXT_SIZES else "standard",
        "text_sizes": TEXT_SIZES,
        "theme": request.COOKIES.get("phaema_theme") if request.COOKIES.get("phaema_theme") in THEMES else "standard",
        "themes": THEMES,
        "skin": request.COOKIES.get("phaema_skin") if request.COOKIES.get("phaema_skin") in SKINS else "classic",
        "skins": SKINS,
        "brand_colour": getattr(modules, "brand_colour", "") if modules else "",
        "welsh_offered": bool(getattr(modules, "welsh_enabled", False)),
        "role_label": ROLE_LABELS.get(role, ""),
        "script_text": {key: gettext_now(key) for key in SCRIPT_TEXT},
        "demo_site": settings.PHAEMA_DEMO_SITE,
        "demo_reset_hours": settings.PHAEMA_DEMO_RESET_HOURS,
        "access_ends_soon": _ends_soon(user),
        "occupier_contact": _lazy_contact(user) if role is None else False,
    }


def _ends_soon(user):
    """The access end date if it is within the warning period, for a banner."""
    if user is None or not user.is_authenticated:
        return None
    from datetime import date, timedelta

    from .outside import WARN_DAYS, ends_on

    end = ends_on(user)
    if end and date.today() <= end <= date.today() + timedelta(days=WARN_DAYS):
        return end
    return None


class _lazy_contact:
    """True if this person is an occupier contact (no role, named on an occupier); worked out when a template asks."""

    def __init__(self, user):
        self.user = user

    def __bool__(self):
        from apps.space import liaison

        return bool(self.user is not None and liaison.is_contact(self.user))


class _lazy_cover:
    """True if this person may arrange cover; worked out only when a template asks."""

    def __init__(self, user):
        self.user = user

    def __bool__(self):
        from .cover_views import can_arrange

        return bool(self.user is not None and can_arrange(self.user))
