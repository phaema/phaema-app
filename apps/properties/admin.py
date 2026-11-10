# SPDX-License-Identifier: AGPL-3.0-or-later
from django.contrib.gis import admin
from django.core.exceptions import ValidationError

from apps.core.admin_roles import AdministratorOnlyEditingMixin, RoleAdminMixin, RoleInlineMixin
from apps.core.roles import is_administrator

from .models import InspireParcel, Portfolio, Property, PropertyPhoto, Title, TitleDocument


class TitleInline(admin.TabularInline):
    model = Title.properties.through
    extra = 0
    verbose_name = "title"
    verbose_name_plural = "titles"


class PhotoInline(RoleInlineMixin, admin.TabularInline):
    model = PropertyPhoto
    extra = 1
    fields = ("image", "caption", "taken_on", "is_main", "order")


@admin.register(Portfolio)
class PortfolioAdmin(admin.ModelAdmin):
    """Each council's own list of portfolios (Investment, Leisure, Adult social care and so on)."""

    list_display = ("name", "description", "active", "order", "property_count")
    list_editable = ("active", "order")
    search_fields = ("name", "description")

    def get_queryset(self, request):
        from django.db.models import Count

        return super().get_queryset(request).annotate(_count=Count("properties"))

    @admin.display(description="Properties", ordering="_count")
    def property_count(self, obj):
        return obj._count

    def has_delete_permission(self, request, obj=None):
        # A portfolio with properties in it cannot be deleted (untick "in use" instead).
        return super().has_delete_permission(request, obj) and (obj is None or not obj.properties.exists())


@admin.register(Property)
class PropertyAdmin(AdministratorOnlyEditingMixin, RoleAdminMixin, admin.GISModelAdmin):
    list_display = ("reference", "name", "property_type", "holding_purpose", "occupation", "managing_surveyor", "postcode")
    list_editable = ("managing_surveyor",)  # assign surveyors to many properties at once
    list_filter = ("property_type", "holding_purpose", "portfolio", "tenure", "occupation", "managing_surveyor")
    search_fields = ("reference", "name", "uprn", "address_line_1", "town", "postcode")
    autocomplete_fields = ("parent",)
    inlines = [PhotoInline, TitleInline]
    gis_widget_kwargs = {"attrs": {"default_lon": -1.5, "default_lat": 52.5, "default_zoom": 6}}
    fieldsets = (
        (None, {"fields": ("reference", "name", "property_type", "parent", "managing_surveyor")}),
        ("Identifiers and address", {"fields": ("uprn", "usrn", "address_line_1", "address_line_2", "town", "postcode")}),
        ("Classification", {"fields": ("holding_purpose", "strategy_section", "purpose_review_date", "portfolio",
                                       "tenure", "occupation", "use_description", "use_class")}),
        ("Areas", {"fields": ("gia_sqm", "nia_sqm", "gea_sqm", "site_area_ha", "area_standard", "area_source",
                              "areas_measured_on")}),
        ("Location", {"fields": ("easting", "northing", "boundary", "boundary_source")}),
        ("Disposal", {"fields": ("disposed_on", "disposal_price"),
                      "description": "When the property is sold or let on a long lease. It then leaves open data."}),
        ("Other", {"fields": ("site_hazards", "exclude_from_publication", "notes")}),
    )

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        field = form.base_fields.get("portfolio")
        if field is not None:
            from django.db.models import Q

            field.queryset = Portfolio.objects.filter(Q(active=True) | Q(pk=getattr(obj, "portfolio_id", None)))
        return form

    def get_readonly_fields(self, request, obj=None):
        # Only administrators assign surveyors; a surveyor's new properties are their own.
        return () if is_administrator(request.user) else ("managing_surveyor",)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if is_administrator(request.user):
            return form
        user = request.user

        class SurveyorPropertyForm(form):
            def clean_parent(self):
                parent = self.cleaned_data.get("parent")
                if parent and parent.managing_surveyor_id != user.pk:
                    raise ValidationError("You can only add parts to properties you manage.")
                return parent

        return SurveyorPropertyForm

    def save_model(self, request, obj, form, change):
        if not change and not is_administrator(request.user):
            obj.managing_surveyor = request.user
        super().save_model(request, obj, form, change)


class DocumentInline(RoleInlineMixin, admin.TabularInline):
    model = TitleDocument
    extra = 1
    fields = ("document_type", "file", "description", "document_date")


@admin.register(Title)
class TitleAdmin(RoleAdminMixin, admin.ModelAdmin):
    list_display = ("__str__", "tenure", "title_class", "deeds_location")
    list_filter = ("tenure", "title_class")
    search_fields = ("title_number", "properties__reference", "properties__name")
    filter_horizontal = ("properties",)
    inlines = [DocumentInline]


@admin.register(InspireParcel)
class InspireParcelAdmin(admin.GISModelAdmin):
    list_display = ("inspire_id", "source_file", "imported_at")
    search_fields = ("inspire_id",)
    readonly_fields = ("inspire_id", "source_file", "imported_at", "valid_from")
    gis_widget_kwargs = {"attrs": {"default_lon": -1.5, "default_lat": 52.5, "default_zoom": 6}}

    def has_add_permission(self, request):
        return False  # import from HM Land Registry files instead
