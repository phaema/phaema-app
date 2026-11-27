# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tenant portal: sign-in by emailed code, strict separation between tenants, rights, contact changes."""
import re
import time
from datetime import date, timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.contrib.auth.models import Group, User
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.test import override_settings

from apps.core.models import AuditEntry, ModuleSettings, OutgoingEmail
from apps.leases.models import Lease, LeaseDocument, Party
from apps.ledger.models import Charge, DemandRun
from apps.portal import access
from apps.portal.models import ContactChange, PortalAccount, SignInCode

pytestmark = pytest.mark.django_db
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
NOTIFY = {"PHAEMA_NOTIFY_API_KEY": "k", "PHAEMA_NOTIFY_TEMPLATE_ID": "t"}


@pytest.fixture
def world():
    cache.clear()
    s = ModuleSettings.load()
    s.tenant_portal_enabled = s.rent_ledger_enabled = True
    s.organisation_name = "Example Council"
    s.payment_link = "https://pay.example.gov.uk/?ref={reference}&amount={amount}"
    s.portal_welcome = "Call us on 01234 567890."
    s.save()
    cafe = Party.objects.create(name="Cafe Ltd", party_type="company", email="cafe@example.com")
    shop = Party.objects.create(name="Shop Ltd", party_type="company")
    leases = {}
    for ref, party in (("L-CAFE", cafe), ("L-SHOP", shop)):
        lease = Lease.objects.create(reference=ref, counterparty=party, direction="out", term_start=date(2024, 1, 1),
                                     premises_description=f"Unit {ref}", next_review_date=date.today() + timedelta(60))
        run = DemandRun.objects.create(due_from=date.today(), due_to=date.today(), issue_date=date.today())
        Charge.objects.create(lease=lease, run=run, kind="rent", description="Quarter's rent",
                              issue_date=date.today(), due_date=date.today() - timedelta(days=40),
                              net=Decimal("500"), vat=Decimal("100"), gross=Decimal("600"))
        leases[ref] = lease
    ann = PortalAccount.objects.create(party=cafe, name="Ann", email="Ann@Example.com")
    bob = PortalAccount.objects.create(party=shop, name="Bob", email="bob@example.com", finance=False,
                                       facilities=True)
    return leases, ann, bob


def _sign_in(client, account):
    """Sign in through the real pages, capturing the code sent to Notify."""
    with override_settings(**NOTIFY), mock.patch("apps.core.notify._client") as make:
        make.return_value.send_email_notification.return_value = {"id": "n1"}
        client.post("/tenant/sign-in/", {"email": account.email})
        body = make.return_value.send_email_notification.call_args.kwargs["personalisation"]["body"]
    code = re.search(r"\b(\d{6})\b", body).group(1)
    return client.post("/tenant/sign-in/code/", {"code": code})


def test_portal_is_off_by_default(world, client):
    s = ModuleSettings.load()
    s.tenant_portal_enabled = False
    s.save()
    assert client.get("/tenant/sign-in/").status_code == 404
    assert client.get("/tenant/").status_code == 404


def test_sign_in_with_emailed_code(world, client):
    _leases, ann, _bob = world
    assert ann.email == "ann@example.com"
    response = _sign_in(client, ann)
    assert response.status_code == 302 and response["Location"] == "/tenant/"
    home = client.get("/tenant/")
    assert b"L-CAFE" in home.content and b"L-SHOP" not in home.content and b"01234 567890" in home.content
    recorded = OutgoingEmail.objects.get(kind="portal_code")
    assert "••••••" in recorded.body and not re.search(r"\b\d{6}\b", recorded.body)  # the code is not kept
    ann.refresh_from_db()
    assert ann.last_sign_in is not None


def test_unknown_address_gets_the_same_page_and_no_email(world, client):
    response = client.post("/tenant/sign-in/", {"email": "nobody@example.com"})
    assert response.status_code == 302 and response["Location"] == "/tenant/sign-in/code/"
    assert not OutgoingEmail.objects.filter(kind="portal_code").exists()
    assert client.post("/tenant/sign-in/code/", {"code": "123456"}).status_code == 200
    assert client.get("/tenant/").status_code == 302


