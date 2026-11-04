# SPDX-License-Identifier: AGPL-3.0-or-later
"""The document library: choose a template, check the details PHAEMA fills in, download it as Word."""
from datetime import date

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils.text import slugify

from apps.core.roles import is_administrator, role_of
from apps.leases.models import Lease
from apps.properties.models import Property

from . import merge, render as docs
from .models import DocumentTemplate

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _can_create(user):
    return role_of(user) in ("Administrators", "Surveyors", "Contributors")


@login_required
def library(request):
    templates = DocumentTemplate.objects.filter(active=True)
    groups = []
    for value, label in DocumentTemplate.Category.choices:
        items = [t for t in templates if t.category == value]
        if items:
            groups.append((label, items))
    return render(request, "documents/library.html", {"groups": groups, "is_admin": is_administrator(request.user)})


def _source(request, template):
    """The record the document is created from, as keyword arguments for merge.context."""
    get = request.GET if request.method == "GET" else request.POST
    from apps.cases.models import Case

    found = {}
    if get.get("case"):
        found["case"] = get_object_or_404(Case.objects.select_related("case_type", "lease", "party"), pk=get["case"])
    if get.get("lease"):
        found["lease"] = get_object_or_404(Lease, pk=get["lease"])
    if get.get("property"):
        found["prop"] = get_object_or_404(Property, pk=get["property"])
    if get.get("valuation"):
        from apps.valuations.models import Valuation

        found["valuation"] = get_object_or_404(Valuation, pk=get["valuation"])
    return found


@login_required
def create(request, code):
    template = get_object_or_404(DocumentTemplate, code=code, active=True)
    if not _can_create(request.user):
        raise PermissionDenied
    source = _source(request, template)
    if not source:
        return _choose(request, template)
    values = merge.context(user=request.user, **source)
    extras = template.extra_fields or []
    if request.method == "POST":
        for key in list(values) + [f["key"] for f in extras]:
            if f"f_{key}" in request.POST:
                values[key] = request.POST[f"f_{key}"].strip()
        text = docs.fill(template, values, extras)
        if request.POST.get("action") == "preview":
            return _page(request, template, source, values, extras, preview=docs.to_html(text, values))
        data = docs.to_docx(template, text, values)
        name = f"{slugify(template.name)[:50]}-{slugify(values.get('case_reference') or values.get('lease_reference') or values.get('property_reference') or date.today().isoformat())}.docx"
        case = source.get("case")
        if case is not None and request.POST.get("save") == "1":
            from apps.cases.models import CaseDocument
            from apps.cases.workflow import can_contribute

            if can_contribute(request.user, case):
                doc = CaseDocument(case=case, description=f"{template.name} (draft, {date.today():%d/%m/%Y})"[:200],
                                   original_filename=name)
                doc.file.save(name, ContentFile(data), save=True)
        response = HttpResponse(data, content_type=DOCX)
        response["Content-Disposition"] = f'attachment; filename="{name}"'
        return response
    return _page(request, template, source, values, extras,
                 preview=docs.to_html(docs.fill(template, values, extras), values))


def _page(request, template, source, values, extras, preview):
    extra_keys = {f["key"] for f in extras}
    used = {k for k in merge.FIELDS if ("{{ " + k in template.body or "{{" + k in template.body)
            and k not in extra_keys}
    groups = {}
    for key, (group, label) in merge.FIELDS.items():
        if key in used:
            groups.setdefault(group, []).append((key, label, values.get(key, ""), "\n" in str(values.get(key, ""))
                                                 or key in ("reasons", "alienation", "tenant_address",
                                                            "council_address", "addressee_address",
                                                            "guarantor_address")))
    extra_rows = [(f["key"], f.get("label", f["key"]), values.get(f["key"], ""), f.get("long", False),
                   f.get("help", "")) for f in extras]
    case = source.get("case")
    return render(request, "documents/create.html", {
        "template": template, "groups": groups.items(), "extras": extra_rows, "preview": preview,
        "hidden": {k: getattr(v, "pk", v) for k, v in (("case", case), ("lease", source.get("lease")),
                                                         ("property", source.get("prop")),
                                                         ("valuation", source.get("valuation"))) if v},
        "case": case, "source": source,
    })


def _choose(request, template):
    """No record given: pick one."""
    from apps.cases.models import Case

    q = request.GET.get("q", "").strip()
    options = []
    if template.source == "case":
        qs = Case.objects.exclude(status="closed").select_related("case_type")
        if template.case_types:
            qs = qs.filter(case_type__code__in=template.case_types)
        if q:
            qs = qs.filter(title__icontains=q)
        options = [("case", c.pk, f"{c.display_reference} {c.title}") for c in qs[:50]]
    elif template.source in ("lease",):
        qs = Lease.objects.select_related("counterparty").order_by("reference")
        if q:
            qs = qs.filter(reference__icontains=q) | qs.filter(counterparty__name__icontains=q)
        options = [("lease", x.pk, f"{x.reference} {x.counterparty}") for x in qs[:50]]
    elif template.source == "valuation":
        from apps.valuations.models import Valuation

        qs = Valuation.objects.exclude(status="accepted").select_related("property")
        options = [("valuation", v.pk, str(v)) for v in qs[:50]]
    else:
        qs = Property.objects.order_by("reference")
        if q:
            qs = qs.filter(name__icontains=q) | qs.filter(reference__icontains=q)
        options = [("property", p.pk, f"{p.reference} {p.name}") for p in qs[:50]]
    return render(request, "documents/choose.html", {"template": template, "options": options, "q": q})


@login_required
def template_detail(request, code):
    template = get_object_or_404(DocumentTemplate, code=code)
    from .merge import FIELDS

    return render(request, "documents/template.html", {
        "template": template, "is_admin": is_administrator(request.user), "fields": FIELDS.items(),
        "preview": docs.to_html(docs.fill(template, {}, template.extra_fields or []), {}),
    })


def for_case(case):
    return [t for t in DocumentTemplate.objects.filter(active=True, source="case") if t.offered_for(case)]


def for_lease():
    return list(DocumentTemplate.objects.filter(active=True, source="lease"))
