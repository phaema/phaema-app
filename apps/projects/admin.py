# SPDX-License-Identifier: AGPL-3.0-or-later
from django.contrib import admin

from .models import ProjectType


@admin.register(ProjectType)
class ProjectTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "confidential_by_default", "active")
    list_editable = ("active",)
    prepopulated_fields = {"code": ("name",)}
