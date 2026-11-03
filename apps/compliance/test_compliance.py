# SPDX-License-Identifier: AGPL-3.0-or-later
import json
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.compliance import rules, workflow
from apps.compliance.models import Action, BuildingDocument, BuildingSafety, ComplianceType, Requirement
from apps.core.models import ModuleSettings
from apps.leases.models import Lease, Party
from apps.properties.models import Property


@pytest.fixture
def setup(db, make_user):
    surveyor = make_user("surv", "Surveyors")
    building = Property.objects.create(reference="B1", name="Block", property_type="building",
                                       managing_surveyor=surveyor, easting=530000, northing=180000)
    shop = Property.objects.create(reference="S1", name="Shop", property_type="unit", managing_surveyor=surveyor)
    lease = Lease.objects.create(reference="L1", agreement_type="lease",
                                 counterparty=Party.objects.create(name="T Ltd", party_type="company"),
                                 term_start=date(2020, 1, 1), annual_rent=Decimal("1"), repairing="fri")
    lease.properties.add(shop)
    return {"surveyor": surveyor, "building": building, "shop": shop}


def test_types_seeded_and_who_holds_them(setup):
    assert ComplianceType.objects.filter(code="gas", valid_months=12).exists()
    assert rules.responsible(setup["shop"])[0] == "tenant"
    assert rules.responsible(setup["building"])[0] == "council"


def test_certificates_status_and_actions(client, setup):
    client.force_login(setup["surveyor"])
    url = f"/compliance/property/{setup['building'].pk}/"
    gas, eicr = ComplianceType.objects.get(code="gas"), ComplianceType.objects.get(code="eicr")
    client.post(url, {"action": "add_requirements", "kind": [gas.pk, eicr.pk]})
    req = Requirement.objects.get(property=setup["building"], kind=gas)
    assert workflow.statuses([req])[0][1][1] == "Missing"
    pdf = SimpleUploadedFile("gas.pdf", b"%PDF-1.4 cert")
    client.post(url, {"action": "certificate", "requirement": req.pk, "issued_on": "2026-01-15", "result": "actions",
                      "actions": "Service the boiler flue\nLabel the meter", "priority": "high", "file": pdf})
    cert = req.certificates.get()
    assert cert.expires_on == date(2027, 1, 15) and cert.file
    assert cert.actions.count() == 2 and cert.actions.first().due_on == date(2026, 1, 22)
    req = Requirement.objects.get(pk=req.pk)
    assert workflow.statuses([req], today=date(2026, 6, 1))[0][1][1] == "Actions open"
    assert workflow.statuses([req], today=date(2026, 12, 1))[0][1][1] == "Expires soon"
    assert workflow.statuses([req], today=date(2027, 2, 1))[0][1][1] == "Expired"
    item = cert.actions.first()
    client.post(url, {"action": "action_done", "item": item.pk, "date": "2026-01-20"})
    item.refresh_from_db()
    assert item.done_on == date(2026, 1, 20)
    page = client.get("/compliance/?show=all").content.decode()
    assert "Gas safety record" in page and "Missing" in page  # the EICR


def test_remedial_action_becomes_a_repair_job(client, setup):
    settings = ModuleSettings.load()
    settings.maintenance_enabled = True
    settings.save()
    req = workflow.add_requirements(setup["building"], [ComplianceType.objects.get(code="fra")])[0]
    cert = workflow.record(req, date(2026, 10, 1), result="actions")
    item = Action.objects.create(certificate=cert, description="Fit a door closer", priority="high")
    client.force_login(setup["surveyor"])
    client.post(f"/compliance/property/{setup['building'].pk}/", {"action": "action_job", "item": item.pk})
    item.refresh_from_db()
    assert item.job.title == "Fit a door closer" and item.job.priority == "urgent" and item.job.category == "fire"


def test_higher_risk_screening(client, setup):
    building = setup["building"]
    assert rules.suggested_tier(building)[0] == "B"
    land = Property.objects.create(reference="L9", name="Field", property_type="land")
    assert rules.suggested_tier(land)[0] == "C"
    client.force_login(setup["surveyor"])
    client.post(f"/compliance/property/{building.pk}/", {"action": "screening", "country": "england",
                                                         "height_m": "19.2", "storeys": "6", "residential_units": "12",
                                                         "tier": "A", "accountable_person": "Exampleton Council"})
    s = BuildingSafety.objects.get(property=building)
    assert s.tier == "A" and s.confirmed_by == setup["surveyor"] and rules.suggested_tier(building, s)[0] == "A"
    s.height_m, s.storeys = Decimal("15"), 5
    assert rules.suggested_tier(building, s)[0] == "B"


