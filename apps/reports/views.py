# SPDX-License-Identifier: AGPL-3.0-or-later
"""Report builder: choose records, columns, filters and order; save; run on screen or download."""
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core.roles import ADMINISTRATORS, SURVEYORS

from . import datasets, export
from .models import Report

DATE_MODES = [("", "Any date"), ("next", "In the next … days"), ("last", "In the last … days"),
              ("before_today", "Before today"), ("between", "Between two dates")]


@login_required
def report_list(request):
    visible = Report.objects.filter(Q(shared=True) | ~Q(starter="") | Q(owner=request.user))
    return render(request, "reports/report_list.html", {
        "starters": visible.exclude(starter=""),
        "shared": visible.filter(starter="", shared=True).exclude(owner=request.user).select_related("owner"),
        "mine": visible.filter(starter="", owner=request.user),
        "datasets": datasets.registry().values(),
    })


def _get_visible(request, pk):
    report = get_object_or_404(Report, pk=pk)
    if not report.visible_to(request.user):
        raise Http404
    return report


def _queryset(report):
    ds = datasets.get(report.dataset)
    qs = datasets.apply_filters(ds, ds.queryset(), report.filters)
    sort = ds.field(report.sort_by)
    if sort and sort.filterable:
        order = sort.path if not sort.type == "user" else f"{sort.path}__first_name"
        qs = qs.order_by(f"-{order}" if report.sort_descending else order, "pk")
    return ds, qs


@login_required
def report_run(request, pk):
    report = _get_visible(request, pk)
    ds, qs = _queryset(report)
    if ds is None:
        raise Http404
    exported = export.download(request, report.name, ds, qs, report.columns, totals=report.show_totals)
    if exported:
        return exported
    page = Paginator(qs, 200).get_page(request.GET.get("page"))
    fields, row_iter = datasets.rows(ds, page.object_list, report.columns)
    table = list(row_iter)
    totals = None
    if report.show_totals:
        _f, all_rows = datasets.rows(ds, qs, report.columns)
        sums = [Decimal("0")] * len(fields)
        for row in all_rows:
            for i, (f, v) in enumerate(zip(fields, row)):
                if f.type in ("money", "area") and v is not None:
                    sums[i] += Decimal(str(v))
        totals = [s if f.type in ("money", "area") else None for f, s in zip(fields, sums)]
    return render(request, "reports/report_run.html", {
        "report": report, "dataset": ds, "fields": fields, "table": table, "page_obj": page,
        "totals": totals, "count": page.paginator.count, "can_change": report.can_change(request.user),
        "filter_summary": _describe_filters(ds, report.filters),
    })


def _describe_filters(ds, filters):
    lines = []
    for key, spec in (filters or {}).items():
        f = ds.field(key)
        if not f or not spec:
            continue
        if "in" in spec:
            names = dict(f.choices) if f.type == "choice" else {}
            if f.type == "user":
                users = {str(u.pk): (u.get_full_name() or u.username)
                         for u in get_user_model().objects.filter(pk__in=[v for v in spec["in"] if str(v).isdigit()])}
                names = {**users, "none": _("Nobody")}
            lines.append(f"{f.label}: {', '.join(str(names.get(str(v), v)) for v in spec['in'])}")
        elif "contains" in spec:
            lines.append(f"{f.label} contains “{spec['contains']}”")
        elif "is" in spec:
            lines.append(f"{f.label}: {'Yes' if spec['is'] else 'No'}")
        elif "next_days" in spec:
            lines.append(f"{f.label} in the next {spec['next_days']} days")
        elif "last_days" in spec:
            lines.append(f"{f.label} in the last {spec['last_days']} days")
        elif spec.get("before_today"):
            lines.append(f"{f.label} before today")
        elif "from" in spec or "to" in spec:
            lines.append(f"{f.label} between {spec.get('from') or '…'} and {spec.get('to') or '…'}")
        elif "min" in spec or "max" in spec:
            lines.append(f"{f.label} from {spec.get('min', '…')} to {spec.get('max', '…')}")
    return lines


def _officers():
    return get_user_model().objects.filter(is_active=True, groups__name__in=[ADMINISTRATORS, SURVEYORS]).distinct()