def test_wrong_codes_use_up_the_code(world, client):
    _leases, ann, _bob = world
    with override_settings(**NOTIFY), mock.patch("apps.core.notify._client") as make:
        make.return_value.send_email_notification.return_value = {"id": "n1"}
        client.post("/tenant/sign-in/", {"email": ann.email})
        body = make.return_value.send_email_notification.call_args.kwargs["personalisation"]["body"]
    code = re.search(r"\b(\d{6})\b", body).group(1)
    wrong = "000000" if code != "000000" else "111111"
    for _i in range(SignInCode.TRIES):
        client.post("/tenant/sign-in/code/", {"code": wrong})
    client.post("/tenant/sign-in/code/", {"code": code})
    assert client.get("/tenant/").status_code == 302  # still signed out


def test_expired_code_is_refused(world, client):
    _leases, ann, _bob = world
    row, code = SignInCode.issue(ann)
    SignInCode.objects.filter(pk=row.pk).update(expires_at=row.created_at - timedelta(minutes=1))
    assert not SignInCode.objects.get(pk=row.pk).matches(code)


@override_settings(PHAEMA_PORTAL_SHOW_CODES=True, PHAEMA_NOTIFY_API_KEY="", PHAEMA_NOTIFY_TEMPLATE_ID="")
def test_test_sites_can_show_the_code_when_notify_is_not_set_up(world, client):
    _leases, ann, _bob = world
    client.post("/tenant/sign-in/", {"email": ann.email})
    page = client.get("/tenant/sign-in/code/").content.decode()
    code = re.search(r"your code is (\d{6})", page).group(1)
    client.post("/tenant/sign-in/code/", {"code": code})
    assert client.get("/tenant/").status_code == 200


def test_tenants_only_see_their_own_agreements_and_shared_documents(world, client):
    leases, ann, _bob = world
    mine = LeaseDocument.objects.create(lease=leases["L-CAFE"], document_type="lease", description="Signed lease",
                                        file=ContentFile(PDF, "a.pdf"), shared_with_tenant=True)
    private = LeaseDocument.objects.create(lease=leases["L-CAFE"], document_type="other", description="Internal",
                                           file=ContentFile(PDF, "b.pdf"))
    theirs = LeaseDocument.objects.create(lease=leases["L-SHOP"], document_type="lease", description="Shop lease",
                                          file=ContentFile(PDF, "c.pdf"), shared_with_tenant=True)
    _sign_in(client, ann)
    page = client.get(f"/tenant/agreements/{leases['L-CAFE'].pk}/").content.decode()
    assert "Signed lease" in page and "Internal" not in page
    assert client.get(f"/tenant/documents/{mine.pk}/").status_code == 200
    assert client.get(f"/tenant/documents/{private.pk}/").status_code == 404
    assert client.get(f"/tenant/documents/{theirs.pk}/").status_code == 404
    assert client.get(f"/tenant/agreements/{leases['L-SHOP'].pk}/").status_code == 404
    assert client.get(f"/tenant/agreements/{leases['L-SHOP'].pk}/contact/").status_code == 404


def test_finance_view_shows_balance_overdue_and_pay_now(world, client):
    leases, ann, _bob = world
    _sign_in(client, ann)
    page = client.get(f"/tenant/agreements/{leases['L-CAFE'].pk}/").content.decode()
    assert "£600.00" in page and "Overdue" in page and "Pay now" in page
    assert "https://pay.example.gov.uk/?ref=PHC" in page and "Rent review" in page


def test_facilities_only_account_sees_no_money(world, client):
    leases, _ann, bob = world
    _sign_in(client, bob)
    page = client.get(f"/tenant/agreements/{leases['L-SHOP'].pk}/").content.decode()
    assert "£600.00" not in page and "Pay now" not in page and "Rent review" in page
    assert client.get(f"/tenant/agreements/{leases['L-SHOP'].pk}/contact/").status_code == 404


def test_contact_change_waits_for_estates_and_is_logged_as_portal(world, client):
    leases, ann, _bob = world
    lease = leases["L-CAFE"]
    _sign_in(client, ann)
    form = client.get(f"/tenant/agreements/{lease.pk}/contact/")
    assert form.status_code == 200 and b"cafe@example.com" in form.content
    client.post(f"/tenant/agreements/{lease.pk}/contact/", {"contact_name": "Accounts", "email": "ap@cafe.example",
                                                            "phone": "", "address": "1 High St", "note": ""})
    change = ContactChange.objects.get()
    assert change.status == "waiting" and change.account == ann
    lease.refresh_from_db()
    assert lease.billing_email == ""  # nothing changes yet
    entry = AuditEntry.objects.filter(object_id=str(change.pk), content_type__model="contactchange").get()
    assert entry.via.startswith("Tenant portal") and entry.user is None
    staff = User.objects.create_user("sam")
    change.accept(staff)
    lease.refresh_from_db()
    assert lease.billing_email == "ap@cafe.example" and lease.billing_contact_name == "Accounts"


