# SPDX-License-Identifier: AGPL-3.0-or-later
from django import forms
from django.contrib import admin

from .admin_users import PhaemaUserAdmin
from .models import AccessArea, AccountRequest, ApiToken, AuditEntry, Cover, ModuleSettings, OutgoingEmail, TextCopy


@admin.register(ModuleSettings)
class ModuleSettingsAdmin(admin.ModelAdmin):
    fieldsets = [
        (None, {"fields": ["organisation_name", "brand_colour"]}),
        ("Modules", {"fields": ["rent_ledger_enabled", "service_charges_enabled", "maintenance_enabled",
                                "compliance_enabled", "golden_thread_enabled", "valuation_enabled",
                                "space_enabled", "space_costing_enabled", "open_data_enabled"]}),
        ("Tenant portal", {"fields": ["tenant_portal_enabled", "portal_welcome"]}),
        ("Contractor portal", {"fields": ["contractor_portal_enabled"]}),
        ("Rent ledger", {"fields": ["invoicing", "invoice_prefix", "next_invoice_number", "vat_rate",
                                    "rent_income_code", "service_charge_income_code", "vat_code_standard",
                                    "vat_code_exempt"]}),
        ("Letters and notices", {"fields": ["department", "postal_address", "letter_phone", "letter_email",
                                            "website", "email_demands", "payment_link"]}),
        ("Maintenance", {"fields": ["order_approval_limit"]}),
        ("Maps", {"fields": ["os_maps_api_key", "os_map_style"]}),
        ("Floor areas", {"fields": ["area_basis"]}),
        ("Language", {"fields": ["welsh_enabled"],
                      "description": "Welsh Language Standards: councils in Wales provide Welsh interfaces for "
                                     "software where one exists."}),
        ("Scanned documents", {"fields": ["ocr_enabled"],
                               "description": "Progress is under Manage data, Scanned documents."}),
        ("Estate strategy", {"fields": ["strategy_review_years"],
                             "description": "The lists of holding purpose sub-categories and asset strategies are "
                                            "in Manage data."}),
        ("Security", {"fields": ["two_step_required", "outside_access_months"]}),
        ("Single sign-on", {"fields": ["sso_enabled", "sso_passwords", "sso_create_accounts"],
                            "description": "Sign in with Microsoft 365 or another sign-in service. See Help, "
                                           "Users and roles. Roles and access areas can follow the service's "
                                           "groups: add them under Sign-in group mappings."}),
        ("Reminders", {"fields": ["reminder_days_review", "reminder_days_notice", "reminder_days_break",
                                  "reminder_days_expiry", "reminder_days_option", "reminder_days_other", "overdue_reminders"]}),
    ]

    def has_add_permission(self, request):
        return not ModuleSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AuditEntry)
class AuditEntryAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "user", "action", "content_type", "object_repr", "via")
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


@admin.register(TextCopy)
class TextCopyAdmin(admin.ModelAdmin):
    """Which scanned PDFs have had their text recognised. Read only, apart from asking for one to be read again."""

    list_display = ["__str__", "status", "pages", "pages_scanned", "characters", "poor", "finished_at"]
    list_filter = ["status", "poor"]
    search_fields = ["source"]
    readonly_fields = ["source", "status", "copy", "pages", "pages_scanned", "characters", "poor", "error",
                       "attempts", "queued_at", "finished_at"]
    actions = ["read_again"]

    def has_add_permission(self, request):
        return False

    def changelist_view(self, request, extra_context=None):
        from django.contrib import messages

        from . import ocr

        reason = ocr.missing()
        if reason:
            messages.warning(request, f"Scanned PDFs are not being read on this server: {reason} "
                                      "See the technical manual, Scanned documents.")
        elif not ocr.enabled():
            messages.info(request, "Recognising text in scanned PDFs is switched off in Module settings.")
        return super().changelist_view(request, extra_context)

    @admin.action(description="Read the selected documents again", permissions=["change"])
    def read_again(self, request, queryset):
        count = queryset.update(status=TextCopy.Status.WAITING, attempts=0, error="")
        self.message_user(request, f"{count} documents will be read again within a few minutes.")


