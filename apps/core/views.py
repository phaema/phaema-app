# SPDX-License-Identifier: AGPL-3.0-or-later
import mimetypes
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, SuspiciousFileOperation
from django.core.files.storage import default_storage
from django.core.paginator import Paginator
from django.db import connection
from django.db.models import Count, Sum
from django.http import FileResponse, Http404, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.http import url_has_allowed_host_and_scheme

from apps.leases import events as lease_events
from apps.leases.models import LeaseEvent
from apps.properties.models import Property

from .models import ModuleSettings, AuditEntry

TEXT_SIZES = {"smaller": "Smaller", "standard": "Standard", "large": "Large", "largest": "Largest"}
THEMES = {"standard": "Standard", "dark": "Dark", "contrast": "High contrast", "auto": "Match my device"}
SKINS = {"classic": "Classic", "clear": "Clear", "compact": "Compact"}
DASHBOARDS = ("mine", "estate")


@login_required
def dashboard(request):
    from .roles import SURVEYORS, role_of

    view = request.GET.get("view", "")
    if view not in DASHBOARDS:
        view = request.COOKIES.get("phaema_dashboard", "")
        if view not in DASHBOARDS:
            view = "mine" if role_of(request.user) == SURVEYORS else "estate"
    response = _my_work(request) if view == "mine" else _estate(request)
    if request.GET.get("view") in DASHBOARDS:
        response.set_cookie("phaema_dashboard", view, max_age=365 * 24 * 3600, samesite="Lax")
    return response


def _my_work(request):
    from . import mywork

    people = mywork.viewable(request.user)
    person = request.user
    wanted = request.GET.get("person", "")
    if wanted.isdigit():
        person = next((p for p in people if p.pk == int(wanted)), None)
        if person is None:
            raise PermissionDenied
    context = mywork.build(person, viewer=request.user)
    context.update({"view": "mine", "people": people if len(people) > 1 else [], "person": person,
                    "is_me": person == request.user})
    return render(request, "core/my_work.html", context)


def _visible_changes(user):
    from .access import audit_visible

    return audit_visible(user, AuditEntry.objects.select_related("user", "content_type"))


def _estate(request):
    P = Property
    by_type = P.objects.values("property_type").annotate(n=Count("id")).order_by("property_type")
    labels = dict(P.PropertyType.choices)

    # Lettable space = the lowest-level records (no parts of their own), so nothing is counted twice.
    leaves = (P.objects.filter(children__isnull=True).exclude(property_type=P.PropertyType.LAND)
              .exclude(occupation=P.Occupation.NOT_APPLICABLE))
    vacant_leaves = leaves.filter(occupation=P.Occupation.VACANT)
    totals = leaves.aggregate(nia=Sum("nia_sqm"))
    vacant = vacant_leaves.aggregate(nia=Sum("nia_sqm"), gia=Sum("gia_sqm"), n=Count("id"))
    vacancy_rate = None
    if totals["nia"] and vacant["nia"] is not None:
        vacancy_rate = (vacant["nia"] / totals["nia"] * 100).quantize(Decimal("0.1"))

    units = P.objects.filter(property_type=P.PropertyType.UNIT)
    context = {
        "property_count": P.objects.count(),
        "unit_count": units.count(),
        "vacant_unit_count": units.filter(occupation=P.Occupation.VACANT).count(),
        "vacant_count": P.objects.filter(occupation=P.Occupation.VACANT).count(),
        "vacant_buildings": P.objects.filter(property_type=P.PropertyType.BUILDING, occupation=P.Occupation.VACANT).count(),
        "vacant_space": vacant,
        "lettable_nia": totals["nia"],
        "vacancy_rate": vacancy_rate,
        "my_count": P.objects.filter(managing_surveyor=request.user).count(),
        "by_type": [(r["property_type"], labels.get(r["property_type"], r["property_type"]), r["n"]) for r in by_type],
        "lease_events": lease_events.event_summary(),
        "tenancies_at_will": lease_events.tenancies_at_will(),
        "essence": lease_events.essence_summary(),
        "documents_review": lease_events.documents_for_review(),
        "my_events": LeaseEvent.objects.filter(assigned_to=request.user, status__in=("open", "in_progress")).count(),
        "my_overdue": LeaseEvent.objects.filter(assigned_to=request.user, status__in=("open", "in_progress"),
                                                due_date__lt=date.today()).count(),
        "rent_roll": lease_events.rent_roll(),
        "recent_changes": _with_targets(_visible_changes(request.user)[:10]),
    }
    from apps.cases.views import cases_summary

    context["cases"] = cases_summary(request.user)
    from . import access

    settings = ModuleSettings.load()
    if access.can_use(request.user, "maintenance", settings):
        from apps.maintenance.workflow import summary

        context["maintenance"] = summary(request.user)
    if access.can_use(request.user, "valuations", settings):
        from apps.valuations.models import AuditReview, Valuation

        context["valuations"] = {
            "mine": Valuation.objects.filter(valuer__user=request.user).exclude(status="accepted").count(),
            "audits": AuditReview.objects.filter(assigned_to=request.user, status="open").count()}
    if access.can_use(request.user, "compliance", settings):
        from apps.compliance.workflow import summary as compliance_summary

        context["compliance"] = compliance_summary()
    service = access.scope(request.user, "servicecharges", settings)
    if service:
        from apps.servicecharges.deadlines import upcoming

        deadlines = upcoming()
        if service == "patch":
            mine = set(access.patch_leases(request.user).values_list("pk", flat=True))
            deadlines = [d for d in deadlines if d.schedule.members.filter(lease_id__in=mine).exists()]
        context["service_deadlines"] = deadlines
    ledger = access.scope(request.user, "ledger", settings)
    if ledger:
        from apps.ledger import billing

        leases = access.patch_leases(request.user) if ledger == "patch" else None
        summary = billing.arrears_summary(leases=leases)
        context["ledger"] = {"arrears": summary["total"], "arrears_count": summary["count"],
                             "collection": billing.collection(leases=leases), "patch": ledger == "patch"}
    context["view"] = "estate"
    return render(request, "core/dashboard.html", context)


