# SPDX-License-Identifier: AGPL-3.0-or-later
"""Moving records in from another system: trial runs, control totals, the exception report, warnings and sign-off."""
import io
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import load_workbook

from apps.imports.models import MigrationRun
from apps.imports.sheets import LeaseSheet, party_key
from apps.imports.test_imports import LEASE_FIELDS, _book, _headings
from apps.leases.models import Lease, Party
from apps.properties.models import Property


@pytest.fixture
def admin(make_user):
    return make_user("admin1", "Administrators")


@pytest.fixture
def admin2(make_user):
    return make_user("admin2", "Administrators")


@pytest.fixture
def units(db):
    return [Property.objects.create(reference=f"U{i}", name=f"Unit {i}", property_type="unit") for i in (1, 2)]


def _leases():
    return _book({
        "Parties": (["Name", "Type"], [["Mill Bakery Ltd", "Company"], ["River Cafe", "Sole trader or individual"]]),
        "Leases": (_headings(LeaseSheet, LEASE_FIELDS), [
            ["L-1", "Mill Bakery Ltd", "U1", "Lease", "25/03/2024", "24/03/2034", "12,500", "Open market, upwards only",
             "25/03/2029"],
            ["L-2", "River Cafe", "U2", "Licence", "01/04/2025", "31/03/2026", "4800.50", "", ""]]),
    })


def test_party_key_ignores_company_words():
    assert party_key("Mill Bakery Ltd") == party_key("The Mill Bakery Limited") == "mill bakery"
    assert party_key("A & B Plc") == "a b"


def test_trial_run_saves_nothing_and_keeps_a_record(client, admin, units):
    client.force_login(admin)
    preview = client.post("/import/leases/", {"file": _leases()})
    outcome = preview.context["outcome"]
    assert outcome.ok
    controls = {c.key: c.in_file for c in outcome.controls}
    assert controls["Leases:annual_rent"] == Decimal("17300.50") and controls["Leases:rows"] == 2
    trial = client.post("/import/leases/", {"trial": "1", "token": preview.context["token"],
                                            "expected:Leases:annual_rent": "17,300.50",
                                            "expected:Leases:rows": "3"})
    run = MigrationRun.objects.get()
    assert trial.status_code == 302 and trial["Location"] == run.get_absolute_url()
    assert run.mode == "trial" and run.rows == 4 and len(run.file_sha256) == 64
    assert not Lease.objects.filter(reference__in=["L-1", "L-2"]).exists()
    assert not Party.objects.filter(name="Mill Bakery Ltd").exists()
    by_key = {c["key"]: c for c in run.controls}
    assert by_key["Leases:annual_rent"]["in_phaema"] == "17300.50" and by_key["Leases:annual_rent"]["matches"]
    assert by_key["Leases:rows"]["expected"] == "3" and by_key["Leases:rows"]["matches"] is False
    assert run.mismatches and not run.reconciled
    page = client.get(run.get_absolute_url())
    assert page.context["can_import"] and "Does not match" in page.content.decode()
    report = load_workbook(io.BytesIO(client.get(f"/import/runs/{run.pk}/report.xlsx").getvalue()))
    assert report.sheetnames == ["Summary", "Rows"] and report["Rows"].max_row == 5

    # Then import the same file for real from the trial's page, with the same old-system figures.
    done = client.post("/import/leases/", {"confirm": "1", "token": page.context["token"],
                                           **{f"expected:{k}": v for k, v in page.context["expected"].items()}})
    assert done.status_code == 302
    assert Lease.objects.get(reference="L-1").annual_rent == Decimal("12500")
    live = MigrationRun.objects.filter(mode="live").get()
    assert {c["key"]: c["expected"] for c in live.controls}["Leases:rows"] == "3"


