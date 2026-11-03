# SPDX-License-Identifier: AGPL-3.0-or-later
"""PHAEMA's roles applied to the REST API.

Everyone with a role can read. Administrators can create, change and delete anything.
Surveyors can change (not create or delete) records they are allowed to edit on screen.
Viewers cannot change anything.
"""
from rest_framework.permissions import SAFE_METHODS, BasePermission

from .roles import can_edit, has_role, is_administrator


class PhaemaPermission(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated and has_role(user)):
            return False
        if request.method in SAFE_METHODS:
            return True
        if is_administrator(user):
            return True
        if request.method in ("PUT", "PATCH"):
            model = view.get_queryset().model
            return user.has_perm(f"{model._meta.app_label}.change_{model._meta.model_name}")
        return False

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        return can_edit(request.user, obj)
