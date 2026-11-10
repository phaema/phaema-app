# SPDX-License-Identifier: AGPL-3.0-or-later
from django.contrib import admin

from apps.core.admin_users import PhaemaUserAdmin

from .models import SsoGroupMapping, SsoIdentity


class SsoIdentityInline(admin.StackedInline):
    """Shows whether the person signs in with their council account. Tick Delete to unlink them."""

    model = SsoIdentity
    extra = 0
    max_num = 0
    fields = readonly_fields = ("email", "issuer", "linked_at", "last_sign_in")
    verbose_name = verbose_name_plural = "Council sign-in (tick Delete to unlink)"


PhaemaUserAdmin.inlines = [*PhaemaUserAdmin.inlines, SsoIdentityInline]


@admin.register(SsoGroupMapping)
class SsoGroupMappingAdmin(admin.ModelAdmin):
    list_display = ("label", "group", "role", "access_area")
    list_filter = ("role", "access_area")
    search_fields = ("label", "group")
