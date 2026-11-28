# SPDX-License-Identifier: AGPL-3.0-or-later
"""Condition surveys: the survey programme, entering a survey and its items, raising jobs, and the backlog."""
from datetime import date

from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST

from apps.core import places
from apps.core.roles import can_edit
from apps.properties.models import Property
from apps.reports.export import csv_response, xlsx_response

from . import surveys
from .models import Component, ConditionSurvey, SurveyItem
from .views import _can_raise, maintenance_view


class SurveyForm(forms.ModelForm):
    class Meta:
        model = ConditionSurvey
        fields = ["kind", "surveyed_on", "surveyor", "overall_grade", "next_due", "notes", "report"]
        widgets = {"surveyed_on": forms.DateInput(attrs={"type": "date"}),
                   "next_due": forms.DateInput(attrs={"type": "date"}),
                   "notes": forms.Textarea(attrs={"rows": 3})}
        help_texts = {"next_due": gettext_lazy("Left blank, five years after the survey.")}


class ItemForm(forms.ModelForm):
    class Meta:
        model = SurveyItem
        fields = ["element", "location", "description", "grade", "priority", "estimated_cost", "capital",
                  "due_year", "component"]

    def __init__(self, *args, survey=None, **kwargs):
        super().__init__(*args, **kwargs)
        prop = survey.property
        ids = {prop.pk} | prop._descendant_ids()
        self.fields["component"].queryset = Component.objects.filter(property_id__in=ids).select_related("property")
        self.fields["component"].label_from_instance = lambda c: f"{c.name} ({c.property.reference})"


def _editable(request, survey):
    return can_edit(request.user, survey.property)


@maintenance_view
def survey_list(request):
    """The survey programme: when each building was last surveyed and when the next is due."""
    qs = Property.objects.all()
    building, who = request.GET.get("building", ""), request.GET.get("surveyor", "")
    if building.isdigit():
        qs = qs.filter(pk__in=places.subtree(int(building)))
    if who == "me":
        qs = qs.filter(managing_surveyor=request.user)
    elif who == "none":
        qs = qs.filter(managing_surveyor__isnull=True)
    elif who.isdigit():
        qs = qs.filter(managing_surveyor_id=int(who))
    rows = surveys.programme(qs)
    state = request.GET.get("state", "")
    counts = {k: sum(1 for r in rows if r["state"] == k) for k in ("never", "overdue", "due", "ok")}
    if state in counts:
        rows = [r for r in rows if r["state"] == state]
    return render(request, "maintenance/surveys.html", {
        "section": "surveys", "rows": rows, "counts": counts, "state": state,
        "place_filters": places.filters(request.GET), "query": request.GET.urlencode()})


@maintenance_view
def survey_new(request, pk):
    prop = get_object_or_404(Property, pk=pk)
    if not can_edit(request.user, prop):
        raise PermissionDenied
    form = SurveyForm(request.POST or None, request.FILES or None, initial={"surveyed_on": date.today()})
    if request.method == "POST" and form.is_valid():
        survey = form.save(commit=False)
        survey.property = prop
        survey.save()
        messages.success(request, _("Survey added. Now add the work it found."))
        return redirect(survey)
    return render(request, "maintenance/survey_form.html", {"form": form, "property": prop})


