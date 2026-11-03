# SPDX-License-Identifier: AGPL-3.0-or-later
"""PHAEMA's security model: three roles, set up as Django groups.

Administrators  can view and change everything, manage users, import data and change settings.
Surveyors       can view everything, and change the properties they manage (and those
                properties' photos, leases and boundaries). They can add properties, which
                become theirs, and add leases on their own properties.
Viewers         can view everything and change nothing.

Superusers (created with ./phaema.sh admin) can do everything. A signed-in user who is in
none of these groups can see nothing until an administrator gives them a role.
"""
from django.contrib.auth.models import Group, Permission

ADMINISTRATORS = "Administrators"
SURVEYORS = "Surveyors"
VIEWERS = "Viewers"
ROLES = (ADMINISTRATORS, SURVEYORS, VIEWERS)

PHAEMA_APPS = ("core", "properties", "leases", "ledger", "servicecharges")

# Permissions held by each role, as "app_label.codename". Object-level rules (only your
# own properties) are applied on top of these by can_edit().
SURVEYOR_PERMISSIONS = {
    "properties.add_property", "properties.change_property",
    "properties.add_propertyphoto", "properties.change_propertyphoto", "properties.delete_propertyphoto",
    "leases.add_lease", "leases.change_lease",
    "leases.add_breakoption", "leases.change_breakoption", "leases.delete_breakoption",
    "leases.add_party", "leases.change_party",
    "leases.add_leasedocument", "leases.change_leasedocument", "leases.delete_leasedocument",
    "leases.add_leaseevent", "leases.change_leaseevent",
    "leases.add_rentscheduleentry", "leases.change_rentscheduleentry", "leases.delete_rentscheduleentry",
}
ADMIN_EXTRA = {
    "auth.view_user", "auth.add_user", "auth.change_user",
    "auth.view_group",
}


def _perms(names):
    found = []
    for name in names:
        app, codename = name.split(".")
        found.extend(Permission.objects.filter(content_type__app_label=app, codename=codename))
    return found


def ensure_roles(**kwargs):
    """Create or refresh the three groups and their permissions. Safe to run repeatedly."""
    view_all = Permission.objects.filter(content_type__app_label__in=PHAEMA_APPS, codename__startswith="view_")
    all_phaema = Permission.objects.filter(content_type__app_label__in=PHAEMA_APPS)

    viewers, _ = Group.objects.get_or_create(name=VIEWERS)
    viewers.permissions.set(view_all)

    surveyors, _ = Group.objects.get_or_create(name=SURVEYORS)
    surveyors.permissions.set(list(view_all) + _perms(SURVEYOR_PERMISSIONS))

    admins, _ = Group.objects.get_or_create(name=ADMINISTRATORS)
    admins.permissions.set(list(all_phaema) + _perms(ADMIN_EXTRA))


def _group_names(user):
    if not hasattr(user, "_phaema_groups"):
        user._phaema_groups = set(user.groups.values_list("name", flat=True)) if user.pk else set()
    return user._phaema_groups


def role_of(user):
    """The user's highest role name, or None."""
    if not user.is_authenticated:
        return None
    if user.is_superuser:
        return ADMINISTRATORS
    names = _group_names(user)
    return next((r for r in ROLES if r in names), None)


def is_administrator(user):
    return role_of(user) == ADMINISTRATORS


def is_surveyor(user):
    return role_of(user) == SURVEYORS


def has_role(user):
    return role_of(user) is not None


def manages(user, prop):
    return prop is not None and prop.managing_surveyor_id == user.pk


def can_edit(user, obj):
    """Can this user change this particular record?"""
    role = role_of(user)
    if role == ADMINISTRATORS:
        return True
    if role != SURVEYORS or obj is None:
        return False
    from apps.leases.models import BreakOption, Lease, LeaseDocument, LeaseEvent, Party, RentScheduleEntry
    from apps.properties.models import Property, PropertyPhoto

    if isinstance(obj, Property):
        return manages(user, obj)
    if isinstance(obj, PropertyPhoto):
        return manages(user, obj.property)
    if isinstance(obj, Lease):
        return obj.pk is None or obj.properties.filter(managing_surveyor=user).exists()
    if isinstance(obj, (BreakOption, LeaseDocument, LeaseEvent, RentScheduleEntry)):
        return can_edit(user, obj.lease)
    if isinstance(obj, Party):
        return True  # contact details are shared; changes are in the audit trail
    return False  # titles, documents, INSPIRE parcels and settings are for administrators


def sync_staff_status(user):
    """Administrators and surveyors use 'Manage data' (the admin site), so they need staff status."""
    if user.is_superuser:
        return
    user.__dict__.pop("_phaema_groups", None)
    staff = bool(_group_names(user) & {ADMINISTRATORS, SURVEYORS})
    if user.is_staff != staff:
        user.is_staff = staff
        user.save(update_fields=["is_staff"])


def administrators_only(view):
    """View decorator: signed-in Administrators only."""
    from functools import wraps

    from django.contrib.auth.decorators import login_required
    from django.core.exceptions import PermissionDenied

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not is_administrator(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return login_required(wrapped)
