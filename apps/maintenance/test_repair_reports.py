# SPDX-License-Identifier: AGPL-3.0-or-later
"""Repair reports: the shared form in the tenant portal and on departments' building pages, and the triage queue."""
from datetime import date
from html import escape
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from PIL import Image

from apps.core.models import AuditEntry, ModuleSettings
from apps.leases.models import Lease, Party
from apps.maintenance.models import Job, RepairReport
from apps.portal.models import PortalAccount
from apps.portal.tests import _sign_in
from apps.properties.models import Property
from apps.space.test_costs import setup  # noqa: F401  (the fixture)


def _jpeg(name="leak.jpg"):
    out = BytesIO()
    Image.new("RGB", (40, 30), "red").save(out, "JPEG")
    return SimpleUploadedFile(name, out.getvalue(), content_type="image/jpeg")


def _client(user):
    c = Client(HTTP_HOST="localhost")
    c.force_login(user)
    return c


@pytest.fixture
def estate(make_user, setup):  # noqa: F811
    from django.core.cache import cache

    cache.clear()
    s = ModuleSettings.load()
    s.maintenance_enabled = s.tenant_portal_enabled = True
    s.save()
    sam = make_user("sam", "Surveyors", first_name="Sam")
    unit = Property.objects.create(reference="U1", name="Unit 1, Market Hall", property_type="unit",
                                   managing_surveyor=sam)
    other_unit = Property.objects.create(reference="U2", name="Unit 2", property_type="unit")
    cafe = Party.objects.create(name="Cafe Ltd", party_type="company")
    shop = Party.objects.create(name="Shop Ltd", party_type="company")
    lease = Lease.objects.create(reference="L-1", counterparty=cafe, direction="out", term_start=date(2024, 1, 1),
                                 repairing="iri")
    lease.properties.add(unit)
    other = Lease.objects.create(reference="L-2", counterparty=shop, direction="out", term_start=date(2024, 1, 1))
    other.properties.add(other_unit)
    fac = PortalAccount.objects.create(party=cafe, name="Fay", email="fay@cafe.example", finance=False,
                                       facilities=True)
    fin = PortalAccount.objects.create(party=cafe, name="Finn", email="finn@cafe.example")
    setup["building"].managing_surveyor = sam
    setup["building"].save()
    lee = make_user("lee", first_name="Lee", last_name="Okafor")
    head = make_user("head")
    setup["housing"].liaison = lee
    setup["housing"].save()
    setup["housing"].readers.add(head)
    return {"sam": sam, "unit": unit, "lease": lease, "other": other, "fac": fac, "fin": fin, "lee": lee,
            "head": head, **setup}


def _report(client, lease, **extra):
    data = {"property": lease.properties.first().pk, "location": "Kitchen ceiling", "description": "Water coming in",
            "contact_phone": "07700 900000", **extra}
    return client.post(f"/tenant/agreements/{lease.pk}/repair/", data)


def test_tenant_reports_a_repair_with_a_photo(estate, client):
    _sign_in(client, estate["fac"])
    assert client.get(f"/tenant/agreements/{estate['lease'].pk}/repair/").status_code == 200
    response = _report(client, estate["lease"], danger="on", photos=[_jpeg()])
    assert b"RR-" in response.content
    report = RepairReport.objects.get()
    assert report.source == "tenant" and report.portal_account == estate["fac"] and report.danger
    assert report.property == estate["unit"] and report.lease == estate["lease"] and report.reporter_name == "Fay"
    assert report.photos.count() == 1 and report.photos.first().image.name.endswith(".jpg")
    entry = AuditEntry.objects.get(content_type__model="repairreport", object_id=str(report.pk))
    assert entry.via.startswith("Tenant portal")
    page = client.get(f"/tenant/agreements/{estate['lease'].pk}/").content.decode()
    assert "Kitchen ceiling" in page and "Waiting to be looked at" in page
    dash = _client(estate["sam"]).get("/").content.decode()
    assert "Repair report to look at" in dash and "Someone may be at risk" in dash


def test_only_facilities_rights_and_own_agreements(estate, client):
    _sign_in(client, estate["fin"])
    assert client.get(f"/tenant/agreements/{estate['lease'].pk}/repair/").status_code == 404
    assert b"Report a repair" not in client.get(f"/tenant/agreements/{estate['lease'].pk}/").content
    client.post("/tenant/sign-out/")
    _sign_in(client, estate["fac"])
    assert client.get(f"/tenant/agreements/{estate['other'].pk}/repair/").status_code == 404
    # a property outside the agreement cannot be chosen
    response = client.post(f"/tenant/agreements/{estate['lease'].pk}/repair/", {
        "property": estate["other"].properties.first().pk, "location": "x", "description": "y"})
    assert response.status_code == 200 and not RepairReport.objects.exists()


