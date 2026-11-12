# SPDX-License-Identifier: AGPL-3.0-or-later
"""Drag and drop filing: several files at once on cases, agreements and properties, and drop zones on file choosers."""
from datetime import date
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from apps.cases.models import Case, CaseDocument, CaseType, Correspondence
from apps.core.files import MAX_FILES_AT_ONCE, title_from_filename
from apps.core.roles import ADMINISTRATORS, SURVEYORS, VIEWERS
from apps.leases.models import Lease, LeaseDocument, Party
from apps.properties.models import Property

PDF = b"%PDF-1.4 a document"
EML = (b"From: Ann Carpenter <ann@acme.example>\r\nTo: estates@council.example\r\n"
       b"Subject: Our application\r\nDate: Mon, 02 Nov 2026 10:00:00 +0000\r\n"
       b"Content-Type: text/plain\r\n\r\nPlease see our application.\r\n")


def png():
    out = BytesIO()
    Image.new("RGB", (40, 30), "navy").save(out, "PNG")
    return out.getvalue()


def messages_of(response):
    return " ".join(str(m) for m in response.context["messages"])


@pytest.fixture
def world(db, make_user):
    sue = make_user("sue", SURVEYORS)
    prop = Property.objects.create(reference="T-1", name="Mill Yard", property_type="building", managing_surveyor=sue)
    tenant = Party.objects.create(name="Acme Joinery Ltd", party_type="company")
    lease = Lease.objects.create(reference="L-1", agreement_type="lease", counterparty=tenant,
                                 term_start=date(2022, 1, 1), term_end=date(2032, 1, 1))
    lease.properties.add(prop)
    case = Case.objects.create(case_type=CaseType.objects.get(code="alterations"), title="New mezzanine", lease=lease,
                               owner=sue)
    return {"sue": sue, "prop": prop, "lease": lease, "case": case, "other": make_user("other", SURVEYORS),
            "vic": make_user("vic", VIEWERS)}


def test_titles_come_from_file_names():
    assert title_from_filename("Ground_floor-plan.pdf") == "Ground floor plan"
    assert title_from_filename("C:\\scans\\Lease  signed.PDF") == "Lease signed"
    assert title_from_filename(".pdf") == "Untitled" and title_from_filename("notes") == "notes"


# Cases: documents and saved emails together

def test_case_takes_documents_and_emails_in_one_go(client, world):
    client.force_login(world["sue"])
    case = world["case"]
    page = client.get(case.get_absolute_url()).content.decode()
    assert 'name="files" type="file" multiple' in page and "File documents and emails" in page
    assert page.count('data-module="govuk-file-upload"') >= 4  # the drop area and each single-file chooser
    response = client.post(case.get_absolute_url(), {
        "action": "file_dropped", "direction": "in",
        "files": [SimpleUploadedFile("Mezzanine_drawing.pdf", PDF), SimpleUploadedFile("Application.eml", EML),
                  SimpleUploadedFile("virus.exe", b"MZ")]}, follow=True)
    said = messages_of(response)
    assert "Filed on this case: 1 document and 1 email." in said and "Not filed: virus.exe:" in said
    assert CaseDocument.objects.get(case=case).description == "Mezzanine drawing"
    email = Correspondence.objects.get(case=case)
    assert email.subject == "Our application" and "ann@acme.example" in email.correspondent
    assert email.on == date(2026, 11, 2) and email.direction == "in"


def test_case_drop_needs_a_file_and_is_limited(client, world):
    client.force_login(world["sue"])
    case = world["case"]
    assert "Choose or drop at least one file." in messages_of(
        client.post(case.get_absolute_url(), {"action": "file_dropped"}, follow=True))
    many = [SimpleUploadedFile(f"doc{n}.pdf", PDF) for n in range(MAX_FILES_AT_ONCE + 2)]
    said = messages_of(client.post(case.get_absolute_url(), {"action": "file_dropped", "files": many}, follow=True))
    assert CaseDocument.objects.filter(case=case).count() == MAX_FILES_AT_ONCE
    assert "Only the first 20 files were filed" in said


def test_viewer_cannot_file_on_a_case(client, world):
    client.force_login(world["vic"])
    case = world["case"]
    assert "File documents and emails" not in client.get(case.get_absolute_url()).content.decode()
    response = client.post(case.get_absolute_url(), {"action": "file_dropped",
                                                     "files": [SimpleUploadedFile("a.pdf", PDF)]})
    assert response.status_code == 403 and not CaseDocument.objects.exists()


