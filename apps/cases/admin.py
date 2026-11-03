# SPDX-License-Identifier: AGPL-3.0-or-later
from django import forms
from django.contrib import admin

from apps.core.admin_roles import RoleAdminMixin

from .models import STAGE_ORDER, Case, CaseType, CaseTypeTask, Stage


class CaseTypeForm(forms.ModelForm):
    approval_stages = forms.MultipleChoiceField(
        label="Supervisor approval needed before", required=False, widget=forms.CheckboxSelectMultiple,
        choices=[(s, label) for s, label in Stage.choices if s != STAGE_ORDER[0]],
        help_text="The case cannot move to these stages until the owner's supervisor approves.")

    class Meta:
        model = CaseType
        fields = "__all__"


class TaskTemplateInline(admin.TabularInline):
    model = CaseTypeTask
    extra = 0


@admin.register(CaseType)
class CaseTypeAdmin(RoleAdminMixin, admin.ModelAdmin):
    form = CaseTypeForm
    list_display = ("name", "group", "target_days", "acknowledge_working_days", "fee", "approval", "event_type",
                    "active")
    list_filter = ("group", "active")
    search_fields = ("name", "code")
    inlines = [TaskTemplateInline]

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