def test_check_report_lists_problems_without_importing(client, admin, units):
    client.force_login(admin)
    bad = _book({"Parties": (["Name", "Type"], [["Good Ltd", "Company"], ["No Type", ""]])})
    preview = client.post("/import/parties/", {"file": bad})
    assert not preview.context["outcome"].ok and "token" not in preview.context
    resp = client.get(f"/import/parties/check.xlsx?token={preview.context['check_token']}")
    rows = load_workbook(io.BytesIO(resp.content))["Rows"]
    assert rows["D3"].value == "Problem" and "Type is missing" in rows["F3"].value
    assert client.get("/import/parties/check.xlsx?token=wrong").status_code == 404
    assert not MigrationRun.objects.exists()


def test_possible_duplicate_party_is_a_warning(client, admin):
    Party.objects.create(name="Mill Bakery Limited", party_type="company", finance_customer_ref="C100")
    client.force_login(admin)
    upload = _book({"Parties": (["Name", "Type"], [["The Mill Bakery Ltd", "Company"], ["Mill Bakery LLP", "Company"]])})
    outcome = client.post("/import/parties/", {"file": upload}).context["outcome"]
    assert outcome.ok and outcome.warning_count == 2
    assert "Mill Bakery Limited" in outcome.rows[0].warnings[0] and "C100" in outcome.rows[0].warnings[0]
    assert any("row 2" in w for w in outcome.rows[1].warnings)


def test_property_import_trial_totals_and_twin_address(client, admin, db):
    Property.objects.create(reference="OLD-1", name="Old shop", property_type="unit", address_line_1="1 High St",
                            postcode="ZZ99 1AA")
    client.force_login(admin)
    text = ("Reference,Name,Type,Address line 1,Postcode,GIA m2\n"
            "P-1,Shop,Lettable unit,1 High St,ZZ99 1AA,120.5\n"
            "P-2,Store,Lettable unit,2 High St,ZZ99 1AA,80\n")
    preview = client.post("/properties/import/", {"file": SimpleUploadedFile("p.csv", text.encode())})
    outcome = preview.context["outcome"]
    assert outcome.ok and "OLD-1" in outcome.rows[0].warnings[0] and not outcome.rows[1].warnings
    client.post("/properties/import/", {"trial": "1", "token": preview.context["token"]})
    run = MigrationRun.objects.get()
    gia = next(c for c in run.controls if c["key"] == "properties:gia_sqm")
    assert gia["in_file"] == "200.5" and Decimal(gia["in_phaema"]) == Decimal("200.5") and gia["matches"]
    assert not Property.objects.filter(reference="P-1").exists() and run.warnings == 1
    done = client.post("/properties/import/", {"confirm": "1", "token": preview.context["token"]})
    assert done.status_code == 302 and Property.objects.filter(reference="P-1").exists()


def test_sign_off_by_another_administrator_only(client, admin, admin2, make_user, units):
    client.force_login(admin)
    preview = client.post("/import/parties/", {"file": _book({"Parties": (["Name", "Type"], [["X Ltd", "Company"]])})})
    client.post("/import/parties/", {"confirm": "1", "token": preview.context["token"]})
    run = MigrationRun.objects.get(mode="live")
    assert not client.get(run.get_absolute_url()).context["can_sign_off"]
    client.post(f"/import/runs/{run.pk}/sign-off/", {"note": "Mine"})
    run.refresh_from_db()
    assert run.signed_off_at is None
    client.force_login(admin2)
    client.post(f"/import/runs/{run.pk}/sign-off/", {"note": "Checked against the old debtor list."})
    run.refresh_from_db()
    assert run.signed_off_by == admin2 and "debtor" in run.sign_off_note
    client.post(f"/import/runs/{run.pk}/sign-off/", {"note": "Again"})
    run.refresh_from_db()
    assert "debtor" in run.sign_off_note
    hub = client.get("/import/")
    assert run in hub.context["runs"] and client.get("/import/runs/").status_code == 200
    surveyor = make_user("surv", "Surveyors")
    client.force_login(surveyor)
    assert client.get(run.get_absolute_url()).status_code in (403, 404)
