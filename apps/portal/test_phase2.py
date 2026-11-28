# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tenant portal phase 2: service charge budgets and statements, querying a line, and certificates the tenant
provides, with reminders."""
import re
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from apps.cases.models import Case
from apps.compliance.models import Certificate, ComplianceType, Requirement
from apps.core.models import ModuleSettings, OutgoingEmail
from apps.leases.models import Lease, Party
from apps.ledger import billing
from apps.portal.models import PortalAccount
from apps.portal.reminders import send_certificate_reminders
from apps.portal.tests import _sign_in
from apps.servicecharges import apportion
from apps.servicecharges.models import CostHeading, Expenditure
from apps.servicecharges.test_service_charges import estate  # noqa: F401  (the fixture)

pytestmark = pytest.mark.django_db
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


@pytest.fixture
def portal(estate):  # noqa: F811
    from django.core.cache import cache

    cache.clear()
    s = ModuleSettings.load()
    s.tenant_portal_enabled = s.compliance_enabled = True
    s.save()
    tenant = estate["leases"][0].counterparty
    fay = PortalAccount.objects.create(party=tenant, name="Fay", email="fay@tenant.example", finance=False,
                                       facilities=True)
    finn = PortalAccount.objects.create(party=tenant, name="Finn", email="finn@tenant.example")
    other = Party.objects.create(name="Other Ltd", party_type="company")
    olease = Lease.objects.create(reference="L9", agreement_type="lease", counterparty=other,
                                  term_start=date(2024, 1, 1))
    olease.properties.add(estate["units"][3])
    gas = ComplianceType.objects.filter(code__icontains="gas").first() or ComplianceType.objects.create(
        code="gas", name="Gas safety record", valid_months=12)
    req = Requirement.objects.create(property=estate["units"][0], kind=gas, responsible="tenant")
    council_req = Requirement.objects.create(property=estate["units"][0], responsible="council",
                                             kind=ComplianceType.objects.exclude(pk=gas.pk).first())
    return {**estate, "fay": fay, "finn": finn, "olease": olease, "req": req, "council_req": council_req,
            "lease": estate["leases"][0]}


def test_service_charges_only_once_issued_and_for_facilities(portal, client):
    lease, year = portal["lease"], portal["year"]
    _sign_in(client, portal["fay"])
    assert b"Service charges" not in client.get(f"/tenant/agreements/{lease.pk}/").content
    assert client.get(f"/tenant/agreements/{lease.pk}/service-charges/{year.pk}/budget/").status_code == 404
    year.budget_issued_on, year.budget_commentary = date(2025, 3, 1), "New cleaning contract."
    year.save()
    page = client.get(f"/tenant/agreements/{lease.pk}/").content.decode()
    assert "Service charges" in page and "Not yet" in page
    budget = client.get(f"/tenant/agreements/{lease.pk}/service-charges/{year.pk}/budget/").content.decode()
    assert "New cleaning contract." in budget and "£2,000.00" in budget  # 20% of £10,000
    assert client.get(f"/tenant/agreements/{lease.pk}/service-charges/{year.pk}/statement/").status_code == 404
    client.post("/tenant/sign-out/")
    _sign_in(client, portal["finn"])  # finance rights only
    assert client.get(f"/tenant/agreements/{lease.pk}/service-charges/{year.pk}/budget/").status_code == 404


def test_year_end_statement_after_reconciliation_shows_the_balance(portal, client):
    lease, year = portal["lease"], portal["year"]
    billing.issue_run(date(2025, 3, 1), date(2026, 3, 31), date(2025, 3, 1), service=True, rent=False)
    Expenditure.objects.create(year=year, heading=CostHeading.objects.get(code="CLN"), spent_on=date(2025, 6, 1),
                               description="Cleaning", amount=Decimal("12000"))
    before = next(line for line in apportion.reconcile(year).lines if line.share.member.lease == lease).balance
    apportion.finalise(year, date(2026, 5, 1))
    after = next(line for line in apportion.reconcile(year).lines if line.share.member.lease == lease).balance
    assert after == before != 0  # balancing charges do not count as paid on account
    year.refresh_from_db()
    year.budget_issued_on, year.statements_issued_on = date(2025, 3, 1), date(2026, 5, 1)
    year.save()
    _sign_in(client, portal["fay"])
    page = client.get(f"/tenant/agreements/{lease.pk}/service-charges/{year.pk}/statement/").content.decode()
    assert "Balance due from you" in page and f"£{before:,.2f}" in page


def test_query_a_line_opens_a_case_the_tenant_can_follow(portal, client):
    lease, year = portal["lease"], portal["year"]
    year.budget_issued_on = date(2025, 3, 1)
    year.save()
    _sign_in(client, portal["fay"])
    heading = CostHeading.objects.get(code="CLN")
    client.post(f"/tenant/agreements/{lease.pk}/service-charges/{year.pk}/query/",
                {"heading": heading.pk, "question": "Why has cleaning gone up?"})
    case = Case.objects.get()
    assert case.case_type.code == "sc_dispute" and case.how_received == "portal" and heading.name in case.title
    assert case.correspondence.get().summary == "Why has cleaning gone up?"
    assert case.display_reference.encode() in client.get(f"/tenant/agreements/{lease.pk}/").content


def test_tenant_sends_a_certificate_and_estates_check_it(portal, client, make_user):
    lease, req = portal["lease"], portal["req"]
    _sign_in(client, portal["fay"])
    page = client.get(f"/tenant/agreements/{lease.pk}/").content.decode()
    assert req.kind.name in page and "Not sent yet" in page and portal["council_req"].kind.name not in page
    assert client.get(f"/tenant/agreements/{lease.pk}/certificates/{portal['council_req'].pk}/").status_code == 404
    response = client.post(f"/tenant/agreements/{lease.pk}/certificates/{req.pk}/", {
        "issued_on": (date.today() - timedelta(days=10)).isoformat(), "result": "ok",
        "carried_out_by": "A Engineer, Gas Safe 123456", "reference": "GS-1",
        "file": SimpleUploadedFile("gas.pdf", PDF, "application/pdf")})
    assert b"Certificate sent" in response.content
    cert = Certificate.objects.get()
    assert cert.portal_account == portal["fay"] and cert.checked_on is None and cert.file
    assert "In date" in client.get(f"/tenant/agreements/{lease.pk}/").content.decode()
    admin = make_user("ada", "Administrators")
    staff = Client(HTTP_HOST="localhost")
    staff.force_login(admin)
    assert "Certificate from a tenant to check" in staff.get("/?view=mine").content.decode()
    page = staff.get(f"/compliance/property/{req.property_id}/").content.decode()
    assert "Waiting to be checked" in page
    staff.post(f"/compliance/property/{req.property_id}/", {"action": "check_certificate", "certificate": cert.pk})
    cert.refresh_from_db()
    assert cert.checked_by == admin and cert.checked_on


def test_certificate_dates_cannot_be_in_the_future(portal, client):
    _sign_in(client, portal["fay"])
    client.post(f"/tenant/agreements/{portal['lease'].pk}/certificates/{portal['req'].pk}/", {
        "issued_on": (date.today() + timedelta(days=3)).isoformat(), "result": "ok", "carried_out_by": "X",
        "file": SimpleUploadedFile("gas.pdf", PDF, "application/pdf")})
    assert not Certificate.objects.exists()


def test_reminders_for_missing_and_running_out_certificates(portal):
    req = portal["req"]
    today = date.today()
    assert send_certificate_reminders(today) == 1  # Fay has facilities rights; Finn does not
    email = OutgoingEmail.objects.get(kind="certificate_reminder")
    assert email.to == "fay@tenant.example" and "do not have a copy" in email.body
    assert re.search(rf"/tenant/agreements/{portal['lease'].pk}/certificates/{req.pk}/", email.body)
    assert send_certificate_reminders(today) == 0  # not again within 30 days
    from django.contrib.contenttypes.models import ContentType

    from apps.core.models import AuditEntry

    logged = AuditEntry.objects.filter(content_type=ContentType.objects.get_for_model(req), object_id=str(req.pk),
                                       action="update")
    assert any(e.changes.get("tenant_reminded_on", [None, None])[1] == str(today) for e in logged)
    Certificate.objects.create(requirement=req, issued_on=today - timedelta(days=345))  # runs out in about 20 days
    assert send_certificate_reminders(today + timedelta(days=31)) == 1
    req.refresh_from_db()
    Certificate.objects.create(requirement=req, issued_on=today)
    assert send_certificate_reminders(today + timedelta(days=70)) == 0  # in date again


def test_no_reminders_when_the_portal_is_off(portal):
    s = ModuleSettings.load()
    s.tenant_portal_enabled = False
    s.save()
    assert send_certificate_reminders() == 0
