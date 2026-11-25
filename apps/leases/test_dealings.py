# SPDX-License-Identifier: AGPL-3.0-or-later
"""The dealings register: consent cases open dealings, completing an assignment changes the tenant, history is kept."""
from datetime import date
from decimal import Decimal

import pytest

from apps.cases import workflow as case_workflow
from apps.cases.models import Case, CaseType
from apps.leases import dealings
from apps.leases.models import Dealing, Lease, Party
from apps.properties.models import Property


@pytest.fixture
def surveyor(make_user):
    return make_user("sue", "Surveyors", email="sue@example.org")


@pytest.fixture
def lease(db, surveyor):
    prop = Property.objects.create(reference="P1", name="Shop", property_type="unit", managing_surveyor=surveyor)
    tenant = Party.objects.create(name="Old Tenant Ltd", party_type="company")
    guarantor = Party.objects.create(name="Old Guarantor", party_type="individual")
    obj = Lease.objects.create(reference="L1", agreement_type="lease", counterparty=tenant, guarantor=guarantor,
                               term_start=date(2020, 1, 1), term_end=date(2035, 12, 31), annual_rent=Decimal("10000"),
                               assignment_terms="consent", aga_on_assignment=True)
    obj.properties.add(prop)
    return obj


@pytest.fixture
def assignee(db):
    return Party.objects.create(name="New Tenant Ltd", party_type="company")


def test_consent_case_opens_a_dealing_and_the_decision_moves_it_on(lease, surveyor, client):
    case = case_workflow.open_case(CaseType.objects.get(code="assignment"), title="Consent to assign", lease=lease)
    dealing = Dealing.objects.get(case=case)
    assert dealing.kind == Dealing.Kind.ASSIGNMENT and dealing.status == Dealing.Status.PROPOSED
    assert dealing.from_party == lease.counterparty
    case.decision, case.decision_on = Case.Decision.CONDITIONS, date(2026, 3, 1)
    case.save()
    dealings.from_case(case)
    dealing.refresh_from_db()
    assert dealing.status == Dealing.Status.CONSENTED and dealing.consent_on == date(2026, 3, 1)


def test_other_case_types_open_no_dealing(lease):
    case_workflow.open_case(CaseType.objects.get(code="alterations"), title="Alterations", lease=lease)
    assert not Dealing.objects.exists()


def test_completing_an_assignment_changes_the_tenant_and_keeps_the_history(lease, assignee, surveyor, client):
    old = lease.counterparty
    new_guarantor = Party.objects.create(name="New Guarantor", party_type="individual")
    dealing = Dealing.objects.create(lease=lease, kind=Dealing.Kind.ASSIGNMENT, status=Dealing.Status.CONSENTED,
                                     to_party=assignee, guarantor=new_guarantor, aga=True)
    client.force_login(surveyor)
    response = client.post(f"/leases/dealings/{dealing.pk}/complete/", {"completed_on": "2026-04-01"})
    assert response.status_code == 302
    lease.refresh_from_db()
    dealing.refresh_from_db()
    assert lease.counterparty == assignee and lease.guarantor == new_guarantor
    assert dealing.status == Dealing.Status.COMPLETED and dealing.from_party == old
    assert dealings.tenants(lease) == [(old, date(2020, 1, 1), date(2026, 4, 1), True),
                                       (assignee, date(2026, 4, 1), None, False)]
    assert dealings.liable_former_tenants(lease) == [old]
    roles = {str(r["role"]) for r in old.arrangements()}
    assert roles == {"Former tenant (guarantor under an AGA)"}
    page = client.get(lease.get_absolute_url()).content.decode()
    assert "Former tenant still liable" in page and "Who has held this agreement" in page


def test_a_second_assignment_releases_the_first_aga(lease, assignee):
    first = Dealing.objects.create(lease=lease, kind=Dealing.Kind.ASSIGNMENT, to_party=assignee, aga=True)
    dealings.complete(first, completed_on=date(2025, 1, 1))
    third = Party.objects.create(name="Third Tenant", party_type="company")
    second = Dealing.objects.create(lease=lease, kind=Dealing.Kind.ASSIGNMENT, to_party=third, aga=False)
    dealings.complete(second, completed_on=date(2026, 1, 1))
    lease.refresh_from_db()
    assert lease.counterparty == third and dealings.liable_former_tenants(lease) == []
    assert [row[0].name for row in dealings.tenants(lease)] == ["Old Tenant Ltd", "New Tenant Ltd", "Third Tenant"]


def test_completion_needs_the_other_party(lease, surveyor, client):
    dealing = Dealing.objects.create(lease=lease, kind=Dealing.Kind.ASSIGNMENT)
    client.force_login(surveyor)
    client.post(f"/leases/dealings/{dealing.pk}/complete/", {"completed_on": "2026-04-01"})
    dealing.refresh_from_db()
    assert dealing.status == Dealing.Status.PROPOSED


def test_underlease_completion_leaves_the_tenant(lease, assignee):
    dealing = Dealing.objects.create(lease=lease, kind=Dealing.Kind.UNDERLEASE, to_party=assignee,
                                     premises="First floor", term_start=date(2026, 1, 1), term_end=date(2030, 12, 31),
                                     annual_rent=Decimal("4000"))
    dealings.complete(dealing, completed_on=date(2026, 1, 1))
    lease.refresh_from_db()
    assert lease.counterparty.name == "Old Tenant Ltd" and dealing.status == Dealing.Status.COMPLETED


def test_viewers_cannot_complete(lease, assignee, make_user, client):
    dealing = Dealing.objects.create(lease=lease, kind=Dealing.Kind.ASSIGNMENT, to_party=assignee)
    client.force_login(make_user("vic", "Viewers"))
    assert client.post(f"/leases/dealings/{dealing.pk}/complete/", {"completed_on": "2026-04-01"}).status_code == 403


def test_headlease_and_underleases_show_on_both_agreements(lease, surveyor, client):
    council = Party.objects.create(name="Head Landlord plc", party_type="company")
    head = Lease.objects.create(reference="H1", direction="in", agreement_type="lease", counterparty=council,
                                term_start=date(2010, 1, 1), annual_rent=Decimal("5000"))
    lease.headlease = head
    lease.save()
    client.force_login(surveyor)
    assert "Headlease" in client.get(lease.get_absolute_url()).content.decode()
    assert "Underleases" in client.get(head.get_absolute_url()).content.decode()
