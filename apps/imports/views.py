# SPDX-License-Identifier: AGPL-3.0-or-later
"""Import hub: choose what to import, download its template, upload, preview, try it out and confirm; and the record
of trial and real runs with their reports and sign-off."""
import os
import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.storage import default_storage
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods, require_POST

from apps.core.access import can_do_finance, scope
from apps.core.roles import is_administrator

from .sheets import WORKBOOKS

IMPORT_DIR = "imports"
MAX_BYTES = 10 * 1024 * 1024


FINANCE_IMPORTS = {"receipts": "ledger", "expenditure": "servicecharges", "project_spending": None}


def _available(user):
    """What this person may import: administrators, everything switched on; finance staff, receipts and service
    charge spending for modules they can open in full."""
    from apps.core.models import ModuleSettings

    settings = ModuleSettings.load()
    needs = {"receipts": settings.rent_ledger_enabled, "expenditure": settings.service_charges_enabled,
             "maintenance": settings.maintenance_enabled, "valuations": settings.valuation_enabled}
    found = [wb for wb in WORKBOOKS.values() if needs.get(wb.key, True)]
    if is_administrator(user):
        return found
    if can_do_finance(user):
        return [wb for wb in found if wb.key in FINANCE_IMPORTS and (
            FINANCE_IMPORTS[wb.key] is None or scope(user, FINANCE_IMPORTS[wb.key], settings) == "full")]
    return []


