# SPDX-License-Identifier: AGPL-3.0-or-later
from django.contrib import admin

from apps.core.admin_roles import RoleAdminMixin

from .models import (BUILDING_TYPES, BuildingCost, CostLine, CostSharing, FixedShare, Headcount, Occupation,
                     Occupier, Space, UseFigure, UseMeasure)


class _BuildingChoices:
    """Only buildings, units and sites can hold spaces."""

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        from apps.properties.models import Property

        if db_field.name == "building":
            kwargs["queryset"] = Property.objects.filter(property_type__in=BUILDING_TYPES).order_by("reference")
        if db_field.name == "occupier":
            kwargs["queryset"] = Occupier.objects.filter(active=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        if "building" in request.GET:
            initial["building"] = request.GET["building"]
        return initial

    def response_add(self, request, obj, post_url_continue=None):
        if "_addanother" not in request.POST and "_continue" not in request.POST:
            return _back_to_building(obj)
        return super().response_add(request, obj, post_url_continue)

    def response_change(self, request, obj):
        if "_addanother" not in request.POST and "_continue" not in request.POST:
            return _back_to_building(obj)
        return super().response_change(request, obj)


def _back_to_building(obj):
    from django.shortcuts import redirect

    return redirect("space:building", obj.building_id)


@admin.register(Occupier)
class OccupierAdmin(admin.ModelAdmin):
    list_display = ("name", "level", "parent", "external_kind", "cost_centre", "head_of_service", "liaison_shown",
                    "active")
    list_filter = ("level", "external_kind", "active")
    search_fields = ("name", "cost_centre", "head_of_service")
    autocomplete_fields = ("parent", "liaison")
    fieldsets = (
        (None, {"fields": ("name", "level", "parent", "external_kind", "active"),
                "description": "Council directorates, departments and teams, and outside organisations sharing "
                               "council buildings (NHS, police, charities: One Public Estate)."}),
        ("Contacts and finance", {"fields": ("head_of_service", "liaison", "liaison_name", "cost_centre")}),
    )

    @admin.display(description="Property liaison")
    def liaison_shown(self, obj):
        if obj.liaison:
            return obj.liaison.get_full_name() or obj.liaison.username
        return obj.liaison_name or "–"

    def has_delete_permission(self, request, obj=None):
        if obj is not None and (obj.occupations.exists() or obj.children.exists()):
            return False  # untick Active instead, so history stays
        return super().has_delete_permission(request, obj)


@admin.register(Space)
class SpaceAdmin(_BuildingChoices, RoleAdminMixin, admin.ModelAdmin):
    list_display = ("name", "building", "kind", "floor", "use", "area_sqm", "capacity")
    list_filter = ("kind", "use")
    search_fields = ("name", "building__reference", "building__name")
    autocomplete_fields = ("building",)
    fields = ("building", ("kind", "use"), "name", ("floor", "level"), ("area_sqm", "capacity"), "notes")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        field = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name == "floor" and request.GET.get("building", "").isdigit():
            field.queryset = field.queryset.filter(building_id=int(request.GET["building"]))
        return field


@admin.register(Occupation)
class OccupationAdmin(_BuildingChoices, RoleAdminMixin, admin.ModelAdmin):
    list_display = ("occupier", "building", "space", "share", "basis", "starts", "ends")
    list_filter = ("basis", "occupier")
    search_fields = ("occupier__name", "building__reference", "building__name", "space__name")
    autocomplete_fields = ("building",)
    fields = ("building", "space", "occupier", ("share_percent", "share_sqm"), "basis", ("starts", "ends"), "notes")

    @admin.display(description="Share")
    def share(self, obj):
        area = obj.area()
        return f"{obj.percent():.0f}%" + (f" ({area} m²)" if area else "")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        field = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name == "space" and request.GET.get("building", "").isdigit():
            field.queryset = field.queryset.filter(building_id=int(request.GET["building"]))
        return field


@admin.register(Headcount)
class HeadcountAdmin(_BuildingChoices, RoleAdminMixin, admin.ModelAdmin):
    list_display = ("occupier", "building", "counted_on", "people", "fte", "source", "entered_by")
    list_filter = ("occupier",)
    autocomplete_fields = ("building",)
    fields = ("building", "occupier", "counted_on", ("people", "fte"), "source")

    @admin.display(description="Entered by")
    def entered_by(self, obj):
        who = obj.updated_by or obj.created_by
        return (who.get_full_name() or who.username) if who else "–"


@admin.register(UseMeasure)
class UseMeasureAdmin(admin.ModelAdmin):
    list_display = ("name", "unit", "order", "active")
    list_editable = ("order", "active")

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.figures.exists():
            return False
        return super().has_delete_permission(request, obj)


@admin.register(UseFigure)
class UseFigureAdmin(_BuildingChoices, RoleAdminMixin, admin.ModelAdmin):
    list_display = ("building", "measure", "period_start", "period_end", "value", "available", "source",
                    "entered_by")
    list_filter = ("measure",)
    autocomplete_fields = ("building",)
    fields = ("building", "measure", ("period_start", "period_end"), ("value", "available"), "source")

    @admin.display(description="Entered by")
    def entered_by(self, obj):
        who = obj.updated_by or obj.created_by
        return (who.get_full_name() or who.username) if who else "–"

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        field = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name == "measure":
            field.queryset = UseMeasure.objects.filter(active=True)
        return field


class _CostsOnly:
    """Cost figures are seen only by people the space costs module is opened for (administrators, finance)."""

    def _allowed(self, request):
        from apps.core.access import can_use

        return can_use(request.user, "spacecosts")

    def has_module_permission(self, request):
        return self._allowed(request) and super().has_module_permission(request)

    def has_view_permission(self, request, obj=None):
        return self._allowed(request) and super().has_view_permission(request, obj)

    def has_add_permission(self, request, *args):
        return self._allowed(request) and super().has_add_permission(request, *args)

    def has_change_permission(self, request, obj=None):
        return self._allowed(request) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return self._allowed(request) and super().has_delete_permission(request, obj)


@admin.register(CostLine)
class CostLineAdmin(_CostsOnly, admin.ModelAdmin):
    list_display = ("name", "notional", "from_jobs", "order", "active")
    list_editable = ("order", "active")

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.amounts.exists():
            return False
        return super().has_delete_permission(request, obj)


@admin.register(BuildingCost)
class BuildingCostAdmin(_CostsOnly, _BuildingChoices, admin.ModelAdmin):
    list_display = ("building", "year", "line", "amount", "source", "entered_by")
    list_filter = ("year_starting", "line")
    search_fields = ("building__reference", "building__name", "source")
    autocomplete_fields = ("building",)
    fields = ("building", "year_starting", "line", "amount", "source")

    @admin.display(description="Year", ordering="year_starting")
    def year(self, obj):
        from .models import financial_year_label

        return financial_year_label(obj.year_starting)

    @admin.display(description="Entered by")
    def entered_by(self, obj):
        who = obj.updated_by or obj.created_by
        return (who.get_full_name() or who.username) if who else "–"

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        field = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name == "line":
            field.queryset = CostLine.objects.filter(active=True)
        return field

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        if request.GET.get("year", "").isdigit():
            initial["year_starting"] = int(request.GET["year"])
        return initial


class FixedShareInline(admin.TabularInline):
    model = FixedShare
    extra = 1

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "occupier":
            kwargs["queryset"] = Occupier.objects.filter(active=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(CostSharing)
class CostSharingAdmin(_CostsOnly, _BuildingChoices, admin.ModelAdmin):
    list_display = ("building", "method", "notes")
    autocomplete_fields = ("building",)
    fields = ("building", "method", "notes")
    inlines = [FixedShareInline]
