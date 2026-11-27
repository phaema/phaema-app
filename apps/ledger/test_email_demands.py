# SPDX-License-Identifier: AGPL-3.0-or-later
"""Emailing a demand run through GOV.UK Notify, and recording emails when Notify is not set up."""
from datetime import date
from decimal import Decimal
from unittest import mock

import pytest
from django.contrib.auth.models import Group, User
from django.test import override_settings
from django.urls import reverse

from apps.core.models import ModuleSettings, OutgoingEmail
from apps.leases.models import Lease, Party
from apps.ledger import emails
from apps.ledger.models import Charge, DemandRun

pytestmark = pytest.mark.django_db


@pytest.fixture
def setup():
    s = ModuleSettings.load()
    s.rent_ledger_enabled = True
    s.email_demands = True
    s.organisation_name = "Example Council"
    s.letter_email = "estates@example.gov.uk"
    s.payment_link = "https://pay.example.gov.uk/rent?ref={reference}&amount={amount}"
    s.save()
    admin = User.objects.create_user("admin", password="pw")
    admin.groups.add(Group.objects.get_or_create(name="Administrators")[0])
    tenant = Party.objects.create(name="Cafe Ltd", party_type="company", email="cafe@example.com",
                                  contact_name="Ann Smith")
    nomail = Party.objects.create(name="No Mail Ltd", party_type="company")
    run = DemandRun.objects.create(due_from=date(2026, 12, 25), due_to=date(2027, 3, 24), issue_date=date(2026, 11, 27))
    leases = []
    for ref, party in (("L-1", tenant), ("L-2", nomail)):
        lease = Lease.objects.create(reference=ref, counterparty=party, direction="out", term_start=date(2025, 1, 1),
                                     premises_description=f"Shop {ref}")
        Charge.objects.create(lease=lease, run=run, kind="rent", description="Rent to 24 March 2027",
                              issue_date=run.issue_date, due_date=date(2026, 12, 25), net=Decimal("1000"),
                              vat=Decimal("200"), gross=Decimal("1200"))
        leases.append(lease)
    return admin, run, leases


def test_compose_lists_charges_total_and_pay_link(setup):
    _admin, run, _leases = setup
    d = emails.demands(run)[0]
    subject, body = emails.compose(d)
    assert "Example Council" in subject and "£1,200.00" in subject
    assert "Dear Ann Smith," in body and "Shop L-1" in body
    assert "Pay now: https://pay.example.gov.uk/rent?ref=" in body and "amount=1200.00" in body
    assert "estates@example.gov.uk" in body


def test_billing_email_on_the_agreement_wins(setup):
    _admin, run, leases = setup
    leases[0].billing_email = "accounts@example.com"
    leases[0].save()
    assert emails.demands(run)[0].to == "accounts@example.com"


@override_settings(PHAEMA_NOTIFY_API_KEY="", PHAEMA_NOTIFY_TEMPLATE_ID="")
def test_without_notify_emails_are_recorded_not_sent(setup, client):
    admin, run, _leases = setup
    client.force_login(admin)
    page = client.get(reverse("ledger:run-email", args=[run.pk]))
    assert page.status_code == 200 and b"not set up yet" in page.content
    client.post(reverse("ledger:run-email", args=[run.pk]))
    sent = list(OutgoingEmail.objects.all())
    assert len(sent) == 1  # the agreement with no address is skipped
    assert sent[0].status == OutgoingEmail.Status.RECORDED and sent[0].to == "cafe@example.com"
    assert sent[0].created_by == admin and sent[0].demand_run == run
    client.post(reverse("ledger:run-email", args=[run.pk]))
    assert OutgoingEmail.objects.count() == 1  # each agreement once per run


@override_settings(PHAEMA_NOTIFY_API_KEY="test-key", PHAEMA_NOTIFY_TEMPLATE_ID="tmpl")
def test_with_notify_emails_are_sent_and_failures_can_be_retried(setup, client):
    admin, run, _leases = setup
    client.force_login(admin)
    with mock.patch("apps.core.notify._client") as make:
        make.return_value.send_email_notification.side_effect = RuntimeError("400 bad request")
        client.post(reverse("ledger:run-email", args=[run.pk]))
    email = OutgoingEmail.objects.get()
    assert email.status == OutgoingEmail.Status.FAILED and "400" in email.error
    with mock.patch("apps.core.notify._client") as make:
        make.return_value.send_email_notification.return_value = {"id": "abc-123"}
        client.post(reverse("ledger:run-email", args=[run.pk]))  # without "again": nothing new
        assert not make.return_value.send_email_notification.called
        client.post(reverse("ledger:run-email", args=[run.pk]), {"again": "1"})
        kwargs = make.return_value.send_email_notification.call_args.kwargs
    assert kwargs["template_id"] == "tmpl" and kwargs["email_address"] == "cafe@example.com"
    assert set(kwargs["personalisation"]) == {"subject", "body"}
    latest = OutgoingEmail.objects.order_by("-pk").first()
    assert latest.status == OutgoingEmail.Status.SENT and latest.notify_id == "abc-123" and latest.sent_at


def test_only_finance_people_and_only_when_switched_on(setup, client):
    admin, run, _leases = setup
    viewer = User.objects.create_user("viewer", password="pw")
    viewer.groups.add(Group.objects.get_or_create(name="Viewers")[0])
    client.force_login(viewer)
    assert client.post(reverse("ledger:run-email", args=[run.pk])).status_code == 403
    s = ModuleSettings.load()
    s.email_demands = False
    s.save()
    client.force_login(admin)
    assert client.get(reverse("ledger:run-email", args=[run.pk])).status_code == 403
    assert OutgoingEmail.objects.count() == 0


def test_emails_cannot_be_changed_or_deleted_in_admin(setup, client):
    admin, run, _leases = setup
    admin.is_staff = admin.is_superuser = True
    admin.save()
    email = OutgoingEmail.objects.create(kind="demand", to="x@example.com", subject="s", body="b")
    client.force_login(admin)
    url = reverse("admin:core_outgoingemail_change", args=[email.pk])
    assert client.get(url).status_code == 200
    client.post(url, {"to": "y@example.com"})
    email.refresh_from_db()
    assert email.to == "x@example.com"
    assert client.post(reverse("admin:core_outgoingemail_delete", args=[email.pk]), {"post": "yes"}).status_code == 403
