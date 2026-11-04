# SPDX-License-Identifier: AGPL-3.0-or-later
"""User administration: administrators manage users and roles, but only superusers can grant superuser powers."""
from django import forms
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.contrib.auth.models import Group

from .roles import ROLES
from apps.core.models import AccessArea, StaffProfile, supervisor_of

AREAS_HELP = ("Which optional modules this person can open. Everyone with a role can use properties, leases, events, "
              "cases and documents. The role still decides what they can change.")


class _AreasMixin(forms.Form):
    access_areas = forms.ModelMultipleChoiceField(
        queryset=AccessArea.objects.all(), required=False, widget=forms.CheckboxSelectMultiple,
        label="Access areas", help_text=AREAS_HELP)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["access_areas"].label_from_instance = (
            lambda a: f"{a.name}: {', '.join(a.module_names()) or 'core only'}"
                      f"{'; rent and service charges for their own patch' if a.own_patch_finance else ''}"
                      f"{'; can raise rent and credit notes' if a.finance_actions else ''}")
        if self.instance and self.instance.pk:
            self.fields["access_areas"].initial = list(self.instance.access_areas.all())


class PhaemaUserChangeForm(_AreasMixin, UserChangeForm):
    pass


class PhaemaUserCreationForm(_AreasMixin, UserCreationForm):
    pass

User = get_user_model()
admin.site.unregister(User)


class StaffProfileInline(admin.StackedInline):
    model = StaffProfile
    can_delete = False
    fk_name = "user"
    extra = 1
    verbose_name = verbose_name_plural = "Staff details"
    max_num = 1
    autocomplete_fields = ["supervisor"]


@admin.register(User)
class PhaemaUserAdmin(UserAdmin):
    form = PhaemaUserChangeForm
    add_form = PhaemaUserCreationForm
    inlines = [StaffProfileInline]
    search_fields = ("username", "first_name", "last_name", "email")
    list_display = ("username", "first_name", "last_name", "email", "role", "supervisor", "is_active", "last_login")
    list_filter = ("groups", "is_active", "is_superuser")
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Personal details", {"fields": ("first_name", "last_name", "email")}),
        ("Role", {"fields": ("groups", "is_active", "is_superuser"),
                  "description": "Administrators can change everything. Surveyors can change the properties "
                                 "they manage. Viewers can only look. Give each person one role. "
                                 "When someone leaves or changes job, use "
                                 "<a href=\"/people/hand-over/\">Hand over work</a> to move their properties, "
                                 "cases and tasks to colleagues."}),
        ("Access areas", {"fields": ("access_areas",)}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("username", "first_name", "last_name", "email",
                                                 "password1", "password2", "groups", "access_areas")}),
    )

    @admin.display(description="Supervisor")
    def supervisor(self, obj):
        boss = supervisor_of(obj)
        return (boss.get_full_name() or boss.username) if boss else "–"

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

    def get_fieldsets(self, request, obj=None):
        sets = super().get_fieldsets(request, obj)
        if obj is not None and not self.has_change_permission(request, obj):
            # Read-only view (a superuser seen by an administrator): access areas are a form field, not a model one.
            sets = [s for s in sets if s[0] != "Access areas"]
        return sets

    def has_change_permission(self, request, obj=None):
        # Only superusers may edit superuser accounts.
        if obj is not None and obj.is_superuser and not request.user.is_superuser:
            return False
        return super().has_change_permission(request, obj)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        if "access_areas" in form.cleaned_data:
            form.instance.access_areas.set(form.cleaned_data["access_areas"])
        from .roles import sync_staff_status

        sync_staff_status(form.instance)