def test_documents_keep_every_version(client, setup):
    client.force_login(setup["surveyor"])
    url = f"/compliance/property/{setup['building'].pk}/"
    client.post(url, {"action": "document", "title": "Floor plans", "category": "plans",
                      "file": SimpleUploadedFile("p.pdf", b"%PDF-1.4 v1")})
    first = BuildingDocument.objects.get()
    client.post(url, {"action": "document", "supersedes": first.pk,
                      "file": SimpleUploadedFile("p2.pdf", b"%PDF-1.4 v2")})
    second = BuildingDocument.objects.exclude(pk=first.pk).get()
    first.refresh_from_db()
    assert second.title == "Floor plans" and second.version() == 2 and not first.is_current and second.is_current
    page = client.get(url).content.decode()
    assert "1 earlier version" in page


def test_open_data(client, setup):
    hidden = Property.objects.create(reference="R1", name="Refuge", property_type="building",
                                     exclude_from_publication=True)
    Property.objects.create(reference="R1-U1", name="Part of the refuge", property_type="unit", parent=hidden)
    assert client.get("/open-data/").status_code == 404  # off by default
    settings = ModuleSettings.load()
    settings.open_data_enabled = True
    settings.save()
    assert client.get("/open-data/").status_code == 200  # no sign-in needed
    text = client.get("/open-data/land-and-assets.csv").content.decode("utf-8-sig")
    assert "B1" in text and "Refuge" not in text
    data = json.loads(client.get("/open-data/land-and-assets.geojson").content)
    feature = next(f for f in data["features"] if f["properties"]["asset_reference"] == "B1")
    assert feature["geometry"]["type"] == "Point" and data["licence"].startswith("Open Government")
    records = json.loads(client.get("/open-data/available-property.json").content)["records"]
    assert all(r["asset_reference"] != "B1" for r in records)


def test_reports_and_permissions(client, make_user, setup):
    req = workflow.add_requirements(setup["shop"], [ComplianceType.objects.get(code="epc")])[0]
    workflow.record(req, date.today() - timedelta(days=400), rating="F")
    client.force_login(make_user("view", "Viewers"))
    for url in ("/compliance/", f"/compliance/property/{setup['shop'].pk}/", "/compliance/?format=xlsx", "/"):
        assert client.get(url).status_code == 200, url
    assert client.post(f"/compliance/property/{setup['shop'].pk}/", {"action": "screening"}).status_code == 403
    from apps.reports.models import Report

    epc = Report.objects.get(starter="epc_f_g")
    assert "S1" in client.get(epc.get_absolute_url()).content.decode()
    for report in Report.objects.filter(starter__in=["certificates_expired", "certificates_60", "actions_overdue"]):
        assert client.get(report.get_absolute_url()).status_code == 200


def test_component_import(client, make_user, setup):
    from openpyxl import Workbook

    settings = ModuleSettings.load()
    settings.maintenance_enabled = True
    settings.save()
    wb = Workbook()
    ws = wb.active
    ws.title = "Components"
    ws.append(["Property reference", "Component", "Category", "Installed (year)", "Expected life (years)",
               "Condition", "Replacement cost"])
    ws.append(["B1", "Main roof", "Roof", 2001, 25, "C", 85000])
    import io

    buf = io.BytesIO()
    wb.save(buf)
    client.force_login(make_user("admin", "Administrators"))
    assert client.get("/import/maintenance/template.xlsx").status_code == 200
    response = client.post("/import/maintenance/", {"file": SimpleUploadedFile("c.xlsx", buf.getvalue())})
    assert response.context["result"].ok, [r.errors for r in response.context["result"].rows]
    client.post("/import/maintenance/", {"confirm": "1", "token": response.context["token"]})
    from apps.maintenance.models import Component

    assert Component.objects.filter(property=setup["building"], name="Main roof", condition="C").exists()