def importers_only(view):
    """Administrators, and finance staff for the finance imports."""
    from functools import wraps

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not _available(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return login_required(wrapped)


def _workbook(request, key):
    cls = next((wb for wb in _available(request.user) if wb.key == key), None)
    if cls is None:
        raise Http404
    return cls


def _adapter(request, key):
    from .migration import adapters_for

    found = next((a for a in adapters_for(request.user) if a.key == key), None)
    if found is None:
        raise Http404
    return found


@importers_only
def hub(request):
    from .models import MigrationRun

    kinds = {a.key for a in _adapters(request)}
    return render(request, "imports/hub.html", {
        "workbooks": _available(request.user),
        "runs": MigrationRun.objects.filter(kind__in=kinds).select_related("run_by", "signed_off_by")[:5]})


def _adapters(request):
    from .migration import adapters_for

    return adapters_for(request.user)


@importers_only
def template(request, key):
    cls = _workbook(request, key)
    response = HttpResponse(cls().template(),
                            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="phaema-{key}-import-template.xlsx"'
    return response


def _session_key(key):
    return "property_import" if key == "properties" else f"import_{key}"


def _stored(request, key):
    """The file uploaded for checking, if it is still there."""
    stored = request.session.get(_session_key(key), {})
    if stored.get("path") and default_storage.exists(stored["path"]):
        return stored
    return None


def _open(stored):
    fh = default_storage.open(stored["path"], "rb")
    fh.name = stored["name"]
    return fh


def _forget(request, key):
    stored = request.session.pop(_session_key(key), None)
    if stored and stored.get("path") and default_storage.exists(stored["path"]):
        default_storage.delete(stored["path"])


def handle(request, adapter, template_name, done_url):
    """Upload and check a file; try it out; import it. Shared by the property import and the hub's workbooks."""
    from . import migration
    from .models import MigrationRun

    key = adapter.key
    ctx = {"workbook": adapter, "adapter": adapter}
    if request.method == "POST" and ("confirm" in request.POST or "trial" in request.POST):
        stored = _stored(request, key)
        if not stored or stored.get("token") != request.POST.get("token") or not stored.get("ok"):
            messages.error(request, _("That import has expired. Please upload the file again."))
            return redirect(request.path)
        mode = MigrationRun.Mode.TRIAL if "trial" in request.POST else MigrationRun.Mode.LIVE
        with _open(stored) as fh:
            outcome = adapter.check(fh)
            if not outcome.ok:
                _forget(request, key)
                messages.error(request, _("The records changed since the preview. Please upload the file again."))
                return redirect(request.path)
            expected = migration.expected_from(request.POST, outcome.controls)
            fh.seek(0)
            record, outcome = migration.run(adapter, fh, mode, request.user, expected)
        if mode == MigrationRun.Mode.TRIAL:
            stored["expected"] = {k: str(v) for k, v in expected.items()}
            request.session[_session_key(key)] = stored
            messages.success(request, _("Trial run finished: nothing was saved. Check the figures below, then "
                                        "import the file for real when you are ready."))
            return redirect(record)
        _forget(request, key)
        parts = [_("%(label)s: %(c)s added, %(u)s updated") % {"label": label, "c": c, "u": u}
                 for label, c, u, _n in outcome.summary]
        messages.success(request, _("Import complete. ") + "; ".join(parts) + ".")
        if record.mismatches:
            messages.warning(request, _("Some control totals do not match. See the import record."))
        return redirect(done_url)

    if request.method == "POST" and request.FILES.get("file"):
        uploaded = request.FILES["file"]
        try:
            if uploaded.size > MAX_BYTES:
                raise ValidationError(_("The file must be smaller than 10 MB."))
            outcome = adapter.check(uploaded)
            if not outcome.rows:
                raise ValidationError(_("The file has no rows to import."))
        except ValidationError as exc:
            ctx["file_error"] = " ".join(exc.messages)
        else:
            _forget(request, key)
            token = uuid.uuid4().hex
            uploaded.seek(0)
            ext = os.path.splitext(uploaded.name)[1].lower()
            path = default_storage.save(f"{IMPORT_DIR}/{token}{ext}", uploaded)
            request.session[_session_key(key)] = {"token": token, "path": path, "name": uploaded.name,
                                                  "ok": outcome.ok}
            ctx.update(result=outcome.result, outcome=outcome, filename=uploaded.name, check_token=token)
            if outcome.ok:
                ctx["token"] = token
    elif request.method == "POST":
        ctx["file_error"] = _("Choose a file to upload.")
    return render(request, template_name, ctx)


@importers_only
@require_http_methods(["GET", "POST"])
def upload(request, key):
    from django.urls import reverse

    adapter = _adapter(request, key)
    if key == "properties":
        return redirect("properties:import")
    return handle(request, adapter, "imports/upload.html", reverse("imports:hub"))


@importers_only
def check_report(request, key):
    """The checked file as an Excel report of every row, whether or not it has problems."""
    from .migration import report

    adapter = _adapter(request, key)
    stored = _stored(request, key)
    if not stored or stored.get("token") != request.GET.get("token"):
        raise Http404
    with _open(stored) as fh:
        outcome = adapter.check(fh)
    response = HttpResponse(report(outcome, title=adapter.title, filename=stored["name"]),
                            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="phaema-{key}-check.xlsx"'
    return response


def _run(request, pk):
    from .models import MigrationRun

    record = get_object_or_404(MigrationRun.objects.select_related("run_by", "signed_off_by"), pk=pk)
    if record.kind not in {a.key for a in _adapters(request)}:
        raise Http404
    return record


@importers_only
def runs(request):
    from .models import MigrationRun

    kinds = {a.key for a in _adapters(request)}
    return render(request, "imports/runs.html", {
        "runs": MigrationRun.objects.filter(kind__in=kinds).select_related("run_by", "signed_off_by")[:200]})


@importers_only
def run_detail(request, pk):
    record = _run(request, pk)
    stored = _stored(request, record.kind)
    same_file = bool(stored and stored.get("ok") and record.mode == "trial" and not record.signed_off_at
                     and _fingerprint(stored) == record.file_sha256)
    return render(request, "imports/run.html", {
        "run": record, "can_import": same_file, "token": stored["token"] if same_file else "",
        "expected": (stored or {}).get("expected", {}),
        "can_sign_off": is_administrator(request.user) and not record.signed_off_at
        and record.run_by_id != request.user.pk,
        "upload_url": _upload_url(record.kind)})


def _upload_url(kind):
    from django.urls import reverse

    return reverse("properties:import") if kind == "properties" else reverse("imports:upload", args=[kind])


def _fingerprint(stored):
    from .migration import fingerprint

    with _open(stored) as fh:
        return fingerprint(fh)


@importers_only
def run_report(request, pk):
    record = _run(request, pk)
    if not record.report:
        raise Http404
    return FileResponse(record.report.open("rb"), as_attachment=True, filename=f"phaema-migration-{record.pk}.xlsx")


@importers_only
@require_POST
def run_sign_off(request, pk):
    from .migration import sign_off

    record = _run(request, pk)
    if not is_administrator(request.user):
        raise PermissionDenied
    try:
        sign_off(record, request.user, request.POST.get("note", ""))
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, _("Signed off."))
    return redirect(record)
