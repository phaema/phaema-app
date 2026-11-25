# SPDX-License-Identifier: AGPL-3.0-or-later
"""Estates strategy, step 1: recording a property's asset strategy and its suitability grade."""
from datetime import date

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _

from apps.core.roles import can_edit
from apps.leases.forms import GovukMixin

from .models import AssetStrategy, AssetStrategyOption, Property, SuitabilityAssessment

DATE = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


class StrategyForm(GovukMixin, forms.ModelForm):
    class Meta:
        model = AssetStrategy
        fields = ["strategy", "decided_on", "reason", "decided_by", "meeting_on", "minute_reference", "review_on"]
        widgets = {"decided_on": DATE, "meeting_on": DATE, "review_on": DATE,
                   "strategy": forms.RadioSelect, "reason": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["strategy"].queryset = AssetStrategyOption.objects.filter(active=True)
        self.fields["strategy"].empty_label = None
        self.fields["strategy"].label_from_instance = (
            lambda o: f"{o.name}: {o.description}" if o.description else o.name)
        for name in ("decided_by", "minute_reference"):
            self.fields[name].widget.attrs["class"] = "govuk-input govuk-!-width-two-thirds"


class SuitabilityForm(GovukMixin, forms.ModelForm):
    class Meta:
        model = SuitabilityAssessment
        fields = ["grade", "assessed_on", "notes"]
        widgets = {"assessed_on": DATE, "grade": forms.RadioSelect, "notes": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["grade"].choices = SuitabilityAssessment.Grade.choices


def _editable(request, pk):
    prop = get_object_or_404(Property, pk=pk)
    if not can_edit(request.user, prop):
        raise PermissionDenied
    return prop


@login_required
def record_strategy(request, pk):
    """Record an asset strategy directly, without an Asset Challenge, for example a decision already made."""
    prop = _editable(request, pk)
    if not request.user.has_perm("properties.add_assetstrategy"):
        raise PermissionDenied
    form = StrategyForm(request.POST or None, initial={"decided_on": date.today()})
    if request.method == "POST" and form.is_valid():
        decision = form.save(commit=False)
        decision.property, decision.recorded_by = prop, request.user
        decision.source = AssetStrategy.Source.DIRECT
        decision.save()
        messages.success(request, _("Asset strategy recorded: %(s)s. Next review %(d)s.")
                         % {"s": decision.strategy, "d": decision.review_on.strftime("%d %b %Y")})
        return redirect(prop.get_absolute_url() + "#strategy")
    return render(request, "properties/strategy_form.html", {
        "object": prop, "form": form, "title": _("Record the asset strategy"),
        "intro": _("Use this for a decision already made, for example in an earlier review or at a committee. "
                   "To review the property's future afresh, start an Asset Challenge instead."),
        "button": _("Record the asset strategy")})


@login_required
def record_suitability(request, pk):
    prop = _editable(request, pk)
    if not request.user.has_perm("properties.add_suitabilityassessment"):
        raise PermissionDenied
    form = SuitabilityForm(request.POST or None, initial={"assessed_on": date.today()})
    if request.method == "POST" and form.is_valid():
        grade = form.save(commit=False)
        grade.property, grade.assessed_by = prop, request.user
        grade.save()
        messages.success(request, _("Suitability recorded: grade %(g)s.") % {"g": grade.grade})
        return redirect(prop.get_absolute_url() + "#strategy")
    return render(request, "properties/strategy_form.html", {
        "object": prop, "form": form, "title": _("Record suitability"),
        "intro": _("How well the building suits the service in it today, whatever its condition: layout, "
                   "access, location, size and the impression it gives."),
        "button": _("Record suitability")})


@login_required
def itza_calculator(request, pk):
    """Work out the area In Terms of Zone A, and keep it (with the workings) on the property."""
    from django.utils import timezone

    from . import itza

    prop = get_object_or_404(Property, pk=pk)
    editable = can_edit(request.user, prop)
    if request.method == "POST":
        spec = itza.spec_from_post(request.POST)
        result = itza.calculate(spec)
        if "save" in request.POST and result.ok:
            if not editable:
                raise PermissionDenied
            prop.itza_sqm, prop.itza_zone_depth_m = result.total, result.zone_depth
            prop.itza_workings = {k: v for k, v in spec.items() if k != "zone_a_rate"}
            prop.itza_measured_on = timezone.localdate()
            prop.itza_notes = request.POST.get("notes", "")[:255]
            prop.save(update_fields=["itza_sqm", "itza_zone_depth_m", "itza_workings", "itza_measured_on",
                                     "itza_notes", "updated_at"])
            messages.success(request, _("ITZA of %(a)s m² saved on the property.") % {"a": f"{result.total:,.2f}"})
            return redirect(prop.get_absolute_url() + "#areas")
    else:
        spec = dict(prop.itza_workings or {}) or {"zone_depth": str(prop.itza_zone_depth_m or itza.DEFAULT_ZONE_DEPTH),
                                                  "mode": "rectangle"}
        result = itza.calculate(spec) if prop.itza_workings else None
    others = list(spec.get("others") or [])
    others += [{}] * (itza.OTHER_ROWS - len(others))
    zones = list(spec.get("zones") or []) + [""] * len(itza.ZONES)
    rent = prop.zone_a_rent()
    return render(request, "properties/itza.html", {
        "object": prop, "spec": spec, "result": result, "editable": editable,
        "zones": [(n, label, zones[n]) for n, (label, _w) in enumerate(itza.ZONES)],
        "others": list(enumerate(others[:itza.OTHER_ROWS])), "divisors": itza.COMMON_DIVISORS,
        "notes": request.POST.get("notes", prop.itza_notes) if request.method == "POST" else prop.itza_notes,
        "result_sqft": itza.sqft(result.total) if result is not None and result.ok else None,
        "rate_sqft": itza.per_sqft(result.zone_a_rate) if result is not None and result.zone_a_rate else None,
        "rent": rent, "rent_sqft": itza.per_sqft(rent[1]) if rent else None,
    })