def test_access_ends_a_year_after_the_agreement(world, client):
    leases, ann, _bob = world
    _sign_in(client, ann)
    lease = leases["L-CAFE"]
    lease.status, lease.actual_end = Lease.Status.ENDED, date.today() - timedelta(days=200)
    lease.term_end = lease.actual_end
    lease.save()
    assert client.get("/tenant/").status_code == 200  # within 12 months
    lease.actual_end = lease.term_end = date.today() - timedelta(days=400)
    lease.save()
    assert client.get("/tenant/").status_code == 302  # no agreements left: signed out


def test_deactivated_account_is_signed_out_at_once(world, client):
    _leases, ann, _bob = world
    _sign_in(client, ann)
    assert b"signed out" in client.post("/tenant/sign-out/").content
    assert client.get("/tenant/").status_code == 302
    _sign_in(client, ann)
    PortalAccount.objects.filter(pk=ann.pk).update(active=False)
    assert client.get("/tenant/").status_code == 302


@override_settings(PHAEMA_PORTAL_IDLE_MINUTES=30)
def test_idle_sessions_end(world, client):
    _leases, ann, _bob = world
    _sign_in(client, ann)
    session = client.session
    session[access.SEEN_KEY] = int(time.time()) - 31 * 60
    session.save()
    assert client.get("/tenant/").status_code == 302


def test_portal_session_gives_no_staff_access(world, client):
    _leases, ann, _bob = world
    _sign_in(client, ann)
    assert client.get("/").status_code == 302  # staff sign-in page
    assert client.get("/admin/").status_code == 302
    assert client.get("/api/properties/").status_code in (401, 403)


def test_portal_pages_have_their_own_policy_and_are_not_cached(world, client):
    page = client.get("/tenant/sign-in/")
    assert "tile.openstreetmap.org" not in page["Content-Security-Policy"]
    assert "no-store" in page["Cache-Control"]


def test_invitation_sent_when_estates_add_an_account(world, client):
    leases, _ann, _bob = world
    admin = User.objects.create_user("admin", password="pw", is_staff=True)
    admin.groups.add(Group.objects.get_or_create(name="Administrators")[0])
    client.force_login(admin)
    party = leases["L-CAFE"].counterparty
    client.post("/admin/portal/portalaccount/add/", {"party": party.pk, "name": "Cath", "email": "cath@cafe.example",
                                                      "finance": "on", "active": "on"})
    account = PortalAccount.objects.get(email="cath@cafe.example")
    assert account.invited_by == admin
    invite = OutgoingEmail.objects.get(kind="portal_invite")
    assert "/tenant/sign-in/" in invite.body and invite.to == "cath@cafe.example"


def test_staff_share_a_document_and_demand_emails_link_to_the_portal(world, client):
    leases, _ann, _bob = world
    admin = User.objects.create_user("admin2", password="pw")
    admin.groups.add(Group.objects.get_or_create(name="Administrators")[0])
    client.force_login(admin)
    doc = LeaseDocument.objects.create(lease=leases["L-CAFE"], document_type="lease", file=ContentFile(PDF, "d.pdf"))
    client.post(f"/leases/documents/{doc.pk}/share/", {"share": "1"})
    doc.refresh_from_db()
    assert doc.shared_with_tenant
    from apps.ledger import emails

    run = leases["L-CAFE"].charges.first().run
    _subject, body = emails.compose(emails.demands(run)[0])
    assert "/tenant/sign-in/" in body


def test_old_sign_in_codes_are_deleted(world):
    _leases, ann, _bob = world
    old, _code = SignInCode.issue(ann)
    SignInCode.objects.filter(pk=old.pk).update(created_at=old.created_at - timedelta(days=2))
    fresh, _code = SignInCode.issue(ann)
    assert SignInCode.purge() == 1
    assert list(SignInCode.objects.all()) == [fresh]
