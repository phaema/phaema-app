# SPDX-License-Identifier: AGPL-3.0-or-later
from django.contrib import admin

from .models import AssetClass, AuditReview, Classification, IndexPoint, Valuation, ValuationSettings, Valuer


@admin.register(AssetClass)
class AssetClassAdmin(admin.ModelAdmin):
    list_display = ("name", "basis", "alternative_basis", "cycle_years", "depreciated", "active")


@admin.register(ValuationSettings)
class ValuationSettingsAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not ValuationSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Valuer)
class ValuerAdmin(admin.ModelAdmin):
    list_display = ("name", "firm", "status", "user", "rics_number", "registered_valuer", "first_instructed",
                    "active")
    list_filter = ("status", "active")


@admin.register(Classification)
class ClassificationAdmin(admin.ModelAdmin):
    list_display = ("property", "asset_class", "effective_from", "reason")
    list_filter = ("asset_class",)
    autocomplete_fields = ("property",)


@admin.register(Valuation)
class ValuationAdmin(admin.ModelAdmin):
    list_display = ("__str__", "asset_class", "valuer", "value", "status")
    list_filter = ("status", "asset_class")
    search_fields = ("property__reference", "property__name")
    raw_id_fields = ("property", "case")

    def view_on_site(self, obj):
        return obj.get_absolute_url()


@admin.register(AuditReview)
class AuditReviewAdmin(admin.ModelAdmin):
    list_display = ("__str__", "reason", "status", "due_on", "assigned_to", "outcome")
    list_filter = ("status", "accounts_year", "reason")
    raw_id_fields = ("valuation",)

    def view_on_site(self, obj):
        return obj.get_absolute_url()


@admin.register(IndexPoint)
class IndexPointAdmin(admin.ModelAdmin):
    list_display = ("index", "on", "value", "source")
    list_filter = ("index",)
