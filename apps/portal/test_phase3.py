# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tenant portal phase 3: messages answered by the managing surveyor or their cover, insurance, rent deposit and
payment plan progress."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from apps.core.models import Cover, ModuleSettings, OutgoingEmail
from apps.leases.models import DepositEntry, Lease, LeaseDocument, Party
from apps.ledger import creditcontrol
from apps.portal.models import PortalAccount, PortalMessage
from apps.portal.tests import _sign_in
from apps.properties.models import Property

pytestmark = pytest.mark.django_db
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def _staff(user):
    c = Client(HTTP_HOST="localhost")
    c.force_login(user)
    return c


@pytest.fixture
def world(make_user):
    from django.core.cache import cache

    cache.clear()
    s = ModuleSettings.load()
    s.tenant_portal_enabled = s.rent_ledger_enabled = True
    s.save()
    sam = make_user("sam", "Surveyors", email="sam@council.example", first_name="Sam")
    cara = make_user("cara", "Surveyors", email="cara@council.example", first_name="Cara")
    unit = Property.objects.create(reference="U1", name="Unit 1", property_type="unit", managing_surveyor=sam)
    cafe = Party.objects.create(name="Cafe Ltd", party_type="company")
    lease = Lease.objects.create(reference="L-1", counterparty=cafe, direction="out", term_start=date(2024, 1, 1),
                                 insurance="tenant", annual_rent=Decimal("12000"), rent_frequency="monthly")
    lease.properties.add(unit)
    ann = PortalAccount.objects.create(party=cafe, name="Ann", email="ann@cafe.example", facilities=True)
    fay = PortalAccount.objects.create(party=cafe, name="Fay", email="fay@cafe.example", finance=False,
                                       facilities=True)
    return {"sam": sam, "cara": cara, "unit": unit, "lease": lease, "ann": ann, "fay": fay}


def test_tenant_message_goes_to_the_surveyor_and_cover(world, client):
    lease = world["lease"]
    Cover.objects.create(user=world["cara"], covered=world["sam"], starts_on=date.today() - timedelta(days=1),
                         ends_on=date.today() + timedelta(days=5))
    _sign_in(client, world["ann"])
    client.post(f"/tenant/agreements/{lease.pk}/messages/", {"text": "Can we talk about the yard?"})
    message = PortalMessage.objects.get()
    assert message.direction == "in" and message.account == world["ann"]
    assert sorted(mail.outbox[-1].to) == ["cara@council.example", "sam@council.example"]
    assert "yard" not in mail.outbox[-1].body  # the text stays in PHAEMA
    for user in (world["sam"], world["cara"]):
        assert "Message from a tenant" in _staff(user).get("/?view=mine").content.decode()


def test_staff_reply_tells_the_tenant_and_shows_in_the_portal(world, client):
    lease = world["lease"]
    _sign_in(client, world["ann"])
    client.post(f"/tenant/agreements/{lease.pk}/messages/", {"text": "Question"})
    sam = _staff(world["sam"])
    assert b"Question" in sam.get(f"/leases/{lease.pk}/messages/").content
    sam.post(f"/leases/{lease.pk}/messages/", {"text": "Answer about the yard"})
    assert PortalMessage.objects.get(direction="in").answered_at is not None
    email = OutgoingEmail.objects.get(kind="portal_message")
    assert email.to == "ann@cafe.example" and "Answer about the yard" not in email.body
    assert "Message from a tenant" not in sam.get("/?view=mine").content.decode()
    page = client.get(f"/tenant/agreements/{lease.pk}/").content.decode()
    assert "1 new reply" in page
    thread = client.get(f"/tenant/agreements/{lease.pk}/messages/").content.decode()
    assert "Answer about the yard" in thread and "Sam" in thread
    assert "new reply" not in client.get(f"/tenant/agreements/{lease.pk}/").content.decode()


