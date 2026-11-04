# SPDX-License-Identifier: AGPL-3.0-or-later
"""Access areas: which optional modules each person can open, and the surveyor's patch.

A module must be switched on for the council (Module settings) AND opened for the person by one of their access
areas. Administrators can open everything that is switched on. Core PHAEMA is open to everyone with a role.

Scopes returned by scope():
    "full"   the whole module
    "patch"  rent ledger and service charges only, limited to the person's patch (see patch_people)
    None     no access
"""
from datetime import date
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render

from .roles import ADMINISTRATORS, SURVEYORS, role_of

FLAGS = {"ledger": "rent_ledger_enabled", "servicecharges": "service_charges_enabled",
         "maintenance": "maintenance_enabled", "compliance": "compliance_enabled",
         "valuations": "valuation_enabled"}
PATCH_MODULES = ("ledger", "servicecharges")


def _settings():
    from .models import ModuleSettings

    return ModuleSettings.load()


def areas(user):
    if not getattr(user, "is_authenticated", False):
        return []
    if not hasattr(user, "_phaema_areas"):
        user._phaema_areas = list(user.access_areas.all()) if user.pk else []
    return user._phaema_areas


def switched_on(module, settings=None):
    return bool(getattr(settings or _settings(), FLAGS[module]))


def scope(user, module, settings=None):
    """How much of a module this person can see: "full", "patch" or None."""
    if not switched_on(module, settings):
        return None
    role = role_of(user)
    if role is None:
        return None
    if role == ADMINISTRATORS:
        return "full"
    mine = areas(user)
    if any(module in (a.modules or []) for a in mine):
        return "full"
    if module in PATCH_MODULES and any(a.own_patch_finance for a in mine):
        return "patch"
    return None


def can_use(user, module, settings=None):
    return scope(user, module, settings) is not None


def can_do_finance(user):
    """Raise rent, issue credit notes, create finance exports, approve service charge budgets, import receipts."""
    role = role_of(user)
    if role == ADMINISTRATORS:
        return True
    return role == SURVEYORS and any(a.finance_actions for a in areas(user))


# ------------------------------------------------------------------ the patch

def chain(user):
    """Everyone below this person in the supervision chain (supervisees, their supervisees, and so on)."""
    from .models import StaffProfile

    found, frontier = set(), {user.pk}
    while frontier:
        below = set(StaffProfile.objects.filter(supervisor_id__in=frontier).values_list("user_id", flat=True))
        frontier = below - found - {user.pk}
        found |= frontier
    return found


def covering(user, today=None):
    """People this person is covering for today."""
    from .models import Cover

    today = today or date.today()
    return set(Cover.objects.filter(user=user, starts_on__lte=today, ends_on__gte=today)
               .values_list("covered_id", flat=True))


def patch_people(user, today=None):
    """Whose properties count as this person's patch: themselves, their whole chain, anyone they are covering for
    and that person's chain."""
    if not getattr(user, "pk", None):
        return set()
    people = {user.pk} | chain(user)
    from django.contrib.auth import get_user_model

    User = get_user_model()
    for pk in covering(user, today):
        people.add(pk)
        people |= chain(User(pk=pk))
    return people


def patch_property_ids(user, today=None):
    """Properties in the patch, with every part of them (a surveyor who manages an estate manages its units)."""
    from apps.properties.models import Property

    ids = set()
    for prop in Property.objects.filter(managing_surveyor_id__in=patch_people(user, today)):
        ids.add(prop.pk)
        ids.update(prop._descendant_ids())
    return ids


def lease_filter(user, prefix="", today=None):
    """A Q that keeps leases (or records with a lease, via prefix such as "lease__") in the person's patch.
    A lease over several premises is in the patch if any of them is."""
    return Q(**{f"{prefix}properties__in": patch_property_ids(user, today)})


def lease_in_patch(user, lease, today=None):
    from apps.leases.models import Lease

    return Lease.objects.filter(pk=lease.pk).filter(lease_filter(user, today=today)).exists()


# ------------------------------------------------------------------ guarding a module's pages

def module_view(module, off_template):
    """Decorator for every page of an optional module: signed in, switched on for the council, and opened for
    this person by an access area. The view finds the scope in request.access_scope."""
    def decorate(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            settings = _settings()
            if not switched_on(module, settings):
                return render(request, off_template, status=404)
            found = scope(request.user, module, settings)
            if found is None:
                return render(request, "core/no_module.html", {"module": dict(_labels())[module]}, status=403)
            request.access_scope = found
            return view(request, *args, **kwargs)

        return login_required(wrapped)

    return decorate


def _labels():
    from .models import AccessArea

    return AccessArea.MODULES


class ModulesForUser:
    """What templates see as `modules`: the council's settings, with each *_enabled flag also requiring that this
    person can open the module. Every other setting passes straight through."""

    def __init__(self, settings, user):
        self._settings = settings
        self._user = user

    def __getattr__(self, name):
        value = getattr(self._settings, name)
        for module, flag in FLAGS.items():
            if name == flag:
                return bool(value) and can_use(self._user, module, self._settings)
        return value


def finance_only(view):
    """View decorator: Administrators, or Surveyors in an access area with finance actions."""
    from django.core.exceptions import PermissionDenied

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not can_do_finance(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return login_required(wrapped)


def require_full(request):
    """Inside a module page: refuse people who only see their own patch (for example the finance exports)."""
    from django.core.exceptions import PermissionDenied

    if getattr(request, "access_scope", "full") != "full":
        raise PermissionDenied


def patch_leases(user, today=None):
    from apps.leases.models import Lease

    return Lease.objects.filter(lease_filter(user, today=today)).distinct()
