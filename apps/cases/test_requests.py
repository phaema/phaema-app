# SPDX-License-Identifier: AGPL-3.0-or-later
"""Requests that open a case, from the tenant portal and from council departments."""
from datetime import date

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from apps.cases.models import Case, CaseType
from apps.core.models import ModuleSettings
from apps.leases.models import Lease, Party
from apps.portal.models import PortalAccount
from apps.portal.tests import _sign_in
from apps.properties.models import Property
from apps.space.test_costs import setup  # noqa: F401  (the fixture)

pytestmark = pytest.mark.django_db
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def _client(user):
    c = Client(HTTP_HOST="localhost")
    c.force_login(user)
    return c


@pytest.fixture
def world(make_user, setup):  # noqa: F811
    from django.core.cache import cache

    cache.clear()
    s = ModuleSettings.load()
    s.tenant_portal_enabled = True
    s.save()
    sam = make_user("sam", "Surveyors")
    unit = Property.objects.create(reference="U1", name="Unit 1", property_type="unit", managing_surveyor=sam)
    cafe = Party.objects.create(name="Cafe Ltd", party_type="company")
    shop = Party.objects.create(name="Shop Ltd", party_type="company")
    lease = Lease.objects.create(reference="L-1", counterparty=cafe, direction="out", term_start=date(2024, 1, 1))
    lease.properties.add(unit)
    other = Lease.objects.create(reference="L-2", counterparty=shop, direction="out", term_start=date(2024, 1, 1))
    other.properties.add(unit)
    ann = PortalAccount.objects.create(party=cafe, name="Ann", email="ann@cafe.example", finance=False)
    bob = PortalAccount.objects.create(party=shop, name="Bob", email="bob@shop.example")
    setup["building"].managing_surveyor = sam
    setup["building"].save()
    lee = make_user("lee", first_name="Lee", last_name="Okafor")
    head = make_user("head")
    setup["housing"].liaison = lee
    setup["housing"].save()
    setup["housing"].readers.add(head)
    return {"sam": sam, "lease": lease, "other": other, "ann": ann, "bob": bob, "lee": lee, "head": head, **setup}


def test_shipped_types_say_who_can_ask():
    assert CaseType.objects.get(code="assignment").tenant_can_start
    assert CaseType.objects.get(code="alterations").request_documents
    assert CaseType.objects.get(code="space_request").department_can_start
    assert not CaseType.objects.get(code="arrears").tenant_can_start


def test_tenant_asks_for_consent_and_follows_it(world, client):
    lease = world["lease"]
    _sign_in(client, world["ann"])
    form = client.get(f"/tenant/agreements/{lease.pk}/request/").content.decode()
    assert "Consent to assign" in form and "Rent arrears" not in form and "Drawings of the works" in form
    alterations = CaseType.objects.get(code="alterations")
    response = client.post(f"/tenant/agreements/{lease.pk}/request/", {
        "case_type": alterations.pk, "title": "New shopfront", "details": "Replace the shopfront in March.",
        "files": [SimpleUploadedFile("drawings.pdf", PDF, "application/pdf")]})
    case = Case.objects.get()
    assert case.display_reference.encode() in response.content
    assert case.how_received == "portal" and case.portal_account == world["ann"] and case.lease == lease
    assert case.owner == world["sam"] and case.party == lease.counterparty and case.target_date
    assert case.correspondence.get().summary == "Replace the shopfront in March."
    doc = case.documents.get()
    assert doc.shared_with_requester and doc.original_filename == "drawings.pdf"
    assert case.tasks.filter(description__startswith="Acknowledge").exists()
    page = client.get(f"/tenant/agreements/{lease.pk}/").content.decode()
    assert "Licence for alterations" in page and "Received" in page
    detail = client.get(f"/tenant/requests/{case.pk}/").content.decode()
    assert "drawings.pdf" in detail and "Target date" in detail
    assert client.get(f"/tenant/requests/{case.pk}/documents/{doc.pk}/").status_code == 200