def _read_form(post, ds):
    """Turn the submitted form into report settings, with a list of problems."""
    errors = []
    chosen = [f.key for f in ds.fields if post.get(f"col_{f.key}")]

    def position(key):
        try:
            return int(post.get(f"pos_{key}") or 999)
        except ValueError:
            return 999
    columns = sorted(chosen, key=lambda k: (position(k), [f.key for f in ds.fields].index(k)))
    if not columns:
        errors.append(_("Choose at least one column."))
    filters = {}
    for f in ds.fields:
        if not f.filterable:
            continue
        k = f"f_{f.key}"
        if f.type in ("choice", "user"):
            values = post.getlist(k)
            if values:
                filters[f.key] = {"in": values}
        elif f.type == "text":
            if post.get(k, "").strip():
                filters[f.key] = {"contains": post[k].strip()}
        elif f.type == "bool":
            if post.get(k) in ("yes", "no"):
                filters[f.key] = {"is": post[k] == "yes"}
        elif f.type in datasets.NUMERIC:
            spec = {}
            for end in ("min", "max"):
                raw = post.get(f"{k}_{end}", "").strip().replace(",", "").replace("£", "")
                if raw:
                    try:
                        spec[end] = float(Decimal(raw))
                    except Exception:
                        errors.append(_("%(label)s: enter a number.") % {"label": f.label})
            if spec:
                filters[f.key] = spec
        elif f.type == "date":
            mode = post.get(f"{k}_mode", "")
            if mode in ("next", "last"):
                days = post.get(f"{k}_days", "").strip()
                if days.isdigit():
                    filters[f.key] = {f"{mode}_days": int(days)}
                else:
                    errors.append(_("%(label)s: enter a number of days.") % {"label": f.label})
            elif mode == "before_today":
                filters[f.key] = {"before_today": True}
            elif mode == "between":
                spec = {e: post.get(f"{k}_{e}") for e in ("from", "to") if post.get(f"{k}_{e}")}
                if spec:
                    filters[f.key] = spec
    sort_by = post.get("sort_by", "")
    if sort_by and not (ds.field(sort_by) and ds.field(sort_by).filterable):
        sort_by = ""
    return {
        "name": post.get("name", "").strip()[:120], "description": post.get("description", "").strip()[:255],
        "columns": columns, "filters": filters, "sort_by": sort_by,
        "sort_descending": post.get("sort_descending") == "1", "show_totals": post.get("show_totals") == "1",
        "shared": post.get("shared") == "1",
    }, errors


def _form_context(ds, report, errors=None):
    columns = report.columns
    filter_rows = []
    for f in ds.fields:
        if not f.filterable:
            continue
        spec = (report.filters or {}).get(f.key, {})
        row = {"field": f, "spec": spec}
        if f.type == "user":
            row["options"] = [("none", _("Nobody"))] + [(str(u.pk), u.get_full_name() or u.username) for u in _officers()]
        elif f.type == "choice":
            row["options"] = f.choices
        if f.type == "date":
            mode = ("next" if "next_days" in spec else "last" if "last_days" in spec else "before_today"
                    if spec.get("before_today") else "between" if ("from" in spec or "to" in spec) else "")
            row["mode"], row["days"] = mode, spec.get("next_days", spec.get("last_days", ""))
        filter_rows.append(row)
    return {
        "dataset": ds, "report": report, "errors": errors or [],
        "columns": [(f, f.key in columns, (columns.index(f.key) + 1) if f.key in columns else "") for f in ds.fields],
        "filter_rows": filter_rows, "date_modes": DATE_MODES,
        "sortable": [f for f in ds.fields if f.filterable],
    }


@login_required
def report_new(request):
    ds = datasets.get(request.GET.get("dataset", ""))
    if ds is None:
        return render(request, "reports/report_choose.html", {"datasets": datasets.registry().values()})
    report = Report(dataset=ds.key, columns=ds.default_columns, owner=request.user)
    return _edit(request, ds, report, new=True)


@login_required
def report_edit(request, pk):
    report = _get_visible(request, pk)
    if not report.can_change(request.user):
        raise PermissionDenied
    return _edit(request, datasets.get(report.dataset), report)


def _edit(request, ds, report, new=False):
    errors = []
    if request.method == "POST":
        data, errors = _read_form(request.POST, ds)
        for k, v in data.items():
            setattr(report, k, v)
        if not report.name:
            errors.insert(0, _("Give the report a name."))
        if not errors:
            if new:
                report.owner = request.user
            report.save()
            messages.success(request, _("Report saved."))
            return redirect(report)
    ctx = _form_context(ds, report, errors)
    ctx["new"] = new
    return render(request, "reports/report_edit.html", ctx)


@login_required
@require_POST
def report_copy(request, pk):
    original = _get_visible(request, pk)
    copy = Report.objects.create(
        name=(_("Copy of %(name)s") % {"name": original.name})[:120], description=original.description,
        dataset=original.dataset, columns=original.columns, filters=original.filters, sort_by=original.sort_by,
        sort_descending=original.sort_descending, show_totals=original.show_totals, owner=request.user)
    messages.success(request, _("Report copied. You can now change it."))
    return redirect("reports:edit", copy.pk)


@login_required
@require_POST
def report_delete(request, pk):
    report = _get_visible(request, pk)
    if not report.can_change(request.user) or report.starter:
        raise PermissionDenied
    report.delete()
    messages.success(request, _("Report deleted."))
    return redirect("reports:list")
