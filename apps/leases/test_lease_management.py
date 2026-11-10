# SPDX-License-Identifier: AGPL-3.0-or-later
"""Lease management additions: dashboard counts, time of the essence, estimated rental value, documents for
review, demands on hold, billing contacts, arrears passed over and the holding purpose review."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.base import ContentFile
from django.urls import reverse

from apps.core.roles import ADMINISTRATORS
from apps.leases import events, workflow
from apps.leases.models import Lease, LeaseDocument, LeaseEvent, Party
from apps.properties.models import Property

TODAY = date.today()
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


@pytest.fixture
def admin_client(client, db):
    user = get_user_model().objects.create_user("boss", password="x", is_staff=True)
    user.groups.add(Group.objects.get(name=ADMINISTRATORS))
    client.force_login(user)
    return client


@pytest.fixture
def estate(db):
    prop = Property.objects.create(reference="P1", name="Shop", property_type="unit", holding_purpose="investment")
    tenant = Party.objects.create(name="Tenant Ltd", party_type="company", contact_name="Pat Main",
                                  email="pat@example.org", address="1 High Street")

    def lease(ref, **kw):
        kw.setdefault("term_start", TODAY - timedelta(days=400))
        kw.setdefault("agreement_type", "lease")
        obj = Lease.objects.create(reference=ref, counterparty=tenant, **kw)
        obj.properties.add(prop)
        workflow.sync_events(obj)
        return obj

    soon = TODAY + timedelta(days=60)
    return {
        "prop": prop, "tenant": tenant,
        "inside": lease("IN", term_end=soon, security_of_tenure="inside", annual_rent=Decimal("10000"),
                        review_basis="om_up", next_review_date=TODAY + timedelta(days=30), time_of_essence=True),
        "out": lease("OUT", term_end=soon, security_of_tenure="contracted_out", annual_rent=Decimal("4000"),
                     rent_frequency="monthly"),
        "late": lease("LATE", term_end=TODAY - timedelta(days=10), security_of_tenure="contracted_out"),
        "taw": lease("TAW", agreement_type="taw", term_end=None),
        "old_taw": lease("TAWX", agreement_type="taw", term_end=None, status="ended"),
    }


def test_expiries_split_by_1954_act_status(estate):
    rows = {r["type"]: r for r in events.event_summary()}
    assert rows["expiry"]["due"] == 2 and rows["expiry"]["overdue"] == 1
    assert rows["expiry_inside"]["due"] == 1 and rows["expiry_inside"]["overdue"] == 0
    assert rows["expiry_out"]["due"] == 1 and rows["expiry_out"]["overdue"] == 1
    assert "expiry_other" not in rows  # only shown when there is something in it
    assert rows["expiry_out"]["sub"] and rows["expiry_out"]["query"] == "type=expiry&security=out"


def test_dashboard_shows_tenancies_at_will_and_links(admin_client, estate):
    assert events.tenancies_at_will() == 1  # the ended one is not counted
    page = admin_client.get(reverse("dashboard") + "?view=estate").content.decode()
    assert "tenancy at will in place" in page and "agreement_type=taw&amp;live=1" in page
    assert "Contracted in" in page and "Contracted out" in page and "Time is of the essence" in page
    listed = admin_client.get(reverse("leases:list") + "?agreement_type=taw&live=1")
    assert [lease.reference for lease in listed.context["page_obj"]] == ["TAW"]
    out = admin_client.get(reverse("leases:events") + "?type=expiry&security=out&window=overdue")
    assert [e.lease.reference for e in out.context["page_obj"]] == ["LATE"]


def test_time_of_the_essence_is_flagged(admin_client, estate):
    assert events.essence_summary() == {"open": 1, "overdue": 0, "due": 1}
    review = estate["inside"].events.get(event_type="review")
    assert review.time_of_essence and not estate["inside"].events.get(event_type="expiry").time_of_essence
    listed = admin_client.get(reverse("leases:events") + "?type=review&essence=1")
    assert [e.pk for e in listed.context["page_obj"]] == [review.pk]
    assert b"Time is of the essence for this rent review" in admin_client.get(review.get_absolute_url()).content
    flagged = admin_client.get(reverse("leases:list") + "?flag=essence")
    assert [lease.reference for lease in flagged.context["page_obj"]] == ["IN"]


def test_estimated_rental_value_on_reviews_and_renewals(admin_client, estate):
    review = estate["inside"].events.get(event_type="review")
    resp = admin_client.post(review.get_absolute_url(), {
        "save_details": "1", "status": "in_progress", "estimated_rental_value": "12500", "outcome": "",
        "assigned_to": ""})
    assert resp.status_code == 302
    review.refresh_from_db()
    assert review.estimated_rental_value == Decimal("12500") and review.erv_uplift == Decimal("2500")
    assert b"above the current rent" in admin_client.get(review.get_absolute_url()).content
    # break and hand-added events do not carry one
    other = LeaseEvent.objects.create(lease=estate["inside"], event_type="other", title="Inspect",
                                      due_date=TODAY + timedelta(days=5))
    assert b"estimated_rental_value" not in admin_client.get(other.get_absolute_url()).content
    from apps.reports import datasets

    lease = datasets.get("leases").queryset().get(reference="IN")
    assert datasets.get("leases").field("erv").value(lease) == Decimal("12500")


def test_documents_for_review(admin_client, estate):
    def doc(lease, kind, review, name):
        return LeaseDocument.objects.create(lease=lease, document_type=kind, description=name, review_date=review,
                                            file=ContentFile(PDF, name="d.pdf"))

    overdue = doc(estate["inside"], "insurance", TODAY - timedelta(days=3), "Old certificate")
    doc(estate["out"], "schedule", TODAY + timedelta(days=40), "Schedule of condition")
    doc(estate["out"], "lease", None, "Signed lease")
    doc(estate["old_taw"], "other", TODAY - timedelta(days=3), "On an ended agreement")
    assert events.documents_for_review() == {"overdue": 1, "due": 1}
    assert overdue.review_rag()[0] == "red"
    page = admin_client.get(reverse("leases:documents") + "?window=overdue")
    assert [d.description for d in page.context["page_obj"]] == ["Old certificate"]
    both = admin_client.get(reverse("leases:documents"))
    assert len(both.context["page_obj"]) == 2
    download = admin_client.get(reverse("leases:documents") + "?format=csv")
    assert download.status_code == 200 and b"Date for review" in download.content
    assert b"Lease documents to review" in admin_client.get(reverse("dashboard") + "?view=estate").content


def test_tenant_insurance_certificate_case(admin_client, estate):
    from apps.cases.models import Case, CaseType

    lease = estate["out"]
    lease.insurance = "tenant"
    lease.save()
    page = admin_client.get(lease.get_absolute_url()).content.decode()
    assert "No insurance certificate held" in page and "type=insurance_certificate" in page
    case_type = CaseType.objects.get(code="insurance_certificate")
    form = admin_client.get(reverse("cases:new") + f"?lease={lease.pk}&type=insurance_certificate").context["form"]
    assert form.initial["case_type"] == case_type.pk
    admin_client.post(reverse("cases:new"), {
        "case_type": case_type.pk, "title": "Insurance certificate", "lease": lease.pk, "how_received": "email",
        "received_on": TODAY.isoformat()})
    case = Case.objects.get(case_type=case_type)
    assert case.lease == lease and case.tasks.count() == 4
    LeaseDocument.objects.create(lease=lease, document_type="insurance", description="Certificate 2026",
                                 review_date=TODAY + timedelta(days=300), file=ContentFile(PDF, name="c.pdf"))
    page = admin_client.get(lease.get_absolute_url()).content.decode()
    assert "Certificate held" in page and "No insurance certificate held" not in page and "Case open" in page


def test_demands_on_hold_are_not_raised(estate):
    from apps.ledger import billing

    lease = estate["out"]
    start, end = TODAY, TODAY + timedelta(days=45)
    assert any(c.lease_id == lease.pk for c in billing.proposed_charges(start, end))
    lease.demands_on_hold, lease.demands_on_hold_reason = True, "Dispute"
    lease.save()
    assert not any(c.lease_id == lease.pk for c in billing.proposed_charges(start, end))
    assert [held.reference for held in billing.held_leases()] == ["OUT"]
    lease.demands_on_hold = False
    lease.save()
    assert any(c.lease_id == lease.pk for c in billing.proposed_charges(start, end))  # caught up afterwards


def test_billing_contact_falls_back_to_the_tenant(estate):
    lease = estate["out"]
    assert not lease.has_billing_contact
    assert lease.billing == {"name": "Pat Main", "email": "pat@example.org", "phone": "", "address": "1 High Street"}
    lease.billing_contact_name, lease.billing_email = "Accounts", "accounts@example.org"
    lease.save()
    assert lease.has_billing_contact
    assert lease.billing["name"] == "Accounts" and lease.billing["email"] == "accounts@example.org"
    assert lease.billing["address"] == "1 High Street"  # only what differs is overridden
    from apps.ledger import finance
    from apps.ledger.models import Charge

    charge = Charge.objects.create(lease=lease, description="Rent", issue_date=TODAY, due_date=TODAY,
                                   net=Decimal("100"), gross=Decimal("100"))
    from apps.core.models import ModuleSettings

    row = dict(zip([c.label for c in finance.COLUMNS], next(finance._rows([charge], ModuleSettings.load()))))
    assert row["Customer name"] == "Tenant Ltd" and row["Billing contact"] == "Accounts"
    assert row["Billing email"] == "accounts@example.org" and row["Customer address"] == "1 High Street"


def test_arrears_passed_to_debt_collectors(admin_client, estate):
    from apps.core.models import ModuleSettings
    from apps.ledger.models import Charge

    settings = ModuleSettings.load()
    settings.rent_ledger_enabled = True
    settings.save()
    for key in ("out", "inside"):
        Charge.objects.create(lease=estate[key], description="Rent", issue_date=TODAY - timedelta(days=50),
                              due_date=TODAY - timedelta(days=40), net=Decimal("500"), gross=Decimal("500"))
    lease = estate["out"]
    lease.arrears_referral, lease.arrears_referred_on = "debt", TODAY - timedelta(days=2)
    lease.full_clean()
    lease.save()
    page = admin_client.get(reverse("ledger:arrears"))
    assert page.context["summary"]["count"] == 2 and b"External debt collectors" in page.content
    passed = admin_client.get(reverse("ledger:arrears") + "?referred=any").context["summary"]
    assert [a.lease.reference for a in passed["accounts"]] == ["OUT"] and passed["total"] == Decimal("500")
    still = admin_client.get(reverse("ledger:arrears") + "?referred=none").context["summary"]
    assert [a.lease.reference for a in still["accounts"]] == ["IN"]
    assert b"External debt collectors" in admin_client.get(reverse("ledger:arrears") + "?format=csv").content
    flagged = admin_client.get(reverse("leases:list") + "?flag=referred")
    assert [x.reference for x in flagged.context["page_obj"]] == ["OUT"]


def test_holding_purpose_strategy_section_and_review(admin_client, estate):
    prop = estate["prop"]
    prop.strategy_section, prop.purpose_review_date = "4.2 Investment estate", TODAY - timedelta(days=1)
    prop.save()
    Property.objects.create(reference="P2", name="Hall", property_type="building")
    page = admin_client.get(prop.get_absolute_url()).content.decode()
    assert "4.2 Investment estate" in page and "Review of purpose due" in page and "Overdue" in page
    listed = admin_client.get(reverse("properties:list") + "?purpose_review=overdue")
    assert [p.reference for p in listed.context["page_obj"]] == ["P1"]
    from apps.reports import datasets

    ds = datasets.get("properties")
    assert ds.field("strategy_section").value(prop) == "4.2 Investment estate"
    assert ds.field("purpose_review_date").value(prop) == TODAY - timedelta(days=1)
