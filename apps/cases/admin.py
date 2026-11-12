# SPDX-License-Identifier: AGPL-3.0-or-later
from django import forms
from django.contrib import admin

from apps.core.admin_roles import RoleAdminMixin

from apps.properties.report import PARTS

from .models import STAGE_ORDER, Case, CaseType, CaseTypeChecklistItem, CaseTypeTask, Stage


class CaseTypeForm(forms.ModelForm):
    approval_stages = forms.MultipleChoiceField(
        label="Supervisor approval needed before", required=False, widget=forms.CheckboxSelectMultiple,
        choices=[(s, label) for s, label in Stage.choices if s != STAGE_ORDER[0]],
        help_text="The case cannot move to these stages until the owner's supervisor approves.")
    visit_parts = forms.MultipleChoiceField(
        label="Property information on the site visit sheet", required=False, widget=forms.CheckboxSelectMultiple,
        choices=PARTS,
        help_text="What is printed about the property on the site visit sheet for cases of this type. The case "
                  "details and the safety information (Before you visit) are always included.")

    class Meta:
        model = CaseType
        fields = "__all__"


class TaskTemplateInline(admin.TabularInline):
    model = CaseTypeTask
    extra = 0


class ChecklistInline(admin.TabularInline):
    model = CaseTypeChecklistItem
    extra = 0
    fields = ("order", "heading", "label", "guidance", "kind", "choices", "checks", "each_building")
    verbose_name_plural = "Site visit checklist: what to check or record on site"


@admin.register(CaseType)
class CaseTypeAdmin(RoleAdminMixin, admin.ModelAdmin):
    form = CaseTypeForm
    list_display = ("name", "group", "target_days", "acknowledge_working_days", "fee", "approval", "heads_of_terms", "event_type",
                    "active")
    list_filter = ("group", "active")
    search_fields = ("name", "code")
    inlines = [TaskTemplateInline, ChecklistInline]

    @admin.display(description="approval before")
    def approval(self, obj):
        labels = dict(Stage.choices)
        return ", ".join(str(labels.get(s, s)) for s in obj.approval_stages or []) or "–"


@admin.register(Case)
class CaseAdmin(RoleAdminMixin, admin.ModelAdmin):
    list_display = ("__str__", "case_type", "stage", "status", "owner", "received_on", "target_date")
    list_filter = ("status", "stage", "case_type__group")
    search_fields = ("title", "number", "lease__reference", "property__reference", "party__name")
    autocomplete_fields = ["lease", "property", "party"]
    filter_horizontal = ("contributors",)
    readonly_fields = ("event",)

    def view_on_site(self, obj):
        return obj.get_absolute_url()
