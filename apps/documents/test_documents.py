# SPDX-License-Identifier: AGPL-3.0-or-later
import io
from datetime import date
from decimal import Decimal

import pytest

from apps.cases import workflow
from apps.cases.models import CaseType
from apps.core.models import ModuleSettings
from apps.documents import merge, render
from apps.documents.models import DocumentTemplate
from apps.leases.models import Lease, Party
from apps.properties.models import Property


@pytest.fixture
def setup(db, make_user):
    settings = ModuleSettings.load()
    settings.organisation_name, settings.postal_address = "Exampleton Council", "Town Hall\nExampleton EX1 1AA"
    settings.save()
    surveyor = make_user("surv", "Surveyors", first_name="Alex", last_name="Morgan", email="a@example.org")
    unit = Property.objects.create(reference="U1", name="Unit 1", property_type="unit", managing_surveyor=surveyor,
                                   address_line_1="1 Mill Lane", town="Exampleton")
    tenant = Party.objects.create(name="Deli Co Ltd", party_type="company", address="2 High Street\nExampleton",
                                  contact_name="Ms Jones")
    lease = Lease.objects.create(reference="L1", agreement_type="lease", counterparty=tenant,
                                 lease_date=date(2020, 3, 25), term_start=date(2020, 3, 25),
                                 term_end=date(2030, 3, 24), annual_rent=Decimal("12500"), repairing="fri")
    lease.properties.add(unit)
    case = workflow.open_case(CaseType.objects.get(code="assignment"), title="Assign to New Co",
                              lease=lease, received_on=date(2026, 11, 2))
    return {"surveyor": surveyor, "lease": lease, "case": case, "unit": unit}


def _text(docx_bytes):
    from docx import Document

    doc = Document(io.BytesIO(docx_bytes))
    body = "\n".join(p.text for p in doc.paragraphs)
    body += "\n".join(c.text for t in doc.tables for row in t.rows for c in row.cells)
    header = "\n".join(p.text for p in doc.sections[0].header.paragraphs)
    return body, header


def test_supplied_templates_load_and_are_valid(db):
    assert DocumentTemplate.objects.filter(shipped=True).count() >= 25
    for t in DocumentTemplate.objects.all():
        t.full_clean()
    assert DocumentTemplate.objects.filter(category="notices_1954").exclude(prescribed_form="").exists()


def test_every_template_renders_to_word(setup):
    values = merge.context(user=setup["surveyor"], case=setup["case"])
    for t in DocumentTemplate.objects.all():
        text = render.fill(t, values, t.extra_fields)
        assert "{{" not in text and "{%" not in text, t.code
        data = render.to_docx(t, text, values)
        assert data[:2] == b"PK", t.code  # a .docx is a zip file
        assert render.to_html(text, values)


def test_merge_fields_from_a_case(setup):
    values = merge.context(user=setup["surveyor"], case=setup["case"])
    assert values["tenant_name"] == "Deli Co Ltd" and values["premises"].startswith("Unit 1")
    assert values["annual_rent"] == "£12,500.00" and values["lease_date"] == "25 March 2020"
    assert values["our_ref"] == setup["case"].display_reference and values["dear"] == "Ms Jones"
    assert values["author_name"] == "Alex Morgan" and values["statutory_1988"] == "yes"


def test_creating_a_consent_letter(client, setup):
    client.force_login(setup["surveyor"])
    case = setup["case"]
    url = "/documents/consent-refused/create/"
    page = client.get(url, {"case": case.pk}).content.decode()
    assert "Deli Co Ltd" in page and "Landlord and Tenant Act 1988" in page and "phaema-blank" in page
    response = client.post(url, {"case": case.pk, "f_reasons": "The proposed assignee's accounts show losses.",
                                 "f_addressee": "Deli Company Limited", "save": "1", "action": "word"})
    assert response["Content-Type"].startswith("application/vnd.openxmlformats")
    body, header = _text(response.content)
    assert "Deli Company Limited" in body and "accounts show losses" in body and "section 1(3)" in body
    assert "Exampleton Council" in header
    assert case.documents.filter(description__startswith="Consent refused").exists()


def test_prescribed_forms_are_flagged_and_blanks_highlighted(client, setup):
    client.force_login(setup["surveyor"])
    renewal = workflow.open_case(CaseType.objects.get(code="renewal"), title="Renew", lease=setup["lease"])
    response = client.post("/documents/s25-not-opposing/create/", {"case": renewal.pk, "action": "word"})
    body, _h = _text(response.content)
    assert "PRESCRIBED FORM: Form 1" in body and "[Proposed rent a year]" in body
    from docx import Document

    doc = Document(io.BytesIO(response.content))
    paragraphs = list(doc.paragraphs) + [p for t in doc.tables for row in t.rows for c in row.cells
                                         for p in c.paragraphs]
    assert any(r.font.highlight_color for p in paragraphs for r in p.runs)


def test_choosing_a_record_and_lease_letters(client, setup):
    client.force_login(setup["surveyor"])
    assert "Assign to New Co" in client.get("/documents/consent-approved/create/").content.decode()
    response = client.get("/documents/arrears-reminder/create/", {"lease": setup["lease"].pk})
    assert response.status_code == 200
    assert "Create a letter" in client.get(setup["lease"].get_absolute_url()).content.decode()
    assert "Create a letter or notice" in client.get(setup["case"].get_absolute_url()).content.decode()


def test_permissions_and_safety(client, make_user, setup):
    client.force_login(make_user("view", "Viewers"))
    assert client.get("/documents/").status_code == 200
    assert client.get("/documents/general-letter/").status_code == 200
    assert client.get("/documents/general-letter/create/", {"case": setup["case"].pk}).status_code == 403
    from django.core.exceptions import ValidationError

    bad = DocumentTemplate(code="bad", name="Bad", body="{% load static %}{% debug %}")
    with pytest.raises(ValidationError):
        bad.full_clean()
    broken = DocumentTemplate(code="broken", name="Broken", body="{% if %}")
    with pytest.raises(ValidationError):
        broken.full_clean()
