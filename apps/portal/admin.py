# SPDX-License-Identifier: AGPL-3.0-or-later
"""Manage data: tenant portal accounts (added by estates, never by tenants) and contact changes tenants ask for."""
from django.contrib import admin, messages

from apps.core.roles import is_administrator, is_surveyor

from . import emails
from .models import ContactChange, PortalAccount


class _EstatesOnly:
    """Administrators and surveyors: the people who deal with tenants."""

    def _ok(self, request):
        return is_administrator(request.user) or is_surveyor(request.user)

    def has_module_permission(self, request):
        return self._ok(request)

    def has_view_permission(self, request, obj=None):
        return self._ok(request)

    def has_change_permission(self, request, obj=None):
        return self._ok(request)


@admin.register(PortalAccount)
class PortalAccountAdmin(_EstatesOnly, admin.ModelAdmin):
    list_display = ["name", "email", "party", "finance", "facilities", "active", "invited_at", "last_sign_in"]
    list_filter = ["active", "finance", "facilities"]
    search_fields = ["name", "email", "party__name"]
    autocomplete_fields = ["party"]
    fields = ["party", "name", "email", "finance", "facilities", "active", "invited_by", "invited_at",
              "last_sign_in"]
    readonly_fields = ["invited_by", "invited_at", "last_sign_in"]
    actions = ["send_invitations"]

    def has_add_permission(self, request):
        return self._ok(request)

    def has_delete_permission(self, request, obj=None):
        return False  # untick "active" instead, so the change log keeps who had access

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            emails.invite(obj, request.user)
            messages.info(request, f"Invitation sent to {obj.email}.")

    @admin.action(description="Send the invitation email again")
    def send_invitations(self, request, queryset):
        n = 0
        for account in queryset.filter(active=True).select_related("party"):
            emails.invite(account, request.user)
            n += 1
        self.message_user(request, f"{n} invitation(s) sent.")


@admin.register(ContactChange)
class ContactChangeAdmin(_EstatesOnly, admin.ModelAdmin):
    list_display = ["created_at", "lease", "account", "status", "decided_by"]
    list_filter = ["status"]
    search_fields = ["lease__reference", "account__email"]
    actions = ["accept", "decline"]

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Accept the selected changes (updates the agreement's contact for demands)")
    def accept(self, request, queryset):
        n = 0
        for change in queryset.filter(status=ContactChange.Status.WAITING).select_related("lease"):
            change.accept(request.user)
            n += 1
        self.message_user(request, f"{n} change(s) accepted.")

    @admin.action(description="Decline the selected changes")
    def decline(self, request, queryset):
        n = 0
        for change in queryset.filter(status=ContactChange.Status.WAITING):
            change.decline(request.user)
            n += 1
        self.message_user(request, f"{n} change(s) declined.")