# Agreements: PDFs

def test_agreement_takes_several_pdfs(client, world):
    client.force_login(world["sue"])
    lease = world["lease"]
    page = client.get(lease.get_absolute_url()).content.decode()
    assert reverse("leases:files", args=[lease.pk]) in page and 'id="lease-files"' in page
    response = client.post(reverse("leases:files", args=[lease.pk]), {
        "document_type": "variation",
        "files": [SimpleUploadedFile("Deed of variation 2024.pdf", PDF), SimpleUploadedFile("Side letter.pdf", PDF),
                  SimpleUploadedFile("photo.pdf", b"not really a pdf")]}, follow=True)
    said = messages_of(response)
    assert "2 documents filed on this agreement." in said and "Not filed: photo.pdf:" in said
    docs = LeaseDocument.objects.filter(lease=lease)
    assert sorted(d.description for d in docs) == ["Deed of variation 2024", "Side letter"]
    assert {d.document_type for d in docs} == {"variation"}
    assert docs[0].original_filename.endswith(".pdf")


def test_agreement_files_need_edit_rights(client, world):
    url = reverse("leases:files", args=[world["lease"].pk])
    for who in ("vic", "other"):
        client.force_login(world[who])
        assert client.post(url, {"files": [SimpleUploadedFile("a.pdf", PDF)]}).status_code == 403
    assert client.get(url).status_code == 405 and not LeaseDocument.objects.exists()
    client.force_login(world["vic"])
    assert 'id="lease-files"' not in client.get(world["lease"].get_absolute_url()).content.decode()


# Properties: floor plans and photos

def test_property_takes_plans_and_photos(client, world):
    client.force_login(world["sue"])
    prop = world["prop"]
    url = reverse("properties:files", args=[prop.pk])
    page = client.get(prop.get_absolute_url()).content.decode()
    assert url in page and 'id="plan-files"' in page and 'id="photo-files"' in page
    said = messages_of(client.post(url, {"kind": "plans", "files": [
        SimpleUploadedFile("Ground_floor.pdf", PDF), SimpleUploadedFile("Site.dwg", b"AC1032" + b"\x00" * 20),
        SimpleUploadedFile("notes.docx", b"PK")]}, follow=True))
    assert "2 floor plans added." in said and "Not added: notes.docx:" in said
    assert sorted(prop.plans.values_list("title", flat=True)) == ["Ground floor", "Site"]

    said = messages_of(client.post(url, {"kind": "photos", "files": [
        SimpleUploadedFile("Front elevation.png", png()), SimpleUploadedFile("fake.png", b"not an image")]},
        follow=True))
    assert "1 photo added." in said and "Not added: fake.png:" in said
    assert prop.photos.get().caption == "Front elevation"


def test_property_files_need_edit_rights(client, world, make_user):
    prop = world["prop"]
    url = reverse("properties:files", args=[prop.pk])
    for who in ("vic", "other"):
        client.force_login(world[who])
        assert client.post(url, {"kind": "plans", "files": [SimpleUploadedFile("a.pdf", PDF)]}).status_code == 403
    assert not prop.plans.exists()
    client.force_login(world["vic"])
    assert 'id="plan-files"' not in client.get(prop.get_absolute_url()).content.decode()
    client.force_login(make_user("boss", ADMINISTRATORS))
    client.post(url, {"kind": "plans", "files": [SimpleUploadedFile("a.pdf", PDF)]})
    assert prop.plans.count() == 1


# Every file chooser is a drop zone, with the label the component needs

def test_file_choosers_are_drop_zones():
    import re
    from pathlib import Path

    from django.conf import settings

    found = 0
    for path in Path(settings.BASE_DIR, "templates").rglob("*.html"):
        text = path.read_text()
        for match in re.finditer(r'<input class="govuk-file-upload[^>]*>', text):
            found += 1
            before = text[max(0, match.start() - 400):match.start()]
            assert 'data-module="govuk-file-upload"' in before, f"{path.name}: file chooser is not a drop zone"
            field_id = re.search(r'id="([^"]+)"', match.group(0))
            assert field_id, f"{path.name}: file chooser has no id"
            assert f'for="{field_id.group(1)}"' in text, f"{path.name}: no label for {field_id.group(1)}"
    assert found >= 16
