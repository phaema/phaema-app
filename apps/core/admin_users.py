# SPDX-License-Identifier: AGPL-3.0-or-later
"""User administration: administrators manage users and roles, but only superusers can grant superuser powers."""
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group

from .roles import ROLES

User = get_user_model()
admin.site.unregister(User)


@admin.register(User)
class PhaemaUserAdmin(UserAdmin):
    list_display = ("username", "first_name", "last_name", "email", "role", "is_active", "last_login")
    list_filter = ("groups", "is_active", "is_superuser")
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Personal details", {"fields": ("first_name", "last_name", "email")}),
        ("Role", {"fields": ("groups", "is_active", "is_superuser"),
                  "description": "Administrators can change everything. Surveyors can change the properties "
                                 "they manage. Viewers can only look. Give each person one role."}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("username", "first_name", "last_name", "email",
                                                 "password1", "password2", "groups")}),
    )

    @admin.display(description="Role")
    def role(self, obj):
        if obj.is_superuser:
            return "Superuser"
        return ", ".join(g.name for g in obj.groups.all()) or "None"

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == "groups":
            kwargs["queryset"] = Group.objects.filter(name__in=ROLES).order_by("name")
        return super().formfield_for_manytomany(db_field, request, **kwargs)

    def get_readonly_fields(self, request, obj=None):
        fields = ["last_login", "date_joined"]
        if not request.user.is_superuser:
            fields.append("is_superuser")
        return fields

    def has_change_permission(self, request, obj=None):
        # Only superusers may edit superuser accounts.
        if obj is not None and obj.is_superuser and not request.user.is_superuser:
            return False
        return super().has_change_permission(request, obj)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        from .roles import sync_staff_status

        sync_staff_status(form.instance)
