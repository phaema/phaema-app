# SPDX-License-Identifier: AGPL-3.0-or-later
"""Requests that open a case: one form shared by the tenant portal (for example consent to assign or a licence
for alterations) and council departments' building pages (space requests). Each case type says whether tenants
or departments can ask for it, with guidance and a list of documents to attach. No fees are shown or taken."""
from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from . import workflow
from .models import Case, CaseDocument, CaseType, Correspondence, validate_case_file

MAX_FILES = 10


class _MultipleFiles(forms.ClearableFileInput):
    allow_multiple_selected = True


class _FilesField(forms.FileField):
    widget = _MultipleFiles

    def clean(self, data, initial=None):
        files = [f for f in (data if isinstance(data, (list, tuple)) else [data]) if f]
        if len(files) > MAX_FILES:
            raise ValidationError(_("Attach up to %(n)s files.") % {"n": MAX_FILES})
        for f in files:
            validate_case_file(f)
        return files


class RequestForm(forms.Form):
    case_type = forms.ModelChoiceField(queryset=None, label=gettext_lazy("What are you asking for?"),
                                       empty_label=None, widget=forms.RadioSelect)
    title = forms.CharField(max_length=150, label=gettext_lazy("In a few words"),
                            help_text=gettext_lazy("For example: assign the lease to Smith Trading Ltd"))
    details = forms.CharField(widget=forms.Textarea(attrs={"rows": 6}), max_length=8000,
                              label=gettext_lazy("Tell us more"))
    files = _FilesField(required=False, label=gettext_lazy("Documents"),
                        help_text=gettext_lazy("Up to 10 files: PDF, Word, Excel, images or emails, 25 MB each"))

    def __init__(self, *args, types=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["case_type"].queryset = types
        self.types = list(types)


def tenant_types():
    return CaseType.objects.filter(active=True, tenant_can_start=True).order_by("order", "name")


def department_types():
    return CaseType.objects.filter(active=True, department_can_start=True).order_by("order", "name")


@transaction.atomic
def submit(form, *, received, who, lease=None, prop=None, occupier=None, account=None, user=None):
    """Open the case, file the request as received correspondence and attach the documents, shared with the person
    who asked (they sent them)."""
    d = form.cleaned_data
    case = workflow.open_case(d["case_type"], title=d["title"], lease=lease, property=prop, how_received=received,
                              portal_account=account, occupier=occupier, requested_by=user)
    note = Correspondence.objects.create(case=case, direction=Correspondence.Direction.IN,
                                         method=Correspondence.Method.ONLINE, correspondent=who[:250],
                                         subject=d["title"][:250], summary=d["details"])
    for f in d["files"]:
        CaseDocument.objects.create(case=case, description=f.name[:200], original_filename=f.name[:255], file=f,
                                    correspondence=note,
                                    shared_with_requester=True)
    return case


def progress(case):
    """What the person who asked is told: where it has got to."""
    if case.status == Case.Status.CLOSED:
        if case.decision:
            return case.get_decision_display()
        return _("Closed")
    if case.status == Case.Status.ON_HOLD:
        return _("On hold")
    return case.get_stage_display()


def shared_documents(case):
    return case.documents.filter(shared_with_requester=True).order_by("created_at")


def tenant_cases(account):
    from apps.portal.access import agreements_for

    return (Case.objects.filter(lease__in=agreements_for(account), how_received=Case.Received.PORTAL)
            .select_related("case_type", "lease").order_by("-received_on", "-pk"))


def department_cases(user):
    from apps.space import liaison

    return (Case.objects.filter(occupier__in=liaison.occupiers_for(user), how_received=Case.Received.DEPARTMENT)
            .select_related("case_type", "property", "occupier").order_by("-received_on", "-pk"))
