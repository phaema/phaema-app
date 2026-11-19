# SPDX-License-Identifier: AGPL-3.0-or-later
"""Recognising the text in scanned PDFs (OCR), so that Find in the document viewer works on them.

When any record saves a PDF, the stored file is queued (`queue`). The `ocr_scans` command, run every few minutes by
the scheduler, reads waiting files (`process`): a PDF whose pages already carry text is left alone; otherwise
OCRmyPDF, using the Tesseract engine, writes a copy with the recognised text laid invisibly under each page image.
Everything runs on the council's own server; no document is sent anywhere. The original is never changed: the viewer
shows the searchable copy (`serving_name`), and Download gives the original unless the copy is asked for.

Tesseract and OCRmyPDF are optional at run time: without them files stay waiting and Manage data says why.
"""
import logging
import os
import re
import shutil
import tempfile

from django.apps import apps
from django.conf import settings
from django.core.files import File
from django.core.files.storage import default_storage
from django.db import models, transaction
from django.utils import timezone

log = logging.getLogger(__name__)

MIN_TEXT_PER_PAGE = 20       # characters: fewer on a page means it is an image, not text
POOR_TEXT_PER_PAGE = 60      # characters on average across scanned pages: fewer means little was read
POOR_WORD_SHARE = 0.6        # under this share of ordinary-looking words means the text is mostly garbled
MAX_ATTEMPTS = 3


def languages():
    """Tesseract language codes, joined with "+": English by default; a Welsh council might use "eng+cym"."""
    return getattr(settings, "PHAEMA_OCR_LANGUAGES", "eng") or "eng"


def max_pages():
    return int(getattr(settings, "PHAEMA_OCR_MAX_PAGES", 500))


def missing():
    """What the server lacks for OCR, in words, or "" when everything is there."""
    try:
        import ocrmypdf  # noqa: F401
    except ImportError:
        return "The OCRmyPDF package is not installed."
    if not shutil.which("tesseract"):
        return "Tesseract is not installed on the server."
    return ""


def enabled():
    from .models import ModuleSettings

    return ModuleSettings.load().ocr_enabled


def is_pdf(name):
    return bool(name) and str(name).lower().endswith(".pdf")


def copy_name(source):
    """Where the searchable copy of a stored file goes: beside it, so a confidential project's copy stays under
    projects/ and is served only by the project pages, like the original."""
    stem, _ext = os.path.splitext(source)
    return f"{stem}.text.pdf"


def queue(name):
    """Mark a stored PDF to be read. Safe to call more than once."""
    from .models import TextCopy

    if not is_pdf(name) or name.endswith(".text.pdf") or not enabled():
        return None
    copy, _new = TextCopy.objects.get_or_create(source=name)
    return copy


def _pdf_fields(instance):
    return [f for f in instance._meta.get_fields()
            if isinstance(f, models.FileField) and not isinstance(f, models.ImageField)]


def queue_record(sender, instance, raw=False, **kwargs):
    """post_save: queue any PDF a record holds, once the save has been committed."""
    if raw or sender._meta.app_label in ("sessions", "admin", "contenttypes") or sender.__name__ == "TextCopy":
        return
    names = [getattr(instance, f.name).name for f in _pdf_fields(instance) if getattr(instance, f.name)]
    names = [n for n in names if is_pdf(n)]
    if names:
        transaction.on_commit(lambda: [queue(n) for n in names])


def backlog():
    """Queue every PDF already held, for a council's existing documents. Returns how many were added."""
    from .models import TextCopy

    if not enabled():
        return 0
    known = set(TextCopy.objects.values_list("source", flat=True))
    added = 0
    for model in apps.get_models():
        for field in _pdf_fields(model):
            for name in model._default_manager.exclude(**{field.name: ""}).values_list(field.name, flat=True):
                if is_pdf(name) and name not in known and not name.endswith(".text.pdf"):
                    TextCopy.objects.create(source=name)
                    known.add(name)
                    added += 1
    return added


def text_by_page(path):
    """Characters of text on each page of a PDF, from its own text layer."""
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTTextContainer

    counts = []
    for layout in extract_pages(path):
        counts.append(sum(len("".join(el.get_text().split())) for el in layout if isinstance(el, LTTextContainer)))
    return counts


WORDLIKE = re.compile(r"^[(\"'‘“]*([A-Za-z][A-Za-z'’-]*|\d[\d,./:-]*|£[\d,.]+|[ivxlcdm]+)[)\"'’”.,;:!?%]*$")


