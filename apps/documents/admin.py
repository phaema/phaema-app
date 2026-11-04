# SPDX-License-Identifier: AGPL-3.0-or-later
from django import forms
from django.contrib import admin

from .models import DocumentTemplate


class TemplateForm(forms.ModelForm):
    class Meta:
        model = DocumentTemplate
        fields = "__all__"
        widgets = {"body": forms.Textarea(attrs={"rows": 40, "cols": 100, "style": "font-family: monospace"})}


@admin.register(DocumentTemplate)
class DocumentTemplateAdmin(admin.ModelAdmin):
    form = TemplateForm
    list_display = ("name", "category", "source", "prescribed_form", "shipped", "active")
    list_filter = ("category", "source", "active", "shipped")
    search_fields = ("name", "code", "body")
    save_as = True  # "Save as new" makes a council's own copy of a supplied template

    def view_on_site(self, obj):
        return obj.get_absolute_url()