class ApiTokenForm(forms.ModelForm):
    resources = forms.MultipleChoiceField(
        label="Parts of the API", choices=ApiToken.RESOURCES, required=False, widget=forms.CheckboxSelectMultiple,
        help_text="Tick only what the other system needs. Leave all unticked for every part.")

    class Meta:
        model = ApiToken
        fields = ["name", "user", "access", "resources", "expires_on"]

    def __init__(self, *args, **kwargs):
        from datetime import date, timedelta

        from django.contrib.auth import get_user_model

        from .roles import ROLES

        super().__init__(*args, **kwargs)
        if "user" in self.fields:
            self.fields["user"].queryset = (get_user_model()._default_manager
                                            .filter(is_active=True, groups__name__in=ROLES).distinct()
                                            .order_by("username"))
        if "expires_on" in self.fields and not self.initial.get("expires_on"):
            self.initial["expires_on"] = date.today() + timedelta(days=365)

    def clean_expires_on(self):
        from datetime import date, timedelta

        value = self.cleaned_data["expires_on"]
        today = date.today()
        if value < today:
            raise forms.ValidationError("The end date must be today or later.")
        if value > today + timedelta(days=ApiToken.MAX_DAYS):
            raise forms.ValidationError("A token can last at most two years. Make a new one when it ends.")
        return value


@admin.register(ApiToken)
class ApiTokenAdmin(admin.ModelAdmin):
    """Administrators only: tokens are made here, shown once, and cancelled rather than deleted."""

    form = ApiTokenForm
    list_display = ("name", "prefix_shown", "user", "access", "parts", "expires_on", "last_used_at", "state")
    list_filter = ("access",)
    search_fields = ("name", "prefix", "user__username")
    actions = ["cancel_tokens"]

    def _admin(self, request):
        from .roles import is_administrator

        return is_administrator(request.user)

    def has_module_permission(self, request):
        return self._admin(request)

    def has_view_permission(self, request, obj=None):
        return self._admin(request)

    def has_add_permission(self, request):
        return self._admin(request)

    def has_change_permission(self, request, obj=None):
        return self._admin(request)

    def has_delete_permission(self, request, obj=None):
        return False  # cancelled tokens stay listed, so the change log can be traced back

    def get_fields(self, request, obj=None):
        if obj is None:
            return ["name", "user", "access", "resources", "expires_on"]
        return ["name", "prefix_shown", "user", "access", "parts", "expires_on", "created_at", "created_by",
                "last_used_at", "last_used_from", "state", "revoked_by"]

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return []
        return [f for f in self.get_fields(request, obj) if f != "name"]

    @admin.display(description="Key starts")
    def prefix_shown(self, obj):
        return f"{obj.prefix}…"

    @admin.display(description="Parts of the API")
    def parts(self, obj):
        labels = dict(ApiToken.RESOURCES)
        return ", ".join(str(labels.get(r, r)) for r in obj.resources) or "All"

    @admin.display(description="State")
    def state(self, obj):
        if obj.revoked_at:
            return f"Cancelled {obj.revoked_at:%d %b %Y}"
        return "Working" if obj.is_live() else "Ended"

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        context.update(show_save_and_add_another=False, show_save_and_continue=False)  # the key page comes next
        return super().render_change_form(request, context, add, change, form_url, obj)

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
            request._phaema_api_key = obj.issue()
        super().save_model(request, obj, form, change)

    def response_add(self, request, obj, post_url_continue=None):
        from django.template.response import TemplateResponse

        key = getattr(request, "_phaema_api_key", None)
        if not key:
            return super().response_add(request, obj, post_url_continue)
        context = {**self.admin_site.each_context(request), "token": obj, "key": key, "parts": self.parts(obj),
                   "title": "API token made", "opts": self.model._meta}
        response = TemplateResponse(request, "admin/core/apitoken/issued.html", context)
        response["Cache-Control"] = "no-store"
        return response

    @admin.action(description="Cancel the selected tokens")
    def cancel_tokens(self, request, queryset):
        from django.utils import timezone

        count = 0
        for token in queryset.filter(revoked_at__isnull=True):
            token.revoked_at = timezone.now()
            token.revoked_by = request.user
            token.save(update_fields=["revoked_at", "revoked_by"])
            count += 1
        self.message_user(request, f"{count} token{'s' if count != 1 else ''} cancelled. They stop working at once.")


@admin.register(OutgoingEmail)
class OutgoingEmailAdmin(admin.ModelAdmin):
    """Every email to a tenant, kept as a record: it cannot be changed or deleted here."""
    list_display = ["created_at", "kind", "to", "subject", "status"]
    list_filter = ["status", "kind"]
    search_fields = ["to", "subject", "lease__reference"]
    date_hierarchy = "created_at"

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.method in ("GET", "HEAD") and super().has_view_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False
