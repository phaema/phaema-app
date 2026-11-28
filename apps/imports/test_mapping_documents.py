# SPDX-License-Identifier: AGPL-3.0-or-later
"""Files from another system: matching their columns to PHAEMA's (and saving the matching), and documents in bulk."""
import io
import zipfile
from datetime import date

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import Workbook, load_workbook

from apps.imports.models import ImportMapping, MigrationRun
from apps.leases.models import Lease, LeaseDocument, Party
from apps.properties.demo_media import placeholder_pdf
from apps.properties.models import Property, PropertyPlan


@pytest.fixture
def admin(make_user):
    return make_user("admin1", "Administrators")


def _csv(text, name="export.csv"):
    return SimpleUploadedFile(name, text.encode("utf-8"))


def test_match_columns_save_and_reuse(client, admin):
    client.force_login(admin)
    export = "Customer Name,Kind,Tel\nMill Bakery,Company,01632 960111\n"
    page = client.post("/import/parties/", {"file": _csv(export)})
    assert page.templates[0].name == "imports/mapping.html"
    rows = {h: chosen for _i, h, chosen in page.context["rows"]}
    assert rows == {"Customer Name": "", "Kind": "", "Tel": ""}
    token = page.context["token"]
    # Name is required: leaving it unmatched is refused.
    again = client.post("/import/parties/", {"action": "map", "token": token, "sheet": "Parties",
                                             "map:1": "party_type"})
    assert "Match a column" in again.context["error"]
    preview = client.post("/import/parties/", {"action": "map", "token": token, "sheet": "Parties",
                                               "map:0": "name", "map:1": "party_type", "map:2": "phone",
                                               "save_as": "Old CRM"})
    assert preview.context["outcome"].ok
    saved = ImportMapping.objects.get()
    assert saved.mapping == {"customer name": "name", "kind": "party_type", "tel": "phone"}
    client.post("/import/parties/", {"confirm": "1", "token": preview.context["token"]})
    assert Party.objects.get(name="Mill Bakery").phone == "01632 960111"

    # The next export with the same columns is matched by the saved matching without asking.
    nxt = client.post("/import/parties/", {"file": _csv("Customer Name,Kind,Tel\nRiver Cafe,Company,\n")})
    assert nxt.context["mapping_used"] == saved and nxt.context["outcome"].ok
    client.post("/import/parties/", {"trial": "1", "token": nxt.context["token"]})
    assert MigrationRun.objects.filter(mode="trial").exists() and not Party.objects.filter(name="River Cafe").exists()


def test_two_columns_cannot_fill_one(client, admin):
    client.force_login(admin)
    page = client.post("/import/parties/", {"file": _csv("A,B\nX,Company\n")})
    resp = client.post("/import/parties/", {"action": "map", "token": page.context["token"], "sheet": "Parties",
                                            "map:0": "name", "map:1": "name"})
    assert "both matched" in resp.context["error"]


def test_property_export_matched(client, admin):
    client.force_login(admin)
    page = client.post("/properties/import/", {"file": _csv("Asset ID,Asset Name,Asset Type\nA-1,Depot,Site\n")})
    assert page.templates[0].name == "imports/mapping.html"
    preview = client.post("/properties/import/", {"action": "map", "token": page.context["token"],
                                                  "sheet": "Properties", "map:0": "reference", "map:1": "name",
                                                  "map:2": "property_type"})
    assert preview.context["outcome"].ok
    client.post("/properties/import/", {"confirm": "1", "token": preview.context["token"]})
    assert Property.objects.get(reference="A-1").name == "Depot"


def _zip(rows, files):
    index = Workbook()
    ws = index.active
    ws.title = "Documents"
    ws.append(["File", "Attach to", "Reference", "Type", "Description", "Date"])
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    index.save(buf)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("index.xlsx", buf.getvalue())
        for name, data in files.items():
            z.writestr(name, data)
    return SimpleUploadedFile("docs.zip", out.getvalue())


def test_documents_in_bulk(client, admin):
    tenant = Party.objects.create(name="T Ltd", party_type="company")
    lease = Lease.objects.create(reference="L-9", agreement_type="lease", counterparty=tenant,
                                 term_start=date(2024, 1, 1))
    prop = Property.objects.create(reference="P-9", name="Shop", property_type="unit")
    client.force_login(admin)
    assert load_workbook(io.BytesIO(client.get("/import/documents/index-template.xlsx").content)).sheetnames == [
        "Documents", "Guidance"]
    pdf = placeholder_pdf("Lease", ["Fictional"])
    bad = _zip([["leases/L-9.pdf", "Agreement document", "L-9", "Lease or licence", "Signed lease", "25/03/2024"],
                ["missing.pdf", "Agreement document", "L-9", "", "", ""],
                ["plans/p.pdf", "Floor plan", "NOPE", "", "Ground floor", ""],
                ["notes.txt", "Agreement document", "L-9", "Spaceship", "", ""]],
               {"leases/L-9.pdf": pdf, "plans/p.pdf": pdf, "notes.txt": b"hello"})
    preview = client.post("/import/documents/", {"file": bad})
    errors = {r.number: " ".join(r.errors) for r in preview.context["outcome"].rows}
    assert not errors[2] and "no file called missing.pdf" in errors[3] and "NOPE" in errors[4]
    assert "Spaceship" in errors[5]

    good = _zip([["leases/L-9.pdf", "Lease", "L-9", "Lease or licence", "Signed lease", "25/03/2024"],
                 ["plans/p.pdf", "Floor plan", "P-9", "", "Ground floor", ""]],
                {"leases/L-9.pdf": pdf, "plans/p.pdf": pdf})
    preview = client.post("/import/documents/", {"file": good})
    outcome = preview.context["outcome"]
    assert outcome.ok and [s[0] for s in outcome.summary] == ["Agreement documents", "Floor plans"]
    assert b"Trial run first" not in preview.content
    client.post("/import/documents/", {"confirm": "1", "token": preview.context["token"]})
    doc = LeaseDocument.objects.get(lease=lease)
    assert doc.document_type == "lease" and doc.document_date == date(2024, 3, 25) and doc.original_filename == "L-9.pdf"
    assert PropertyPlan.objects.get(property=prop).title == "Ground floor"
    run = MigrationRun.objects.get(kind="documents")
    assert {c["key"]: c["matches"] for c in run.controls}["documents:rows"]
    # The same zip again warns that the documents are already there.
    again = client.post("/import/documents/", {"file": _zip([["leases/L-9.pdf", "Lease", "L-9", "", "", ""]],
                                                              {"leases/L-9.pdf": pdf})})
    assert again.context["outcome"].warning_count == 1


def test_documents_for_administrators_only(client, make_user):
    client.force_login(make_user("surv", "Surveyors"))
    assert client.get("/import/documents/").status_code in (403, 404)
    assert client.get("/import/documents/index-template.xlsx").status_code in (403, 404)
