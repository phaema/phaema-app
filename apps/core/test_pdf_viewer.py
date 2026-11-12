# SPDX-License-Identifier: AGPL-3.0-or-later
"""The PDF viewer: a person opening a PDF gets PHAEMA's viewer page; the viewer, the API and scripts get the file."""
from datetime import date

import pytest
from django.contrib.staticfiles import finders
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from apps.core import viewer
from apps.leases.models import Lease, LeaseDocument, Party
from apps.properties.models import Property, PropertyPlan

PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"
BROWSER = {"HTTP_ACCEPT": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}


def _client(user):
    client = Client(HTTP_HOST="localhost")
    client.force_login(user)
    return client


@pytest.fixture
def plan(db):
    prop = Property.objects.create(name="Market Hall", address_line_1="1 High Street")
    item = PropertyPlan(property=prop, title="Ground floor plan",
                        file=SimpleUploadedFile("Ground floor (as built).pdf", PDF, content_type="application/pdf"))
    item.save()
    return item


@pytest.mark.django_db
def test_a_person_opening_a_pdf_gets_the_viewer(plan, make_user):
    client = _client(make_user("v.sam", "Surveyors"))
    url = f"/files/{plan.file.name}"
    response = client.get(url, **BROWSER)
    page = response.content.decode()
    assert response.status_code == 200 and response["Content-Type"].startswith("text/html")
    assert "Ground floor plan" in page and "Back to Market Hall" in page
    assert plan.property.get_absolute_url() in page
    assert f'data-src="{url}?raw=1"' in page and f'href="{url}?download=1"' in page
    assert "vendor/pdfjs/build/pdf.min.mjs" in page and "js/pdf-view.mjs" in page
    assert "no-store" in response["Cache-Control"] and "Accept" in response["Vary"]


@pytest.mark.django_db
def test_the_viewer_and_scripts_get_the_file(plan, make_user):
    client = _client(make_user("v.sam", "Surveyors"))
    url = f"/files/{plan.file.name}"
    for response in (client.get(url), client.get(url, HTTP_ACCEPT="*/*"), client.get(url + "?raw=1", **BROWSER)):
        assert response["Content-Type"] == "application/pdf"
        assert response["Content-Disposition"].startswith("inline")
        assert b"".join(response.streaming_content) == PDF
    assert "Accept" in client.get(url)["Vary"]


@pytest.mark.django_db
def test_download_uses_a_name_people_know(plan, make_user):
    client = _client(make_user("v.sam", "Surveyors"))
    response = client.get(f"/files/{plan.file.name}?download=1", **BROWSER)
    assert response["Content-Type"] == "application/pdf"
    assert response["Content-Disposition"].startswith("attachment")
    assert "Ground floor (as built).pdf" in response["Content-Disposition"]


@pytest.mark.django_db
def test_other_files_and_signed_out_people_are_unchanged(plan, make_user):
    drawing = PropertyPlan(property=plan.property, title="Site layout")
    drawing.file.save("site.dxf", ContentFile(b"0\nSECTION\n"))
    drawing.save()
    client = _client(make_user("v.sam", "Surveyors"))
    response = client.get(f"/files/{drawing.file.name}", **BROWSER)
    assert not response["Content-Type"].startswith("text/html")
    assert response["Content-Disposition"].startswith("attachment")
    assert client.get("/files/plans/none.pdf", **BROWSER).status_code == 404
    signed_out = Client(HTTP_HOST="localhost").get(f"/files/{plan.file.name}", **BROWSER)
    assert signed_out.status_code == 302 and "/login" in signed_out["Location"]


@pytest.mark.django_db
def test_titles_and_the_way_back(plan):
    lease = Lease.objects.create(reference="L-1", term_start=date(2020, 1, 1),
                                 counterparty=Party.objects.create(name="Acme Ltd"))
    typed = LeaseDocument(lease=lease, document_type="variation")
    typed.file.save("scan0001.pdf", ContentFile(PDF))
    typed.save()
    about = viewer.describe(typed.file.name)
    assert about["title"] == "Deed of variation" and about["record"] == lease
    assert about["filename"].endswith(".pdf")
    described = LeaseDocument(lease=lease, document_type="lease", description="Lease: Unit 3 / 2020")
    described.file.save("scan0002.pdf", ContentFile(PDF))
    described.save()
    assert viewer.describe(described.file.name)["title"] == "Lease: Unit 3 / 2020"
    unknown = viewer.describe("misc/abc.pdf")
    assert unknown == {"title": "abc.pdf", "filename": "abc.pdf", "record": None}


@pytest.mark.django_db
def test_no_record_goes_back_where_you_came_from(make_user, settings):
    from django.core.files.storage import default_storage

    name = default_storage.save("misc/loose.pdf", ContentFile(PDF))
    client = _client(make_user("v.sam", "Surveyors"))
    page = client.get(f"/files/{name}", HTTP_REFERER="http://localhost/cases/", **BROWSER).content.decode()
    assert 'href="http://localhost/cases/"' in page
    page = client.get(f"/files/{name}", HTTP_REFERER="https://elsewhere.example/x", **BROWSER).content.decode()
    assert "elsewhere.example" not in page and "govuk-back-link" not in page


@pytest.mark.django_db
def test_project_papers_open_in_the_viewer_for_those_who_can_see_them(make_user):
    from apps.projects import workflow
    from apps.projects.models import Project, ProjectType

    lead, other = make_user("v.lead", "Surveyors"), make_user("v.other", "Surveyors")
    project = workflow.start(Project(name="Northgate regeneration", confidential=True, lead=lead,
                                     project_type=ProjectType.objects.get(code="development")), lead)
    client = _client(lead)
    client.post(project.get_absolute_url(), {"action": "add_document", "title": "Heads of terms",
                                             "file": SimpleUploadedFile("hot.pdf", PDF, content_type="application/pdf")})
    url = f"/projects/{project.pk}/files/document/{project.documents.get().pk}/"
    page = client.get(url, **BROWSER).content.decode()
    assert "Heads of terms" in page and f"Back to {project}" in page and f'data-src="{url}?raw=1"' in page
    assert client.get(url + "?raw=1")["Content-Type"] == "application/pdf"
    assert client.get(url + "?download=1")["Content-Disposition"].startswith("attachment")
    assert _client(other).get(url, **BROWSER).status_code == 404


def test_the_viewer_is_shipped_with_phaema():
    for name in ("build/pdf.min.mjs", "build/pdf.worker.min.mjs", "web/pdf_viewer.mjs", "web/pdf_viewer.css", "LICENSE"):
        assert finders.find(f"vendor/pdfjs/{name}"), name
    assert finders.find("js/pdf-view.mjs")
