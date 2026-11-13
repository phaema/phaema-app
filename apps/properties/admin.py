# SPDX-License-Identifier: AGPL-3.0-or-later
from decimal import Decimal

from django import forms
from django.contrib.gis import admin
from django.core.exceptions import ValidationError

from apps.core.admin_roles import AdministratorOnlyEditingMixin, RoleAdminMixin, RoleInlineMixin
from apps.core.roles import is_administrator

from .models import (InspireParcel, Portfolio, Property, PropertyCost, PropertyPhoto, PropertyPlan, PropertyUse,
                     Title, TitleDocument)


class TitleInline(admin.TabularInline):
    model = Title.properties.through
    extra = 0
    verbose_name = "title"
    verbose_name_plural = "titles"


class PhotoInline(RoleInlineMixin, admin.TabularInline):
    model = PropertyPhoto
    extra = 1
    fields = ("image", "caption", "taken_on", "is_main", "order")


class PlanInline(RoleInlineMixin, admin.TabularInline):
    model = PropertyPlan
    extra = 1
    fields = ("title", "file", "drawn_on", "notes")


class CostInline(RoleInlineMixin, admin.TabularInline):
    model = PropertyCost
    extra = 1
    fields = ("year_starting", "running_cost", "rates", "notes")


class PropertyForm(forms.ModelForm):
    """Lets the site area be typed in square metres as well as hectares."""

    site_area_sqm = forms.DecimalField(
        label="Site area (m²)", required=False, min_value=0, max_digits=14, decimal_places=2,
        help_text="Fill in either this or hectares: PHAEMA works out the other. 1 hectare is 10,000 m².")

    class Meta:
        model = Property
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.site_area_ha is not None and "site_area_sqm" in self.fields:
            self.fields["site_area_sqm"].initial = self.instance.site_area_sqm

    def clean(self):
        data = super().clean()
        sqm, ha = data.get("site_area_sqm"), data.get("site_area_ha")
        sqm_changed, ha_changed = "site_area_sqm" in self.changed_data, "site_area_ha" in self.changed_data
        if sqm_changed and sqm is not None:
            from_sqm = (sqm / 10000).quantize(Decimal("0.0001"))
            if ha_changed and ha is not None and ha != from_sqm:
                self.add_error("site_area_sqm", "This does not match the hectares entered. Fill in one or the other.")
            else:
                data["site_area_ha"] = self.instance.site_area_ha = from_sqm
        elif sqm_changed and sqm is None and not ha_changed:
            data["site_area_ha"] = self.instance.site_area_ha = None
        return data


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


@admin.register(PropertyUse)
class PropertyUseAdmin(admin.ModelAdmin):
    """The council's own list of property uses, each matched to a Government Property Data Standard term."""

    list_display = ("name", "standard_usage", "active", "order", "property_count")
    list_editable = ("standard_usage", "active", "order")
    search_fields = ("name", "standard_usage")

    def get_queryset(self, request):
        from django.db.models import Count

        return super().get_queryset(request).annotate(_count=Count("properties"))

    @admin.display(description="Properties", ordering="_count")
    def property_count(self, obj):
        return obj._count

    def has_delete_permission(self, request, obj=None):
        return super().has_delete_permission(request, obj) and (obj is None or not obj.properties.exists())


@admin.register(Property)
class PropertyAdmin(AdministratorOnlyEditingMixin, RoleAdminMixin, admin.GISModelAdmin):
    list_display = ("reference", "name", "property_type", "holding_purpose", "occupation", "managing_surveyor", "postcode")
    list_editable = ("managing_surveyor",)  # assign surveyors to many properties at once
    list_filter = ("property_type", "holding_purpose", "portfolio", "tenure", "occupation", "managing_surveyor")
    search_fields = ("reference", "name", "uprn", "address_line_1", "town", "postcode")
    autocomplete_fields = ("parent",)
    form = PropertyForm
    inlines = [CostInline, PhotoInline, PlanInline, TitleInline]
    gis_widget_kwargs = {"attrs": {"default_lon": -1.5, "default_lat": 52.5, "default_zoom": 6}}
    fieldsets = (
        (None, {"fields": ("reference", "name", "property_type", "parent", "managing_surveyor")}),
        ("Identifiers and address", {"fields": ("uprn", "usrn", "address_line_1", "address_line_2", "town", "postcode")}),
        ("Classification", {"fields": ("holding_purpose", "strategy_section", "purpose_review_date", "portfolio",
                                       "tenure", "acquired_on", "occupation", "use_type", "use_description",
                                       "use_class")}),
        ("Designations", {
            "fields": ("listed_building", "scheduled_monument", "sssi", "conservation_area", "designation_notes"),
            "description": "Leave blank where it is not known. Choose Not listed or No where it has been checked."}),
        ("Vacancy", {
            "fields": ("vacant_since", "vacancy_status", "available_from", "available_until"),
            "description": "For a property whose occupation status is Vacant. These are cleared when it is "
                           "occupied again."}),
        ("Areas", {"fields": ("gia_sqm", "nia_sqm", "gea_sqm", "site_area_ha", "site_area_sqm", "area_standard",
                              "area_source", "areas_measured_on")}),
        ("Site and buildings", {
            "fields": ("location_description", "building_description", "built", "built_year", "condition_grade",
                       "condition_surveyed_on", "construction_type",
                       "construction_detail", "storeys", "basement_levels", "roof_type", "roof_covering",
                       "roof_detail", "window_type", "window_detail", "parking", "parking_spaces"),
            "description": "What the property physically is. Record the site as a whole on the site, and each "
                           "building (block) on its own record. Leave blank anything not known. Floor plans are "
                           "added further down the page."}),
        ("Services", {"fields": ("mains_gas", "electricity", "mains_water", "drainage", "services_notes",
                                 "solar_pv", "solar_capacity_kwp")}),
        ("Location", {"fields": ("easting", "northing", "boundary", "boundary_source")}),
        ("Disposal", {"fields": ("disposal_reason", "disposal_method", "disposal_expected_on",
                                 "disposal_expected_value", "disposed_on", "disposal_price"),
                      "description": "Fill in the reason, method and expected date and value once a disposal is "
                                     "planned. Fill in the last two when the sale or long lease completes: the "
                                     "property then leaves open data."}),
        ("Other", {"fields": ("site_hazards", "exclude_from_publication", "notes")}),
    )

    def get_readonly_fields(self, request, obj=None):
        # Only administrators assign surveyors; a surveyor's new properties are their own.
        return () if is_administrator(request.user) else ("managing_surveyor",)

    def get_form(self, request, obj=None, **kwargs):
        from django.db.models import Q

        form = super().get_form(request, obj, **kwargs)
        # Only lists entries still in use, plus whatever this property already has.
        for name, model in (("portfolio", Portfolio), ("use_type", PropertyUse)):
            field = form.base_fields.get(name)
            if field is not None:
                field.queryset = model.objects.filter(Q(active=True) | Q(pk=getattr(obj, f"{name}_id", None)))
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
