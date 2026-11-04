# SPDX-License-Identifier: AGPL-3.0-or-later
"""Import hub: choose what to import, download its template, upload, preview and confirm."""
import os
import uuid

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from apps.core.access import can_do_finance, scope
from apps.core.roles import is_administrator

from .sheets import WORKBOOKS

IMPORT_DIR = "imports"
MAX_BYTES = 10 * 1024 * 1024


FINANCE_IMPORTS = {"receipts": "ledger", "expenditure": "servicecharges"}


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
        return [wb for wb in found
                if wb.key in FINANCE_IMPORTS and scope(user, FINANCE_IMPORTS[wb.key], settings) == "full"]
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


@importers_only
def hub(request):
    return render(request, "imports/hub.html", {"workbooks": _available(request.user)})


@importers_only
def template(request, key):
    cls = _workbook(request, key)
    response = HttpResponse(cls().template(),
                            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="phaema-{key}-import-template.xlsx"'
    return response


@importers_only
@require_http_methods(["GET", "POST"])
def upload(request, key):
    cls = _workbook(request, key)
    session_key = f"import_{key}"
    ctx = {"workbook": cls}
    if request.method == "POST" and "confirm" in request.POST:
        stored = request.session.get(session_key, {})
        if stored.get("token") != request.POST.get("token") or not default_storage.exists(stored.get("path", "")):
            messages.error(request, _("That import has expired. Please upload the file again."))
            return redirect("imports:upload", key)
        workbook = cls()
        with default_storage.open(stored["path"], "rb") as fh:
            fh.name = stored["name"]
            result, prepared = workbook.validate(fh)
        default_storage.delete(stored["path"])
        request.session.pop(session_key, None)
        if not result.ok:
            messages.error(request, _("The records changed since the preview. Please upload the file again."))
            return redirect("imports:upload", key)
        workbook.apply(prepared)
        parts = [_("%(label)s: %(c)s added, %(u)s updated") % {"label": label, "c": c, "u": u}
                 for label, c, u, _n in result.summary()]
        messages.success(request, _("Import complete. ") + "; ".join(parts) + ".")
        return redirect("imports:hub")

    if request.method == "POST" and request.FILES.get("file"):
        uploaded = request.FILES["file"]
        try:
            if uploaded.size > MAX_BYTES:
                raise ValidationError(_("The file must be smaller than 10 MB."))
            result, _prepared = cls().validate(uploaded)
            if not result.rows:
                raise ValidationError(_("The file has no rows to import."))
        except ValidationError as exc:
            ctx["file_error"] = " ".join(exc.messages)
        else:
            ctx.update(result=result, filename=uploaded.name)
            if result.ok:
                token = uuid.uuid4().hex
                uploaded.seek(0)
                ext = os.path.splitext(uploaded.name)[1].lower()
                path = default_storage.save(f"{IMPORT_DIR}/{token}{ext}", uploaded)
                request.session[session_key] = {"token": token, "path": path, "name": uploaded.name}
                ctx["token"] = token
    elif request.method == "POST":
        ctx["file_error"] = _("Choose a file to upload.")
    return render(request, "imports/upload.html", ctx)
