# SPDX-License-Identifier: AGPL-3.0-or-later
from django.contrib.gis import admin

from .models import Property, PropertyPhoto, Title, TitleDocument


class TitleInline(admin.TabularInline):
    model = Title.properties.through
    extra = 0
    verbose_name = "title"
    verbose_name_plural = "titles"


class PhotoInline(admin.TabularInline):
    model = PropertyPhoto
    extra = 1
    fields = ("image", "caption", "taken_on", "is_main", "order")


@admin.register(Property)
class PropertyAdmin(admin.GISModelAdmin):
    list_display = ("reference", "name", "property_type", "holding_purpose", "occupation", "managing_surveyor", "postcode")
    list_editable = ("managing_surveyor",)  # assign surveyors to many properties at once
    list_filter = ("property_type", "holding_purpose", "tenure", "occupation", "managing_surveyor")
    search_fields = ("reference", "name", "uprn", "address_line_1", "town", "postcode")
    autocomplete_fields = ("parent",)
    inlines = [PhotoInline, TitleInline]
    gis_widget_kwargs = {"attrs": {"default_lon": -1.5, "default_lat": 52.5, "default_zoom": 6}}
    fieldsets = (
        (None, {"fields": ("reference", "name", "property_type", "parent", "managing_surveyor")}),
        ("Identifiers and address", {"fields": ("uprn", "usrn", "address_line_1", "address_line_2", "town", "postcode")}),
        ("Classification", {"fields": ("holding_purpose", "tenure", "occupation", "use_description", "use_class")}),
        ("Areas", {"fields": ("gia_sqm", "nia_sqm", "site_area_ha")}),
        ("Location", {"fields": ("easting", "northing", "boundary")}),
        ("Other", {"fields": ("exclude_from_publication", "notes")}),
    )


class DocumentInline(admin.TabularInline):
    model = TitleDocument
    extra = 1
    fields = ("document_type", "file", "description", "document_date")


@admin.register(Title)
class TitleAdmin(admin.ModelAdmin):
    list_display = ("__str__", "tenure", "title_class", "deeds_location")
    list_filter = ("tenure", "title_class")
    search_fields = ("title_number", "properties__reference", "properties__name")
    filter_horizontal = ("properties",)
    inlines = [DocumentInline]
