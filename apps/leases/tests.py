# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.urls import reverse

from apps.leases.demo import add_months, quarter_day_on_or_before
from apps.leases.models import BreakOption, Lease, Party
from apps.properties.models import Property


@pytest.fixture
def officer(make_user):
    return make_user("officer", "Administrators")


@pytest.fixture
def demo(db):
    call_command("load_demo_data", verbosity=0)


@pytest.fixture
def lease(db):
    unit = Property.objects.create(reference="U1", name="Unit 1", property_type="unit")
    tenant = Party.objects.create(name="Tenant Ltd", party_type="company")
    obj = Lease.objects.create(reference="L1", agreement_type="lease", counterparty=tenant,
                               term_start=date(2020, 3, 25), term_end=date(2030, 3, 24), annual_rent=Decimal("10000"))
    obj.properties.add(unit)
    return obj


def test_term_description(lease):
    assert lease.term_description == "10 years"
    lease.term_end = date(2021, 9, 28)
    assert lease.term_description == "1 year 6 months"
    lease.term_end = None
    assert "Periodic" in str(lease.term_description)


def test_break_notice_deadline_and_key_dates(lease):
    b = BreakOption.objects.create(lease=lease, break_date=date(2025, 3, 25), exercisable_by="tenant", notice_months=6)
    assert b.notice_deadline == date(2024, 9, 25)
    b2 = BreakOption(lease=lease, break_date=date(2025, 3, 31), exercisable_by="tenant", notice_months=1)
    assert b2.notice_deadline == date(2025, 2, 28)
    kinds = [k for _d, _l, k in lease.key_dates()]
    assert kinds == ["notice", "break", "expiry"]


def test_lease_validation(lease):
    lease.term_end = date(2019, 1, 1)
    with pytest.raises(ValidationError):
        lease.full_clean()
    lease.term_end = date(2030, 3, 24)
    lease.guarantor = lease.counterparty
    with pytest.raises(ValidationError):
        lease.full_clean()
    lease.guarantor = None
    lease.next_review_date = date(2025, 3, 25)
    with pytest.raises(ValidationError):
        lease.full_clean()


def test_demo_helpers():
    assert quarter_day_on_or_before(date(2026, 11, 3)) == date(2026, 9, 29)
    assert quarter_day_on_or_before(date(2026, 1, 10)) == date(2025, 12, 25)
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)


def test_demo_leases_are_valid(demo):
    assert Lease.objects.count() == 22
    for obj in Lease.objects.all():
        obj.full_clean()
        assert obj.properties.exists()
    assert Lease.objects.filter(direction="in").count() == 1
    call_command("load_demo_data", verbosity=0)  # repeatable
    assert Lease.objects.count() == 22 and BreakOption.objects.count() == 2


def test_lease_pages_and_filters(client, officer, demo):
    client.force_login(officer)
    url = reverse("leases:list")
    resp = client.get(url)
    assert resp.status_code == 200 and resp.context["paginator"].count == 22
    assert client.get(url, {"direction": "in"}).context["paginator"].count == 1
    expiring = client.get(url, {"expiring": "12"}).context["page_obj"]
    today = date.today()
    assert all(today <= lease.term_end <= add_months(today, 12) for lease in expiring)
    rents = [lease.annual_rent for lease in client.get(url, {"sort": "-rent"}).context["page_obj"]]
    assert rents == sorted(rents, reverse=True)
    assert client.get(url, {"q": "Logistics"}).context["paginator"].count == 1

    l3 = Lease.objects.get(reference="DL-0003")
    html = client.get(l3.get_absolute_url()).content.decode()
    assert "Break option" in html and "Exampleton Holdings plc" in html and "Last date to serve break notice" in html
    html = client.get(l3.counterparty.get_absolute_url()).content.decode()
    assert "DL-0003" in html
    unit = Property.objects.get(reference="DM-E01-U04")
    assert "Exampleton Logistics Ltd" in client.get(unit.get_absolute_url()).content.decode()


def test_lease_api(client, officer, demo):
    client.force_login(officer)
    data = client.get("/api/leases/?page=1").json()
    assert data["count"] == 22
    l3 = next(r for r in data["results"] if r["reference"] == "DL-0003")
    assert l3["breaks"][0]["notice_deadline"]
