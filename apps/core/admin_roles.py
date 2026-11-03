# SPDX-License-Identifier: AGPL-3.0-or-later
"""Apply PHAEMA's roles inside 'Manage data' (the Django admin)."""
from apps.core.roles import can_edit, is_administrator


class RoleAdminMixin:
    """Records a user may view but not change open read-only."""

    def has_change_permission(self, request, obj=None):
        return super().has_change_permission(request, obj) and (obj is None or can_edit(request.user, obj))

    def has_delete_permission(self, request, obj=None):
        return super().has_delete_permission(request, obj) and (obj is None or can_edit(request.user, obj))


class RoleInlineMixin:
    """Inline rows (photos, breaks) follow the record they belong to."""

    def _parent_ok(self, request, obj):
        return obj is None or can_edit(request.user, obj)

    def has_add_permission(self, request, obj=None):
        return super().has_add_permission(request, obj) and self._parent_ok(request, obj)

    def has_change_permission(self, request, obj=None):
        return super().has_change_permission(request, obj) and self._parent_ok(request, obj)

    def has_delete_permission(self, request, obj=None):
        return super().has_delete_permission(request, obj) and self._parent_ok(request, obj)


class AdministratorOnlyEditingMixin:
    """List-page bulk editing (e.g. assigning surveyors) is for administrators only."""

    def get_changelist_instance(self, request):
        cl = super().get_changelist_instance(request)
        if not is_administrator(request.user):
            cl.list_editable = ()
        return cl