def test_photo_checks(estate, client):
    _sign_in(client, estate["fac"])
    _report(client, estate["lease"], photos=[_jpeg(f"p{i}.jpg") for i in range(4)])
    _report(client, estate["lease"], photos=[SimpleUploadedFile("x.jpg", b"not an image", "image/jpeg")])
    assert not RepairReport.objects.exists()


def test_repairs_hidden_when_maintenance_is_off(estate, client):
    s = ModuleSettings.load()
    s.maintenance_enabled = False
    s.save()
    _sign_in(client, estate["fac"])
    assert client.get(f"/tenant/agreements/{estate['lease'].pk}/repair/").status_code == 404
    assert b"Report a repair" not in client.get(f"/tenant/agreements/{estate['lease'].pk}/").content


def test_triage_raises_a_job_and_the_tenant_sees_progress(estate, client):
    _sign_in(client, estate["fac"])
    _report(client, estate["lease"], photos=[_jpeg()])
    report = RepairReport.objects.get()
    sam = _client(estate["sam"])
    page = sam.get(f"/maintenance/reports/{report.pk}/")
    assert page.status_code == 200 and b"Kitchen ceiling" in page.content
    assert sam.get(report.photos.first().image.url).status_code == 200
    assert b"RR-" in sam.get("/maintenance/reports/").content
    sam.post(f"/maintenance/reports/{report.pk}/", {"action": "job", "title": "Roof leak over kitchen",
                                                     "category": "roof", "priority": "urgent", "reply": "On it."})
    report.refresh_from_db()
    job = report.job
    assert report.status == "job" and job.how_reported == Job.Reported.TENANT and job.reported_by == "Fay"
    assert job.lease == estate["lease"] and job.priority == "urgent" and job.target_date
    assert b"RR-" in sam.get(job.get_absolute_url()).content
    page = client.get(f"/tenant/agreements/{estate['lease'].pk}/").content.decode()
    assert "Job raised" in page and "On it." in page and escape(job.get_responsibility_display()) in page
    assert "Repair report to look at" not in sam.get("/").content.decode()


def test_triage_other_decisions(estate, client):
    _sign_in(client, estate["fac"])
    _report(client, estate["lease"])
    _report(client, estate["lease"], location="Front door")
    first, second = RepairReport.objects.order_by("pk")
    sam = _client(estate["sam"])
    sam.post(f"/maintenance/reports/{first.pk}/", {"action": "tenant"})
    first.refresh_from_db()
    assert first.status == "new"  # a reply is needed
    sam.post(f"/maintenance/reports/{first.pk}/", {"action": "tenant", "reply": "Inside repairs are yours."})
    first.refresh_from_db()
    assert first.status == "tenant" and first.progress()[2] == "Tenant's responsibility"
    from apps.maintenance import workflow

    job = workflow.open_job(estate["unit"], "Door lock", user=estate["sam"])
    sam.post(f"/maintenance/reports/{second.pk}/", {"action": "duplicate", "job": job.pk})
    second.refresh_from_db()
    assert second.status == "duplicate" and second.job == job


def test_viewers_cannot_decide(estate, client, make_user):
    _sign_in(client, estate["fac"])
    _report(client, estate["lease"])
    report = RepairReport.objects.get()
    viewer = _client(make_user("vic", "Viewers"))
    assert viewer.post(f"/maintenance/reports/{report.pk}/", {"action": "closed", "reply": "no"}).status_code == 403
    report.refresh_from_db()
    assert report.status == "new"


def test_department_liaison_reports_a_repair(estate):
    lee = _client(estate["lee"])
    building = estate["building"]
    assert b"Report a repair" in lee.get(f"/occupier/building/{building.pk}/").content
    lee.post(f"/occupier/building/{building.pk}/repair/", {
        "property": building.pk, "location": "Second floor toilets", "description": "Tap will not turn off"})
    report = RepairReport.objects.get()
    assert report.source == "department" and report.occupier == estate["housing"]
    assert report.reported_by_user == estate["lee"] and report.reporter_name == "Lee Okafor" and report.lease is None
    assert b"Second floor toilets" in lee.get(f"/occupier/building/{building.pk}/").content
    head = _client(estate["head"])
    assert head.get(f"/occupier/building/{building.pk}/repair/").status_code == 404
    assert b"Second floor toilets" in head.get(f"/occupier/building/{building.pk}/").content  # can follow it