def read_poorly(text, scanned_pages):
    """True when the recognised text is thin or mostly garbled: few characters for the pages, or too few tokens
    that look like ordinary words and numbers (a faint or skewed scan gives strings of stray symbols)."""
    tokens = text.split()
    if len("".join(tokens)) < POOR_TEXT_PER_PAGE * max(scanned_pages, 1):
        return True
    share = sum(1 for t in tokens if WORDLIKE.match(t)) / len(tokens)
    return share < POOR_WORD_SHARE


def read_one(item):
    """Read one waiting file and record the outcome on it."""
    import ocrmypdf

    item.attempts += 1
    item.error = ""
    if not default_storage.exists(item.source):
        item.delete()
        return "gone"
    with tempfile.TemporaryDirectory(prefix="phaema-ocr-") as work:
        original = os.path.join(work, "original.pdf")
        result = os.path.join(work, "searchable.pdf")
        sidecar = os.path.join(work, "text.txt")
        with default_storage.open(item.source, "rb") as src, open(original, "wb") as out:
            shutil.copyfileobj(src, out)
        try:
            counts = text_by_page(original)
        except Exception as exc:  # damaged or password-protected
            return _failed(item, f"The PDF could not be opened: {exc}")
        item.pages = len(counts)
        scanned = [n for n in counts if n < MIN_TEXT_PER_PAGE]
        item.pages_scanned = len(scanned)
        if not scanned:
            return _finish(item, item.Status.HAS_TEXT)
        if item.pages > max_pages():
            return _finish(item, item.Status.TOO_BIG)
        try:
            code = ocrmypdf.ocr(
                original, result, language=languages().split("+"), skip_text=True, output_type="pdf",
                rasterizer="pypdfium", rotate_pages=True, deskew=False, optimize=0, sidecar=sidecar,
                progress_bar=False, jobs=int(getattr(settings, "PHAEMA_OCR_JOBS", 1)), use_threads=True,
                tesseract_timeout=float(getattr(settings, "PHAEMA_OCR_PAGE_SECONDS", 180)))
        except Exception as exc:
            return _failed(item, f"{type(exc).__name__}: {exc}")
        if int(code) != 0:
            return _failed(item, f"OCRmyPDF stopped with code {int(code)}.")
        try:
            with open(sidecar, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            text = ""
        item.characters = len("".join(text.split()))
        item.poor = read_poorly(text, len(scanned))
        target = copy_name(item.source)
        if default_storage.exists(target):
            default_storage.delete(target)
        with open(result, "rb") as fh:
            item.copy = default_storage.save(target, File(fh))
    return _finish(item, item.Status.DONE)


def _finish(item, status):
    item.status = status
    item.finished_at = timezone.now()
    item.save()
    return status


def _failed(item, message):
    log.warning("OCR failed for %s: %s", item.source, message)
    item.error = message[:2000]
    item.finished_at = timezone.now()
    item.status = item.Status.FAILED if item.attempts >= MAX_ATTEMPTS else item.Status.WAITING
    item.save()
    return "failed"


def process(limit=20):
    """Read up to `limit` waiting files. Returns {outcome: count}; {"missing": reason} when OCR is not installed."""
    from .models import TextCopy

    if not enabled():
        return {}
    reason = missing()
    if reason:
        return {"missing": reason}
    done = {}
    for item in TextCopy.objects.filter(status=TextCopy.Status.WAITING).order_by("queued_at")[:limit]:
        outcome = read_one(item)
        done[outcome] = done.get(outcome, 0) + 1
    return done


def tidy():
    """Remove searchable copies whose original has gone (a document deleted or replaced)."""
    from .models import TextCopy

    removed = 0
    for item in TextCopy.objects.exclude(status=TextCopy.Status.WAITING).iterator():
        if not default_storage.exists(item.source):
            if item.copy and default_storage.exists(item.copy):
                default_storage.delete(item.copy)
            item.delete()
            removed += 1
    return removed


def lookup(name):
    """The TextCopy for a stored file, or None."""
    from .models import TextCopy

    if not is_pdf(name):
        return None
    return TextCopy.objects.filter(source=name).first()


def serving_name(name, searchable=True):
    """The stored file to send: the searchable copy when there is one and it is wanted, else the original."""
    item = lookup(name) if searchable else None
    if item is not None and item.status == item.Status.DONE and item.copy and default_storage.exists(item.copy):
        return item.copy
    return name
