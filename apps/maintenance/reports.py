# SPDX-License-Identifier: AGPL-3.0-or-later
"""Repair reports: one form shared by the tenant portal and council departments' property liaisons, and the triage
queue where estates decide what becomes a job."""
from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.files import validate_image
from apps.core.models import ModuleSettings

from . import workflow
from .models import Category, Job, RepairPhoto, RepairReport


def enabled():
    return ModuleSettings.load().maintenance_enabled


class _MultipleImages(forms.ClearableFileInput):
    allow_multiple_selected = True


class _ImagesField(forms.FileField):
    widget = _MultipleImages

    def clean(self, data, initial=None):
        files = [f for f in (data if isinstance(data, (list, tuple)) else [data]) if f]
        if len(files) > RepairReport.MAX_PHOTOS:
            raise ValidationError(_("Add up to %(n)s photos.") % {"n": RepairReport.MAX_PHOTOS})
        for f in files:
            validate_image(f)
        return files


class RepairForm(forms.Form):
    """The repair report form, the same for tenants and council departments."""

    property = forms.ModelChoiceField(queryset=None, label=_("Which building or unit"), required=True)
    location = forms.CharField(max_length=200, label=_("Where is the problem?"),
                               help_text=_("For example: first floor kitchen, above the sink"))
    description = forms.CharField(widget=forms.Textarea(attrs={"rows": 5}), max_length=4000,
                                  label=_("What is wrong?"),
                                  help_text=_("When it started, and anything you have done about it"))
    danger = forms.BooleanField(required=False, label=_("Someone may be at risk, or the building is unsafe or "
                                                        "insecure"))
    contact_phone = forms.CharField(max_length=30, required=False, label=_("Phone number to arrange access"))
    photos = _ImagesField(required=False, label=_("Photos (optional)"),
                          help_text=_("Up to 3 photos, JPEG or PNG"))

    def __init__(self, *args, properties=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["property"].queryset = properties
        self.fields["property"].label_from_instance = lambda p: p.name
        if properties is not None and properties.count() == 1:
            self.fields["property"].initial = properties.first().pk
            self.single = properties.first()
        else:
            self.single = None


@transaction.atomic
def submit(form, *, source, reporter_name, lease=None, occupier=None, account=None, user=None):
    d = form.cleaned_data
    report = RepairReport.objects.create(
        property=d["property"], lease=lease, occupier=occupier, source=source, portal_account=account,
        reported_by_user=user, reporter_name=reporter_name[:150], contact_phone=d["contact_phone"],
        location=d["location"], description=d["description"], danger=d["danger"])
    for f in d["photos"]:
        RepairPhoto.objects.create(report=report, image=f)
    return report


def queue_for(user):
    """Reports waiting to be looked at that this person should see on their dashboard: for buildings they manage,
    or, for administrators, any building, including those no one manages."""
    from apps.core.roles import is_administrator

    waiting = RepairReport.objects.filter(status=RepairReport.Status.NEW).select_related("property")
    if is_administrator(user):
        return waiting
    return waiting.filter(property__managing_surveyor=user)


def _decide(report, user, status, reply="", job=None):
    report.status, report.reply, report.job = status, reply, job
    report.decided_by, report.decided_at = user, timezone.now()
    report.save(update_fields=["status", "reply", "job", "decided_by", "decided_at", "updated_at"])
    return report


def raise_job(report, user, title, category, priority, reply=""):
    how = Job.Reported.TENANT if report.source == RepairReport.Source.TENANT else Job.Reported.ONLINE
    details = f"{report.location}\n\n{report.description}"
    if report.danger:
        details = "Reported as a possible risk to people or an unsafe or insecure building.\n\n" + details
    job = workflow.open_job(report.property, title, user=user, description=details, category=category,
                            priority=priority, reported_by=report.reporter_name, how_reported=how,
                            reported_on=timezone.localdate(report.created_at), lease=report.lease)
    return _decide(report, user, RepairReport.Status.JOB, reply, job)


def mark(report, user, status, reply, job=None):
    return _decide(report, user, status, reply, job)


def open_jobs_at(prop):
    """Open jobs at the property, for "already reported"."""
    return Job.objects.filter(Q(property=prop) | Q(property__in=[a.pk for a in prop.ancestors()]),
                              status__in=Job.OPEN).order_by("-reported_on")


CATEGORIES = Category.choices
