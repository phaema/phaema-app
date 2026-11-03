# SPDX-License-Identifier: AGPL-3.0-or-later
from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from apps.core.roles import ADMINISTRATORS, SURVEYORS

from .models import LeaseEvent, RentScheduleEntry
from .workflow import BREAK_OUTCOMES, EXPIRY_OUTCOMES


class DateInput(forms.DateInput):
    input_type = "date"

    def __init__(self, **kwargs):
        super().__init__(format="%Y-%m-%d", **kwargs)


def officer_choices():
    users = get_user_model().objects.filter(is_active=True, groups__name__in=[ADMINISTRATORS, SURVEYORS]).distinct()
    return users.order_by("first_name", "last_name", "username")


class GovukMixin:
    """Add GOV.UK Design System classes to widgets."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            w = field.widget
            if isinstance(w, forms.Select):
                w.attrs.setdefault("class", "govuk-select")
            elif isinstance(w, forms.Textarea):
                w.attrs.setdefault("class", "govuk-textarea")
                w.attrs.setdefault("rows", 3)
            elif isinstance(w, forms.RadioSelect):
                pass
            else:
                w.attrs.setdefault("class", "govuk-input govuk-input--width-10")


class ReviewOutcomeForm(GovukMixin, forms.Form):
    new_rent = forms.DecimalField(label=_("Agreed annual rent (£)"), max_digits=12, decimal_places=2, min_value=0)
    effective_from = forms.DateField(label=_("Effective from"), widget=DateInput(),
                                     help_text=_("Usually the review date, even if settled later."))
    next_review_date = forms.DateField(label=_("Next rent review"), required=False, widget=DateInput(),
                                       help_text=_("Leave blank if there are no further reviews."))
    notes = forms.CharField(label=_("Notes"), required=False, widget=forms.Textarea,
                            help_text=_("e.g. settled by agreement, by arbitration, or index applied."))


class BreakOutcomeForm(GovukMixin, forms.Form):
    outcome = forms.ChoiceField(label=_("Outcome"), widget=forms.RadioSelect)
    notes = forms.CharField(label=_("Notes"), required=False, widget=forms.Textarea)

    def __init__(self, *args, event=None, **kwargs):
        super().__init__(*args, **kwargs)
        keys = ["served", "not_served"] if event and event.event_type == LeaseEvent.EventType.BREAK_NOTICE \
            else ["exercised", "not_exercised"]
        self.fields["outcome"].choices = [(k, BREAK_OUTCOMES[k]) for k in keys]


class ExpiryOutcomeForm(GovukMixin, forms.Form):
    outcome = forms.ChoiceField(label=_("Outcome"), widget=forms.RadioSelect, choices=list(EXPIRY_OUTCOMES.items()))
    end_date = forms.DateField(label=_("Date the agreement ended"), required=False, widget=DateInput(),
                               help_text=_("Leave blank to use the expiry date. Not needed if holding over."))
    notes = forms.CharField(label=_("Notes"), required=False, widget=forms.Textarea)


class OtherOutcomeForm(GovukMixin, forms.Form):
    status = forms.ChoiceField(label=_("Outcome"), widget=forms.RadioSelect, choices=[
        (LeaseEvent.Status.DONE, _("Completed")), (LeaseEvent.Status.LAPSED, _("No longer needed"))])
    notes = forms.CharField(label=_("Notes"), required=False, widget=forms.Textarea)


class EventEditForm(GovukMixin, forms.ModelForm):
    """Assign an event, mark it in progress, or (for events added by hand) change its title and date."""

    class Meta:
        model = LeaseEvent
        fields = ["title", "due_date", "assigned_to", "status", "outcome"]
        widgets = {"due_date": DateInput(), "outcome": forms.Textarea}
        labels = {"outcome": _("Notes")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].queryset = officer_choices()
        self.fields["assigned_to"].label_from_instance = lambda u: u.get_full_name() or u.username
        self.fields["status"].choices = [(LeaseEvent.Status.OPEN, _("To do")),
                                         (LeaseEvent.Status.IN_PROGRESS, _("In progress"))]
        self.fields["title"].widget.attrs["class"] = "govuk-input"
        if self.instance.pk and self.instance.source:
            # Generated events follow the lease: change the lease to move them.
            del self.fields["title"]
            del self.fields["due_date"]


class NewEventForm(GovukMixin, forms.ModelForm):
    class Meta:
        model = LeaseEvent
        fields = ["title", "due_date", "assigned_to", "outcome"]
        widgets = {"due_date": DateInput(), "outcome": forms.Textarea}
        labels = {"outcome": _("Notes"), "title": _("What needs doing")}
        help_texts = {"title": _("e.g. Insurance renewal, dilapidations inspection, serve section 25 notice.")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].required = True
        self.fields["title"].widget.attrs["class"] = "govuk-input"
        self.fields["assigned_to"].queryset = officer_choices()
        self.fields["assigned_to"].label_from_instance = lambda u: u.get_full_name() or u.username


class RentStepForm(GovukMixin, forms.ModelForm):
    class Meta:
        model = RentScheduleEntry
        fields = ["effective_from", "annual_rent", "reason", "notes"]
        widgets = {"effective_from": DateInput()}

    def __init__(self, *args, lease=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.lease = lease
        self.fields["notes"].widget.attrs["class"] = "govuk-input"

    def clean_effective_from(self):
        value = self.cleaned_data["effective_from"]
        if self.lease and self.lease.rent_schedule.filter(effective_from=value).exists():
            raise forms.ValidationError(_("There is already a rent from that date. Change that entry instead."))
        return value
