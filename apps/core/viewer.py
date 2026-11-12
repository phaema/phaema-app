# SPDX-License-Identifier: AGPL-3.0-or-later
"""Showing PDFs inside PHAEMA.

A PDF that a person opens in their browser is shown in PHAEMA's own viewer page (PDF.js), with the name of the
document, a way back to the record it belongs to, and a download button. The viewer then fetches the file itself.
Anything that is not a browser opening a page (the viewer's own request, the API, a script) gets the file as before.
"""
from django.apps import apps
from django.db import models
from django.shortcuts import render
from django.utils.cache import patch_vary_headers
from django.utils.http import url_has_allowed_host_and_scheme

TITLE_FIELDS = ("title", "description", "name", "caption")


def wants_viewer(request, content_type):
    """True when a person has opened a PDF as a page, and has not asked for the file itself."""
    if content_type != "application/pdf" or request.method != "GET":
        return False
    if "raw" in request.GET or "download" in request.GET:
        return False
    return "text/html" in request.headers.get("Accept", "")


def wants_download(request):
    return "download" in request.GET


def _file_fields():
    """Every file field in PHAEMA (not photos), found once."""
    if not hasattr(_file_fields, "found"):
        _file_fields.found = [
            (model, field.name) for model in apps.get_models() for field in model._meta.get_fields()
            if isinstance(field, models.FileField) and not isinstance(field, models.ImageField)]
    return _file_fields.found


def _record_of(item):
    """The record a document belongs to: the first thing it points at that has a page, else itself."""
    for field in item._meta.get_fields():
        if isinstance(field, models.ForeignKey):
            target = getattr(item, field.name, None)
            if target is not None and hasattr(target, "get_absolute_url"):
                return target
    return item if hasattr(item, "get_absolute_url") else None


def describe(path=None, item=None):
    """What to call a stored file and where it belongs: {"title", "filename", "record"}.

    Files are stored under made-up names, so the name people know comes from the record that holds the file."""
    if item is None and path:
        for model, name in _file_fields():
            item = model._default_manager.filter(**{name: path}).first()
            if item is not None:
                break
    fallback = (path or "document.pdf").rsplit("/", 1)[-1]
    if item is None:
        return {"title": fallback, "filename": fallback, "record": None}
    title = next((value for value in (getattr(item, f, "") for f in TITLE_FIELDS) if value and isinstance(value, str)), "")
    original = getattr(item, "original_filename", "") or ""
    named = str(item) if type(item).__str__ is not models.Model.__str__ else ""
    title = title or named or original or fallback
    filename = original or f"{title}.pdf"
    if not filename.lower().endswith(".pdf"):
        filename += ".pdf"
    filename = "".join(c if c.isalnum() or c in " .-_()" else "-" for c in filename).strip() or fallback
    return {"title": title, "filename": filename, "record": _record_of(item)}


def page(request, about):
    """The viewer page for the PDF at this same address."""
    record = about["record"]
    back, back_label = None, ""
    if record is not None:
        back, back_label = record.get_absolute_url(), " ".join(str(record).split())
    else:
        referer = request.headers.get("Referer", "")
        if referer and url_has_allowed_host_and_scheme(referer, allowed_hosts={request.get_host()},
                                                       require_https=request.is_secure()):
            back = referer
    response = render(request, "core/pdf_view.html", {
        "title": about["title"], "back": back, "back_label": back_label,
        "raw_url": request.path + "?raw=1", "download_url": request.path + "?download=1"})
    response["Cache-Control"] = "private, no-store"
    patch_vary_headers(response, ["Accept"])     # the same address gives the page or the file
    return response
