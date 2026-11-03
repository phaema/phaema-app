# SPDX-License-Identifier: AGPL-3.0-or-later
from django.contrib import admin

from apps.core.admin_roles import RoleAdminMixin

from .models import Action, BuildingDocument, BuildingSafety, Certificate, ComplianceType, Requirement


@admin.register(ComplianceType)
class ComplianceTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "valid_months", "statutory", "regulation", "active")
    list_filter = ("statutory", "active")
    search_fields = ("name", "code")


class CertificateInline(admin.TabularInline):
    model = Certificate
    extra = 0
    fields = ("issued_on", "expires_on", "result", "rating", "carried_out_by", "reference", "file")


@admin.register(Requirement)
class RequirementAdmin(RoleAdminMixin, admin.ModelAdmin):
    list_display = ("kind", "property", "responsible", "active")
    list_filter = ("kind", "responsible", "active")
    search_fields = ("property__reference", "property__name")
    autocomplete_fields = ("property",)
    inlines = [CertificateInline]

    def view_on_site(self, obj):
        return obj.get_absolute_url()


@admin.register(Certificate)
class CertificateAdmin(RoleAdminMixin, admin.ModelAdmin):
    list_display = ("__str__", "requirement", "issued_on", "expires_on", "result")
    list_filter = ("requirement__kind", "result")
    search_fields = ("requirement__property__reference", "reference")
    raw_id_fields = ("requirement", "job")


@admin.register(Action)
class ActionAdmin(RoleAdminMixin, admin.ModelAdmin):
    list_display = ("description", "priority", "due_on", "done_on")
    list_filter = ("priority",)
    raw_id_fields = ("certificate", "job")


@admin.register(BuildingSafety)
class BuildingSafetyAdmin(RoleAdminMixin, admin.ModelAdmin):
    list_display = ("property", "country", "height_m", "storeys", "residential_units", "tier", "confirmed_on")
    list_filter = ("tier", "country")
    autocomplete_fields = ("property",)


@admin.register(BuildingDocument)
class BuildingDocumentAdmin(RoleAdminMixin, admin.ModelAdmin):
    list_display = ("title", "property", "category", "document_date")
    list_filter = ("category",)
    search_fields = ("title", "property__reference")
    autocomplete_fields = ("property",)

    def has_delete_permission(self, request, obj=None):
        return False  # building information is kept for the life of the building
