# SPDX-License-Identifier: AGPL-3.0-or-later
from django.contrib import admin

from .admin_users import PhaemaUserAdmin
from .models import AuditEntry, ModuleSettings


@admin.register(ModuleSettings)
class ModuleSettingsAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not ModuleSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AuditEntry)
class AuditEntryAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "user", "action", "content_type", "object_repr")
    list_filter = ("action", "content_type")
    search_fields = ("object_repr", "object_id")
    readonly_fields = [f.name for f in AuditEntry._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

__all__ = ["PhaemaUserAdmin", "ModuleSettingsAdmin", "AuditEntryAdmin"]