def test_tenants_see_only_portal_requests_on_their_agreements(world, client):
    from apps.cases import workflow

    lease = world["lease"]
    internal = workflow.open_case(CaseType.objects.get(code="arrears"), title="Arrears", lease=lease)
    _sign_in(client, world["bob"])
    client.post(f"/tenant/agreements/{world['other'].pk}/request/", {
        "case_type": CaseType.objects.get(code="signage").pk, "title": "Sign", "details": "A sign"})
    theirs = Case.objects.get(how_received="portal")
    client.post("/tenant/sign-out/")
    _sign_in(client, world["ann"])
    assert client.get(f"/tenant/requests/{internal.pk}/").status_code == 404
    assert client.get(f"/tenant/requests/{theirs.pk}/").status_code == 404
    assert b"Arrears" not in client.get(f"/tenant/agreements/{lease.pk}/").content


def test_only_shared_documents_reach_the_tenant(world, client):
    from django.core.files.base import ContentFile

    lease = world["lease"]
    _sign_in(client, world["ann"])
    client.post(f"/tenant/agreements/{lease.pk}/request/", {
        "case_type": CaseType.objects.get(code="assignment").pk, "title": "Assign", "details": "To X Ltd"})
    case = Case.objects.get()
    internal = case.documents.create(description="Covenant check", file=ContentFile(PDF, "check.pdf"))
    assert client.get(f"/tenant/requests/{case.pk}/documents/{internal.pk}/").status_code == 404
    assert b"Covenant check" not in client.get(f"/tenant/requests/{case.pk}/").content
    sam = _client(world["sam"])
    assert b"Share with the person who asked" in sam.get(case.get_absolute_url()).content
    sam.post(f"/cases/documents/{internal.pk}/share/", {"share": "1"})
    assert client.get(f"/tenant/requests/{case.pk}/documents/{internal.pk}/").status_code == 200


def test_decision_shown_to_the_tenant(world, client):
    lease = world["lease"]
    _sign_in(client, world["ann"])
    client.post(f"/tenant/agreements/{lease.pk}/request/", {
        "case_type": CaseType.objects.get(code="change_of_use").pk, "title": "Cafe to bakery", "details": "x"})
    case = Case.objects.get()
    case.decision, case.decision_on, case.reasons = "conditions", date.today(), "Opening hours 7am to 6pm."
    case.status = "closed"
    case.save()
    page = client.get(f"/tenant/requests/{case.pk}/").content.decode()
    assert "Approved with conditions" in page and "Opening hours 7am to 6pm." in page


def test_department_space_request(world):
    building = world["building"]
    lee = _client(world["lee"])
    assert b"Make a request" in lee.get(f"/occupier/building/{building.pk}/").content
    form = lee.get(f"/occupier/building/{building.pk}/request/").content.decode()
    assert "Space request from a department" in form and "Consent to assign" not in form
    lee.post(f"/occupier/building/{building.pk}/request/", {
        "case_type": CaseType.objects.get(code="space_request").pk, "title": "Six more desks",
        "details": "The team grows by 6 in April."})
    case = Case.objects.get()
    assert case.how_received == "dept" and case.occupier == world["housing"] and case.requested_by == world["lee"]
    assert case.property == building and case.owner == world["sam"]
    assert b"Six more desks" in lee.get(f"/occupier/building/{building.pk}/").content
    assert lee.get(f"/occupier/requests/{case.pk}/").status_code == 200
    head = _client(world["head"])
    assert head.get(f"/occupier/building/{building.pk}/request/").status_code == 404
    assert head.get(f"/occupier/requests/{case.pk}/").status_code == 200  # can follow it


def test_requests_with_no_owner_reach_administrators(world, client, make_user):
    world["lease"].properties.first().managing_surveyor = None
    unit = world["lease"].properties.first()
    unit.managing_surveyor = None
    unit.save()
    _sign_in(client, world["ann"])
    client.post(f"/tenant/agreements/{world['lease'].pk}/request/", {
        "case_type": CaseType.objects.get(code="signage").pk, "title": "Sign", "details": "A sign"})
    case = Case.objects.get()
    assert case.owner is None
    admin = _client(make_user("ada", "Administrators"))
    assert "Request with no one to deal with it" in admin.get("/?view=mine").content.decode()