def test_messages_with_no_surveyor_go_to_administrators(world, client, make_user):
    world["unit"].managing_surveyor = None
    world["unit"].save()
    admin = make_user("ada", "Administrators", email="ada@council.example")
    _sign_in(client, world["ann"])
    client.post(f"/tenant/agreements/{world['lease'].pk}/messages/", {"text": "Hello"})
    assert mail.outbox[-1].to == ["ada@council.example"]
    assert "Message from a tenant" in _staff(admin).get("/?view=mine").content.decode()


def test_viewers_cannot_open_or_answer(world, make_user):
    viewer = _staff(make_user("vic", "Viewers"))
    assert viewer.get(f"/leases/{world['lease'].pk}/messages/").status_code == 403


def test_message_about_a_request(world, client):
    from apps.cases.models import CaseType

    lease = world["lease"]
    _sign_in(client, world["ann"])
    client.post(f"/tenant/agreements/{lease.pk}/request/", {
        "case_type": CaseType.objects.get(code="signage").pk, "title": "Sign", "details": "A sign"})
    case = lease.cases.get()
    assert f"?case={case.pk}".encode() in client.get(f"/tenant/requests/{case.pk}/").content
    client.post(f"/tenant/agreements/{lease.pk}/messages/", {"case": case.pk, "text": "Any news?"})
    assert PortalMessage.objects.get().case == case


def test_tenant_sends_insurance_certificate(world, client):
    lease = world["lease"]
    _sign_in(client, world["fay"])
    page = client.get(f"/tenant/agreements/{lease.pk}/").content.decode()
    assert "Tenant insures" in page and "do not have a copy" in page
    client.post(f"/tenant/agreements/{lease.pk}/insurance/", {
        "insurer": "Acme Mutual", "valid_until": (date.today() - timedelta(days=1)).isoformat(),
        "file": SimpleUploadedFile("cover.pdf", PDF, "application/pdf")})
    assert not LeaseDocument.objects.exists()  # cover already run out
    client.post(f"/tenant/agreements/{lease.pk}/insurance/", {
        "insurer": "Acme Mutual", "valid_until": (date.today() + timedelta(days=300)).isoformat(),
        "file": SimpleUploadedFile("cover.pdf", PDF, "application/pdf")})
    doc = LeaseDocument.objects.get()
    assert doc.document_type == "insurance" and doc.portal_account == world["fay"] and doc.review_date
    assert lease.insurance_certificate() == doc
    assert "The latest certificate we have" in client.get(f"/tenant/agreements/{lease.pk}/").content.decode()


def test_insurance_upload_only_where_the_tenant_insures(world, client):
    lease = world["lease"]
    lease.insurance = "landlord_recharged"
    lease.save()
    _sign_in(client, world["ann"])
    assert client.get(f"/tenant/agreements/{lease.pk}/insurance/").status_code == 404


def test_deposit_and_payment_plan_for_finance_accounts(world, client):
    lease = world["lease"]
    DepositEntry.objects.create(lease=lease, date=date(2024, 1, 1), kind="received", amount=Decimal("3000"))
    DepositEntry.objects.create(lease=lease, date=date(2025, 1, 1), kind="drawdown", amount=Decimal("500"),
                                notes="January rent")
    creditcontrol.make_plan(lease, date.today() - timedelta(days=40), Decimal("600"), 3,
                            date.today() - timedelta(days=10))
    _sign_in(client, world["ann"])
    page = client.get(f"/tenant/agreements/{lease.pk}/").content.decode()
    assert "Your rent deposit" in page and "£2,500.00" in page and "January rent" in page
    assert "Your payment plan" in page and "Instalments" in page
    client.post("/tenant/sign-out/")
    _sign_in(client, world["fay"])  # facilities only
    page = client.get(f"/tenant/agreements/{lease.pk}/").content.decode()
    assert "Your rent deposit" not in page and "Your payment plan" not in page
