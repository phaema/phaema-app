# SPDX-License-Identifier: AGPL-3.0-or-later
from django.conf import settings
from django.db import DatabaseError

from .models import ModuleSettings
from .views import TEXT_SIZES


def phaema(request):
    try:
        modules = ModuleSettings.load()
        org = modules.organisation_name or settings.PHAEMA_ORGANISATION_NAME
    except DatabaseError:  # e.g. before the first migration has run
        modules, org = None, settings.PHAEMA_ORGANISATION_NAME
    size = request.COOKIES.get("phaema_text_size", "standard")
    from .roles import ADMINISTRATORS, role_of

    role = role_of(request.user) if hasattr(request, "user") else None
    return {
        "role": role,
        "is_administrator": role == ADMINISTRATORS,
        "modules": modules,
        "organisation_name": org,
        "text_size": size if size in TEXT_SIZES else "standard",
        "text_sizes": TEXT_SIZES,
    }