@maintenance_view
def survey_detail(request, pk):
    survey = get_object_or_404(ConditionSurvey.objects.select_related("property"), pk=pk)
    editable = _editable(request, survey)
    item_form = ItemForm(survey=survey)
    edit_form = None
    if request.method == "POST":
        if not editable:
            raise PermissionDenied
        action = request.POST.get("action")
        if action == "add_item":
            item_form = ItemForm(request.POST, survey=survey)
            if item_form.is_valid():
                item = item_form.save(commit=False)
                item.survey = survey
                item.save()
                messages.success(request, _("Item added."))
                return redirect(f"{survey.get_absolute_url()}#items")
        elif action == "edit":
            edit_form = SurveyForm(request.POST, request.FILES, instance=survey)
            if edit_form.is_valid():
                edit_form.save()
                messages.success(request, _("Survey details saved."))
                return redirect(survey)
        elif action == "finish" and survey.status == ConditionSurvey.Status.DRAFT:
            changed = surveys.finish(survey, update_components=bool(request.POST.get("update_components")))
            messages.success(request, _("Survey finished. %(n)s component grades updated.") % {"n": changed})
            return redirect(survey)
        elif action == "reopen" and survey.status == ConditionSurvey.Status.FINISHED:
            survey.status, survey.finished_on = ConditionSurvey.Status.DRAFT, None
            survey.save(update_fields=["status", "finished_on", "updated_at"])
            return redirect(survey)
    items = list(survey.items.select_related("component", "job"))
    return render(request, "maintenance/survey_detail.html", {
        "survey": survey, "property": survey.property, "items": items, "editable": editable,
        "can_raise": editable and _can_raise(request.user), "item_form": item_form,
        "edit_form": edit_form or SurveyForm(instance=survey), "editing": edit_form is not None,
        "summary": surveys.backlog([i for i in items if i.is_open]),
        "linked": sum(1 for i in items if i.component_id)})


@maintenance_view
@require_POST
def item_action(request, pk):
    item = get_object_or_404(SurveyItem.objects.select_related("survey__property", "job"), pk=pk)
    survey = item.survey
    if not _editable(request, survey):
        raise PermissionDenied
    action = request.POST.get("action")
    if action == "job":
        if not _can_raise(request.user):
            raise PermissionDenied
        try:
            job = surveys.raise_job(item, request.user)
        except ValueError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, _("Job %(ref)s raised.") % {"ref": job.reference})
            return redirect(job)
    elif action in (SurveyItem.State.DONE, SurveyItem.State.NOT_NEEDED, SurveyItem.State.OPEN):
        item.state, item.state_note = action, request.POST.get("note", "")[:255]
        item.save(update_fields=["state", "state_note", "updated_at"])
    elif action == "delete" and survey.status == ConditionSurvey.Status.DRAFT:
        item.delete()
    return redirect(f"{survey.get_absolute_url()}#items")


@maintenance_view
def backlog(request):
    """Backlog maintenance across the estate: open survey items by priority, element and year due."""
    get = request.GET
    qs = surveys.open_items(SurveyItem.objects.select_related("survey__property", "job", "component"))
    qs = places.apply(qs, get, request.user, "survey__property")
    priority = get.get("priority", "")
    if priority in ("1", "2", "3", "4"):
        qs = qs.filter(priority=int(priority))
    elif priority == "backlog":
        qs = qs.filter(priority__in=SurveyItem.BACKLOG)
    items = list(qs.order_by("priority", "due_year", "survey__property__reference"))
    span = int(get.get("years", "10")) if get.get("years", "10") in ("5", "10", "20") else 10
    this_year = date.today().year
    summary = surveys.backlog(items)
    years = [(y, summary["by_year"].get(y, 0)) for y in range(this_year, this_year + span)]
    later = sum((v for y, v in summary["by_year"].items() if y >= this_year + span), 0)
    fmt = get.get("format")
    if fmt in ("xlsx", "csv"):
        from collections import namedtuple

        Col = namedtuple("Col", "label type")
        cols = [Col("Property", "text"), Col("Name", "text"), Col("Surveyed on", "date"), Col("Element", "text"),
                Col("Location", "text"), Col("Work needed", "text"), Col("Condition", "text"),
                Col("Priority", "number"), Col("Year due", "number"), Col("Estimated cost", "money"),
                Col("Capital", "text"), Col("Status", "text")]
        data = ([i.survey.property.reference, i.survey.property.name, i.survey.surveyed_on, i.get_element_display(),
                 i.location, i.description, i.grade, i.priority, i.due_year, i.estimated_cost,
                 "Yes" if i.capital else "No", str(i.status_label)] for i in items)
        title = "Backlog maintenance"
        return xlsx_response(title, cols, data, totals=True) if fmt == "xlsx" else csv_response(title, cols, data)
    return render(request, "maintenance/backlog.html", {
        "section": "backlog", "items": items[:500], "count": len(items), "summary": summary, "years": years,
        "later": later, "span": span, "priority": priority, "place_filters": places.filters(get),
        "query": get.urlencode()})
