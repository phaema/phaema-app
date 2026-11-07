# SPDX-License-Identifier: AGPL-3.0-or-later
from django import forms
from django.contrib import admin

from .admin_users import PhaemaUserAdmin
from .models import AccessArea, AccountRequest, AuditEntry, Cover, ModuleSettings


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
        ("Letters and notices", {"fields": ["department", "postal_address", "letter_phone", "letter_email",
                                            "website"]}),
        ("Maintenance", {"fields": ["order_approval_limit"]}),
        ("Maps", {"fields": ["os_maps_api_key", "os_map_style"]}),
        ("Security", {"fields": ["two_step_required"]}),
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


class AccessAreaForm(forms.ModelForm):
    modules = forms.MultipleChoiceField(
        choices=AccessArea.MODULES, required=False, widget=forms.CheckboxSelectMultiple,
        help_text="The modules everyone in this area can open in full.")

    class Meta:
        model = AccessArea
        fields = ["name", "code", "description", "modules", "own_patch_finance", "finance_actions", "members", "order"]


@admin.register(AccessArea)
class AccessAreaAdmin(admin.ModelAdmin):
    form = AccessAreaForm
    list_display = ("name", "modules_list", "own_patch_finance", "finance_actions", "member_count")
    filter_horizontal = ("members",)
    prepopulated_fields = {"code": ("name",)}

    @admin.display(description="Modules")
    def modules_list(self, obj):
        return ", ".join(obj.module_names()) or "Core only"

    @admin.display(description="People")
    def member_count(self, obj):
        return obj.members.count()


@admin.register(AccountRequest)
class AccountRequestAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "organisation", "requested_at", "done")
    list_filter = ("done",)
    list_editable = ("done",)
    search_fields = ("name", "email", "organisation")
    readonly_fields = ("requested_at",)
    actions = ["approve_surveyor", "approve_administrator", "approve_viewer"]

    def _approve(self, request, queryset, role):
        from django.contrib import messages

        from .account_requests import approve

        for req in queryset:
            user, created, link, emailed = approve(req, role)
            what = "Created" if created else "Updated"
            if emailed:
                self.message_user(request, f"{what} {user.username} for {req.name} and emailed {req.email} a link "
                                           "to choose a password.", messages.SUCCESS)
            else:
                self.message_user(request, f"{what} {user.username} for {req.name}, but the email to {req.email} "
                                           f"could not be sent. Send them this link to choose a password: {link}",
                                  messages.WARNING)

    @admin.action(description="Approve as surveyor: create the sign-in and email them")
    def approve_surveyor(self, request, queryset):
        from .roles import SURVEYORS

        self._approve(request, queryset, SURVEYORS)

    @admin.action(description="Approve as administrator: create the sign-in and email them")
    def approve_administrator(self, request, queryset):
        from .roles import ADMINISTRATORS

        self._approve(request, queryset, ADMINISTRATORS)

    @admin.action(description="Approve as viewer: create the sign-in and email them")
    def approve_viewer(self, request, queryset):
        from .roles import VIEWERS

        self._approve(request, queryset, VIEWERS)


@admin.register(Cover)
class CoverAdmin(admin.ModelAdmin):
    list_display = ("user", "covered", "starts_on", "ends_on", "reason", "created_by")
    list_filter = ("ends_on",)
    autocomplete_fields = ("user", "covered")

    def save_model(self, request, obj, form, change):
        if not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
