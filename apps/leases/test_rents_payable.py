# SPDX-License-Identifier: AGPL-3.0-or-later
"""Rents payable: agreements where the council is the tenant, and what is due over the next twelve months."""
from datetime import date
from decimal import Decimal

import pytest
from django.test import Client

from apps.leases import payable
from apps.leases.models import Lease, Party, RentScheduleEntry
from apps.properties.models import Property

TODAY = date(2026, 11, 19)


@pytest.fixture
def held(db):
    office = Property.objects.create(reference="H1", name="Leased office", property_type="unit")
    landlord = Party.objects.create(name="Example Estates Ltd", party_type="company")
    tenant = Party.objects.create(name="Shop Ltd", party_type="company")
    quarterly = Lease.objects.create(reference="IN-1", direction="in", agreement_type="lease", counterparty=landlord,
                                     term_start=date(2020, 3, 25), term_end=date(2030, 3, 24),
                                     annual_rent=Decimal("40000"), rent_frequency="quarter_days",
                                     next_review_date=date(2027, 3, 25))
    quarterly.properties.add(office)
    RentScheduleEntry.objects.create(lease=quarterly, effective_from=date(2027, 3, 25), annual_rent=Decimal("48000"))
    monthly = Lease.objects.create(reference="IN-2", direction="in", agreement_type="licence", counterparty=landlord,
                                   term_start=date(2026, 9, 1), annual_rent=Decimal("12000"), rent_frequency="monthly",
                                   rent_free_until=date(2027, 2, 28))
    monthly.properties.add(office)
    Lease.objects.create(reference="OUT-1", agreement_type="lease", counterparty=tenant, term_start=date(2020, 1, 1),
                         annual_rent=Decimal("9999"), rent_frequency="quarter_days")
    return quarterly, monthly


def test_payments_follow_the_schedule_and_rent_free(held):
    data = payable.gather(today=TODAY)
    assert [r.lease.reference for r in data.rows] == ["IN-1", "IN-2"]       # let-out agreements are not here
    q, m = data.rows
    assert q.next_payment == (date(2026, 12, 25), Decimal("10000.00"))
    # December at 40,000 a year; from the review on 25 March 2027 at 48,000
    assert [a for _d, a in q.payments] == [Decimal("10000.00")] + [Decimal("12000.00")] * 3
    assert m.payments[0][0] == date(2027, 3, 1)                               # nothing in the rent-free period
    assert len(m.payments) == 8 and m.year_total == Decimal("8000.00")
    assert data.annual_total == Decimal("52000") and data.year_total == Decimal("54000.00")
    assert data.by_month[1] == Decimal("10000.00")                           # December 2026
    assert sum(r.year_total for r in data.rows) == data.year_total


def test_page_and_download(held, make_user):
    client = Client(HTTP_HOST="localhost")
    client.force_login(make_user("v.vic", "Viewers"))
    page = client.get("/leases/rents-payable/").content.decode()
    assert "Rents payable" in page and "IN-1" in page and "OUT-1" not in page and "Example Estates Ltd" in page
    response = client.get("/leases/rents-payable/?format=xlsx")
    assert response["Content-Type"].startswith("application/vnd.openxmlformats")


def test_finance_menu(held, make_user):
    client = Client(HTTP_HOST="localhost")
    client.force_login(make_user("boss", "Administrators"))
    page = client.get("/").content.decode()
    menu = page[page.index("<summary>Finance</summary>"):]
    menu = menu[:menu.index("</details>")]
    assert "Rents payable" in menu and "Income" not in page[:page.index("</nav>")]
