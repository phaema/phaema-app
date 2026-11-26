# SPDX-License-Identifier: AGPL-3.0-or-later
"""The IFRS 16 data pack for finance: the leases the council holds, every payment and the year's changes."""
import io
from datetime import date
from decimal import Decimal

import pytest
from openpyxl import load_workbook

from apps.leases import ifrs16
from apps.leases.models import Lease, Party, RentScheduleEntry
from apps.properties.models import Property

D = Decimal


@pytest.fixture
def landlord(db):
    return Party.objects.create(name="Landlord plc", party_type="company")


def held(landlord, ref, start, end=None, rent="12000", freq="quarter_days", **extra):
    unit = Property.objects.create(reference=f"P-{ref}", name=f"Depot {ref}", property_type="building",
                                   uprn=f"1000{len(ref)}{ref[-1]}")
    lease = Lease.objects.create(reference=ref, direction="in", agreement_type="lease", counterparty=landlord,
                                 term_start=start, term_end=end, annual_rent=D(rent), rent_frequency=freq, **extra)
    lease.properties.add(unit)
    return lease


def test_years_run_april_to_march():
    assert ifrs16.year_bounds(2026) == (date(2026, 4, 1), date(2027, 3, 31))
    assert ifrs16.current_year(date(2027, 2, 1)) == 2026 and ifrs16.current_year(date(2026, 4, 1)) == 2026
    assert ifrs16.year_label(2026) == "2026/27"


def test_payments_run_from_the_year_start_to_the_lease_end(landlord):
    lease = held(landlord, "H1", date(2024, 3, 25), date(2028, 3, 24))
    RentScheduleEntry.objects.create(lease=lease, effective_from=date(2027, 3, 25), annual_rent=D("14000"),
                                     reason="step")
    pack = ifrs16.gather(2026)
    (row,) = pack.rows
    assert row.payments[0] == (date(2026, 6, 24), D("3000.00"))  # 1 April 2026 onwards
    assert row.payments[-1] == (date(2027, 12, 25), D("3500.00"))  # the step applies; none after 24 March 2028
    in_year = [p for p in row.payments if p[0] <= pack.end]
    assert len(in_year) == 4 and sum(a for _d, a in in_year) == D("12500.00")  # Jun, Sep, Dec at 3,000; Mar at 3,500
    assert row.total_from(date(2027, 4, 1)) == D("10500.00")


def test_ifrs16_lease_end_overrides_the_contract_and_runs_past_it(landlord):
    held(landlord, "H2", date(2020, 1, 1), date(2027, 6, 30), freq="annually",
                 ifrs16_lease_end=date(2030, 12, 31), ifrs16_notes="Renewal reasonably certain")
    (row,) = ifrs16.gather(2026).rows
    assert row.lease_end == date(2030, 12, 31) and "set on the agreement" in row.lease_end_source
    assert [d for d, _a in row.payments] == [date(2027, 1, 1), date(2028, 1, 1), date(2029, 1, 1), date(2030, 1, 1)]


def test_flags_periodic_peppercorn_and_index_linked(landlord):
    held(landlord, "H3", date(2015, 1, 1), None, freq="monthly")
    held(landlord, "H4", date(2010, 1, 1), date(2109, 12, 31), rent="0", freq="peppercorn")
    held(landlord, "H5", date(2025, 1, 1), date(2035, 12, 31), review_basis="cpi")
    rows = {r.lease.reference: r for r in ifrs16.gather(2026).rows}
    assert "No end date" in rows["H3"].problems[0] and rows["H3"].payments == []
    assert rows["H4"].nominal and any("current value" in p for p in rows["H4"].problems)
    assert any("Index-linked" in p for p in rows["H5"].problems)


def test_only_held_leases_in_force_in_the_year(landlord):
    held(landlord, "IN", date(2025, 1, 1), date(2030, 1, 1))
    held(landlord, "OLD", date(2010, 1, 1), date(2020, 1, 1), actual_end=date(2020, 1, 1), status="ended")
    held(landlord, "LATER", date(2028, 1, 1), date(2030, 1, 1))
    tenant = Party.objects.create(name="Tenant", party_type="company")
    Lease.objects.create(reference="OUT", direction="out", agreement_type="lease", counterparty=tenant,
                         term_start=date(2025, 1, 1), annual_rent=D("1000"))
    assert [r.lease.reference for r in ifrs16.gather(2026).rows] == ["IN"]


def test_changes_in_the_year(landlord, make_user, client):
    lease = held(landlord, "H6", date(2026, 5, 1), date(2031, 4, 30))
    RentScheduleEntry.objects.create(lease=lease, effective_from=date(2026, 11, 1), annual_rent=D("13000"),
                                     reason="review", notes="Settled")
    lease.ifrs16_lease_end = date(2033, 4, 30)
    lease.save()
    whats = [c.what for c in ifrs16.changes(*ifrs16.year_bounds(2026), ifrs16.gather(2026).rows)]
    assert "New lease" in whats and "Rent change: Rent review" in whats
    if date.today() >= date(2026, 4, 1) and date.today() <= date(2027, 3, 31):
        assert "IFRS 16 lease term ends changed" in whats


def test_download_for_finance_only(landlord, make_user, client):
    held(landlord, "H7", date(2025, 4, 1), date(2030, 3, 31))
    client.force_login(make_user("vic", "Viewers"))
    assert client.get("/leases/rents-payable/ifrs16.xlsx?year=2026").status_code == 403
    assert "IFRS 16 data pack" not in client.get("/leases/rents-payable/").content.decode()
    client.force_login(make_user("ann", "Administrators"))
    assert "IFRS 16 data pack" in client.get("/leases/rents-payable/").content.decode()
    response = client.get("/leases/rents-payable/ifrs16.xlsx?year=2026")
    assert response.status_code == 200 and "2026-27" in response["Content-Disposition"]
    wb = load_workbook(io.BytesIO(response.content))
    assert wb.sheetnames == ["Leases", "Payments", "Changes in the year", "Notes"]
    leases = wb["Leases"]
    assert leases["A5"].value == "H7" and leases.cell(4, 27).value == "Discount rate (%)"
    assert leases.cell(5, 23).value == 48000.0  # 16 quarters from 1 April 2026 to 31 March 2030, at £3,000
    assert wb["Payments"].max_row == 17
