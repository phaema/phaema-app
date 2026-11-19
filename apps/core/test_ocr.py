# SPDX-License-Identifier: AGPL-3.0-or-later
"""Recognising the text in scanned PDFs: queued on save, read by the scheduler's command, shown in the viewer."""
import io
import shutil

import pytest
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client

from apps.core import ocr
from apps.core.models import ModuleSettings, TextCopy
from apps.properties.models import Property, PropertyPlan

BROWSER = {"HTTP_ACCEPT": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
LINES = ["THIS LEASE is made on 1 April 2019", "BETWEEN Exampleton Borough Council (the Landlord)",
         "and Example Trading Limited (the Tenant)", "The initial rent is twelve thousand pounds a year"]
has_tesseract = pytest.mark.skipif(bool(ocr.missing()), reason="Tesseract or OCRmyPDF is not installed")


def scanned_pdf(pages=1):
    """A PDF that is only page images, like a scan."""
    import img2pdf
    from PIL import Image, ImageDraw, ImageFont

    images = []
    for _n in range(pages):
        im = Image.new("L", (1654, 2339), 255)
        draw = ImageDraw.Draw(im)
        try:
            font = ImageFont.truetype("DejaVuSerif.ttf", 34)
        except OSError:
            font = ImageFont.load_default(size=34)
        for i, line in enumerate(LINES):
            draw.text((150, 200 + 70 * i), line, fill=0, font=font)
        buf = io.BytesIO()
        im.save(buf, format="PNG", dpi=(200, 200))
        images.append(buf.getvalue())
    return img2pdf.convert(images)


def typed_pdf():
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", size=12)
    for line in LINES:
        pdf.cell(0, 10, line, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def text_of(data):
    from pdfminer.high_level import extract_text

    return " ".join(extract_text(io.BytesIO(data)).split())


@pytest.fixture
def hall(db):
    return Property.objects.create(name="Market Hall", address_line_1="1 High Street")


def add_plan(prop, data, name="Lease plan.pdf", capture=None):
    plan = PropertyPlan(property=prop, title="Lease plan",
                        file=SimpleUploadedFile(name, data, content_type="application/pdf"))
    plan.save()
    return plan


def _client(user):
    client = Client(HTTP_HOST="localhost")
    client.force_login(user)
    return client


def test_saving_a_pdf_queues_it(hall, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        plan = add_plan(hall, typed_pdf())
    item = TextCopy.objects.get(source=plan.file.name)
    assert item.status == TextCopy.Status.WAITING


def test_switched_off_nothing_is_queued(hall, django_capture_on_commit_callbacks):
    ms = ModuleSettings.load()
    ms.ocr_enabled = False
    ms.save()
    with django_capture_on_commit_callbacks(execute=True):
        add_plan(hall, typed_pdf())
    assert not TextCopy.objects.exists()
    assert ocr.process() == {}


@has_tesseract
def test_typed_pdf_is_left_alone(hall):
    plan = add_plan(hall, typed_pdf())
    ocr.queue(plan.file.name)
    assert ocr.process() == {"has_text": 1}
    item = TextCopy.objects.get()
    assert item.status == TextCopy.Status.HAS_TEXT and item.copy == "" and item.pages == 1


@has_tesseract
def test_scan_is_read_and_the_viewer_uses_the_copy(hall, make_user):
    plan = add_plan(hall, scanned_pdf())
    original = plan.file.read()
    assert "LEASE" not in text_of(original)
    ocr.queue(plan.file.name)
    call_command("ocr_scans", stdout=io.StringIO())
    item = TextCopy.objects.get()
    assert item.status == TextCopy.Status.DONE, item.error
    assert item.copy.endswith(".text.pdf") and default_storage.exists(item.copy)
    assert item.pages == 1 and item.pages_scanned == 1 and item.characters > 100 and not item.poor

    client = _client(make_user("v.sam", "Surveyors"))
    url = f"/files/{plan.file.name}"
    page = client.get(url, **BROWSER).content.decode()
    assert 'data-scan="done"' in page and "download the searchable copy" in page
    raw = b"".join(client.get(url + "?raw=1").streaming_content)
    assert "THIS LEASE is made on 1 April 2019" in text_of(raw)
    download = b"".join(client.get(url + "?download=1").streaming_content)
    assert download == original                       # the original scan stays the document of record
    searchable = b"".join(client.get(url + "?download=1&searchable=1").streaming_content)
    assert searchable == raw


def test_viewer_says_when_a_scan_is_waiting(hall, make_user):
    plan = add_plan(hall, scanned_pdf())
    ocr.queue(plan.file.name)
    page = _client(make_user("v.sam", "Surveyors")).get(f"/files/{plan.file.name}", **BROWSER).content.decode()
    assert 'data-scan="waiting"' in page and "has not been recognised yet" in page


@has_tesseract
def test_too_many_pages(hall, settings):
    settings.PHAEMA_OCR_MAX_PAGES = 1
    plan = add_plan(hall, scanned_pdf(pages=2))
    ocr.queue(plan.file.name)
    ocr.process()
    item = TextCopy.objects.get()
    assert item.status == TextCopy.Status.TOO_BIG and item.pages == 2


def test_read_poorly():
    assert not ocr.read_poorly("THIS LEASE is made on 1 April 2019 between Exampleton Borough Council (the "
                               "Landlord) and Example Trading Limited at a rent of £12,000.", 1)
    assert ocr.read_poorly("ok", 1)
    assert ocr.read_poorly("~r#% ]]i;{ 4&^gh ,,.; ¬¦~ |||| 3$@ " * 10, 1)


def test_without_tesseract_files_wait(hall, monkeypatch):
    plan = add_plan(hall, scanned_pdf())
    ocr.queue(plan.file.name)
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert "Tesseract" in ocr.process()["missing"]
    assert TextCopy.objects.get().status == TextCopy.Status.WAITING


def test_damaged_pdf_fails_after_three_tries(hall, monkeypatch):
    monkeypatch.setattr(ocr, "missing", lambda: "")
    plan = add_plan(hall, b"%PDF-1.4 not really a pdf")
    ocr.queue(plan.file.name)
    for _ in range(3):
        ocr.process()
    item = TextCopy.objects.get()
    assert item.status == TextCopy.Status.FAILED and item.attempts == 3 and item.error


def test_backlog_and_tidy(hall):
    first = add_plan(hall, typed_pdf())
    add_plan(hall, typed_pdf(), name="Second.pdf")
    assert ocr.backlog() == 2 and ocr.backlog() == 0
    item = TextCopy.objects.get(source=first.file.name)
    item.status = TextCopy.Status.DONE
    item.copy = default_storage.save(ocr.copy_name(item.source), io.BytesIO(b"%PDF-1.4"))
    item.save()
    default_storage.delete(first.file.name)
    assert ocr.tidy() == 1
    assert not default_storage.exists(item.copy) and TextCopy.objects.count() == 1


def test_manage_data_page(client, hall, make_user, monkeypatch):
    plan = add_plan(hall, typed_pdf())
    item = ocr.queue(plan.file.name)
    item.status = TextCopy.Status.FAILED
    item.save()
    make_user("boss", "Administrators")
    client.login(username="boss", password="a-long-test-password")
    monkeypatch.setattr(ocr, "missing", lambda: "Tesseract is not installed on the server.")
    page = client.get("/admin/core/textcopy/", follow=True).content.decode()
    assert "Tesseract is not installed" in page and "Lease plan" in page or plan.file.name.rsplit("/", 1)[-1] in page
    client.post("/admin/core/textcopy/", {"action": "read_again", "_selected_action": [item.pk]})
    item.refresh_from_db()
    assert item.status == TextCopy.Status.WAITING and item.attempts == 0


@has_tesseract
def test_confidential_project_scan_stays_with_the_project(make_user):
    from apps.projects import workflow
    from apps.projects.models import Project, ProjectType

    lead = make_user("v.lead", "Surveyors")
    project = workflow.start(Project(name="Northgate regeneration", confidential=True, lead=lead,
                                     project_type=ProjectType.objects.get(code="development")), lead)
    client = _client(lead)
    client.post(project.get_absolute_url(), {"action": "add_document", "title": "Heads of terms",
                                             "file": SimpleUploadedFile("hot.pdf", scanned_pdf(),
                                                                        content_type="application/pdf")})
    document = project.documents.get()
    ocr.queue(document.file.name)
    ocr.process()
    item = TextCopy.objects.get()
    assert item.status == TextCopy.Status.DONE and item.copy.startswith("projects/")
    url = f"/projects/{project.pk}/files/document/{document.pk}/"
    assert 'data-scan="done"' in client.get(url, **BROWSER).content.decode()
    assert "THIS LEASE" in text_of(b"".join(client.get(url + "?raw=1").streaming_content))
    assert client.get(f"/files/{item.copy}").status_code == 404     # not through the general file address
