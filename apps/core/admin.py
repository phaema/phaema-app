# SPDX-License-Identifier: AGPL-3.0-or-later
from django.contrib import admin

from .admin_users import PhaemaUserAdmin
from .models import AuditEntry, ModuleSettings


@admin.register(ModuleSettings)
class ModuleSettingsAdmin(admin.ModelAdmin):
    fieldsets = [
        (None, {"fields": ["organisation_name", "brand_colour"]}),
        ("Modules", {"fields": ["rent_ledger_enabled", "service_charges_enabled", "maintenance_enabled",
                                "compliance_enabled", "golden_thread_enabled", "valuation_enabled",
                                "open_data_enabled"]}),
        ("Rent ledger", {"fields": ["invoicing", "invoice_prefix", "next_invoice_number", "vat_rate",
                                    "rent_income_code", "service_charge_income_code", "vat_code_standard",
                                    "vat_code_exempt"]}),
        ("Maintenance", {"fields": ["order_approval_limit"]}),
        ("Maps", {"fields": ["os_maps_api_key", "os_map_style"]}),
        ("Reminders", {"fields": ["reminder_days_review", "reminder_days_notice", "reminder_days_break",
                                  "reminder_days_expiry", "reminder_days_other", "overdue_reminders"]}),
    ]

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
