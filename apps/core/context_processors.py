# SPDX-License-Identifier: AGPL-3.0-or-later
from django.conf import settings
from django.db import DatabaseError

from .models import ModuleSettings


def phaema(request):
    try:
        modules = ModuleSettings.load()
        org = modules.organisation_name or settings.PHAEMA_ORGANISATION_NAME
    except DatabaseError:  # e.g. before the first migration has run
        modules, org = None, settings.PHAEMA_ORGANISATION_NAME
    return {"modules": modules, "organisation_name": org}