def _target(entry):
    """The page for the record an audit entry is about, if it still exists."""
    model = entry.content_type.model_class()
    if model is None or not hasattr(model, "get_absolute_url"):
        return None
    try:
        return model.objects.get(pk=entry.object_id).get_absolute_url()
    except (model.DoesNotExist, ValueError):
        return None


def _with_targets(entries):
    entries = list(entries)
    for e in entries:
        e.target_url = _target(e)
    return entries


@login_required
def change_list(request):
    from .access import audit_visible

    qs = audit_visible(request.user, AuditEntry.objects.select_related("user", "content_type"))
    user_id = request.GET.get("user", "")
    if user_id == "system":
        qs = qs.filter(user__isnull=True)
    elif user_id.isdigit():
        qs = qs.filter(user_id=int(user_id))
    from apps.reports import datasets, export

    exported = export.download(request, "Change log", datasets.get("changes"), qs)
    if exported:
        return exported
    page = Paginator(qs, 50).get_page(request.GET.get("page"))
    page.object_list = _with_targets(page.object_list)
    users = get_user_model().objects.filter(auditentry__isnull=False).distinct().order_by("first_name", "username")
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "core/change_list.html", {"page_obj": page, "users": users, "selected_user": user_id,
                                                     "querystring": params.urlencode()})


@login_required
def change_detail(request, pk):
    from .access import audit_visible

    entry = get_object_or_404(audit_visible(request.user, AuditEntry.objects.select_related("user", "content_type")),
                              pk=pk)
    model = entry.content_type.model_class()
    rows = []
    for name, values in (entry.changes or {}).items():
        before, after = (values + [None, None])[:2] if isinstance(values, list) else (None, values)
        label, before_txt, after_txt = name, before, after
        if model is not None:
            try:
                field = model._meta.get_field(name)
                label = str(field.verbose_name)
                before_txt, after_txt = _display(field, before), _display(field, after)
            except Exception:  # field removed since the change was made
                pass
        rows.append((label, before_txt, after_txt))
    return render(request, "core/change_detail.html", {"entry": entry, "rows": rows, "target_url": _target(entry)})


def _display(field, value):
    if value in (None, ""):
        return ""
    if field.choices:
        return dict((str(k), v) for k, v in field.flatchoices).get(str(value), value)
    if field.is_relation and field.related_model is not None:
        try:
            return str(field.related_model.objects.get(pk=value))
        except Exception:
            return f"{value} (no longer exists)"
    if field.get_internal_type() == "BooleanField":
        return "Yes" if value == "True" else "No"
    if field.get_internal_type() == "MultiPolygonField":
        return "Boundary drawn"
    return value


@login_required
def protected_file(request, path):
    """Serve uploaded photos and documents to signed-in users only. Project papers are served by the project pages,
    which check that the person can see the project."""
    if path.startswith("projects/"):
        raise Http404
    try:
        if not default_storage.exists(path):
            raise Http404
        handle = default_storage.open(path, "rb")
    except SuspiciousFileOperation:
        raise Http404
    content_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
    inline = content_type in ("application/pdf", "image/jpeg", "image/png")
    response = FileResponse(handle, content_type=content_type, as_attachment=not inline,
                            filename=path.rsplit("/", 1)[-1])
    response["Cache-Control"] = "private, max-age=3600"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def _remember(request, cookie, value):
    target = request.GET.get("next") or "/"
    if not url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        target = "/"
    response = HttpResponseRedirect(target)
    response.set_cookie(cookie, value, max_age=365 * 24 * 3600, samesite="Lax")
    return response


def set_text_size(request, size):
    if size not in TEXT_SIZES:
        raise Http404
    return _remember(request, "phaema_text_size", size)


def set_skin(request, skin):
    if skin not in SKINS:
        raise Http404
    return _remember(request, "phaema_skin", skin)


def set_theme(request, theme):
    if theme not in THEMES:
        raise Http404
    return _remember(request, "phaema_theme", theme)


def health(request):
    """Used by the container health check."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return JsonResponse({"status": "ok"})
