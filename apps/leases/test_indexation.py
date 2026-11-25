# SPDX-License-Identifier: AGPL-3.0-or-later
"""Index-linked rent reviews: the calculation, the index figures and recording the outcome."""
from datetime import date
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.leases import indexation, workflow
from apps.leases.models import IndexFigure, IndexSeries, Lease, LeaseEvent, Party, RentScheduleEntry
from apps.properties.models import Property

D = Decimal


@pytest.fixture
def cpi(db):
    series = IndexSeries.objects.get(code="CPI")  # seeded by the migration
    # Made-up figures for the tests: 100 in March 2021, rising by 0.5 a month.
    month = date(2021, 1, 1)
    for i in range(72):
        IndexFigure.objects.create(series=series, month=month, value=D("99") + D("0.5") * i)
        month = date(month.year + (month.month // 12), month.month % 12 + 1, 1)
    return series


@pytest.fixture
def surveyor(make_user):
    return make_user("sue", "Surveyors", email="sue@example.org")


@pytest.fixture
def lease(cpi, surveyor):
    prop = Property.objects.create(reference="P1", name="Shop", property_type="unit", managing_surveyor=surveyor)
    tenant = Party.objects.create(name="Tenant Ltd", party_type="company")
    obj = Lease.objects.create(
        reference="L1", agreement_type="lease", counterparty=tenant, term_start=date(2021, 6, 24),
        term_end=date(2036, 6, 23), annual_rent=D("10000"), rent_frequency="quarter_days", review_basis="cpi",
        review_interval_years=3, next_review_date=date(2024, 6, 24), index_series=cpi,
        index_base_month=date(2021, 3, 15), index_lag_months=3)
    obj.properties.add(prop)
    workflow.sync_events(obj)
    return obj


def value(month):
    """The test figure for a month: 99 in January 2021, plus 0.5 a month."""
    return D("99") + D("0.5") * ((month.year - 2021) * 12 + month.month - 1)


def test_rent_follows_the_index_from_the_base_month_to_the_lagged_review_month(lease):
    calc = indexation.calculate(lease, date(2024, 6, 24))
    assert calc.ok and calc.base_month == date(2021, 3, 1) and calc.review_month == date(2024, 3, 1)
    assert (calc.base_value, calc.review_value) == (value(date(2021, 3, 1)), value(date(2024, 3, 1)))
    expected = (D("10000") * value(date(2024, 3, 1)) / value(date(2021, 3, 1))).quantize(D("0.01"))
    assert calc.new_rent == calc.indexed_rent == expected and calc.years == 3 and not calc.applied
    assert "CPI Mar 2024" in calc.summary()


def test_cap_compounds_each_year(lease):
    lease.index_cap_pct = D("4")
    lease.save()
    calc = indexation.calculate(lease, date(2024, 6, 24))  # index rose about 18%; the cap allows 4% a year
    assert calc.cap_rent == (D("10000") * D("1.04") ** 3).quantize(D("0.01")) == D("11248.64")
    assert calc.new_rent == calc.cap_rent and calc.applied == ["cap"]
    lease.index_compounded = False
    lease.save()
    assert indexation.calculate(lease, date(2024, 6, 24)).new_rent == D("11200.00")


def test_collar_and_upwards_only(lease, cpi):
    # The index falls: the collar lifts the rent to 1% a year; with no collar, upwards only keeps the rent.
    IndexFigure.objects.filter(series=cpi, month=date(2024, 3, 1)).update(value=D("90"))
    lease.index_collar_pct = D("1")
    lease.save()
    calc = indexation.calculate(lease, date(2024, 6, 24))
    assert calc.new_rent == (D("10000") * D("1.01") ** 3).quantize(D("0.01")) and calc.applied == ["collar"]
    lease.index_collar_pct = None
    lease.save()
    calc = indexation.calculate(lease, date(2024, 6, 24))
    assert calc.new_rent == D("10000") and calc.applied == ["upwards only"]
    lease.index_upward_only = False
    lease.save()
    assert indexation.calculate(lease, date(2024, 6, 24)).new_rent < D("10000")


def test_missing_terms_or_figures_are_explained(lease, cpi):
    IndexFigure.objects.filter(series=cpi, month=date(2024, 3, 1)).delete()
    calc = indexation.calculate(lease, date(2024, 6, 24))
    assert not calc.ok and "March 2024" in calc.problem and "not be published" in calc.problem
    lease.index_base_month = None
    lease.save()
    assert "base index month" in indexation.calculate(lease, date(2024, 6, 24)).problem
    lease.review_basis = "om_up"
    lease.save()
    assert not indexation.calculate(lease, date(2024, 6, 24)).ok


def test_review_page_proposes_the_rent_and_recording_moves_the_base_month(client, lease, surveyor):
    event = lease.events.get(event_type=LeaseEvent.EventType.REVIEW)
    client.force_login(surveyor)
    expected = indexation.calculate(lease, event.due_date).new_rent
    page = client.get(event.get_absolute_url()).content.decode()
    assert "Index-linked rent" in page and f"{expected:,.2f}" in page
    response = client.post(event.get_absolute_url(), {
        "record_outcome": "1", "new_rent": str(expected), "effective_from": "2024-06-24",
        "next_review_date": "2027-06-24", "notes": "Index applied."})
    assert response.status_code == 302
    lease.refresh_from_db()
    assert lease.index_base_month == date(2024, 3, 1) and lease.next_review_date == date(2027, 6, 24)
    entry = lease.rent_schedule.get(effective_from=date(2024, 6, 24))
    assert entry.annual_rent == expected and entry.reason == RentScheduleEntry.Reason.INDEXATION
    # The next review is worked out from the new rent and the new base month.
    nxt = indexation.calculate(lease, date(2027, 6, 24))
    assert nxt.base_month == date(2024, 3, 1) and nxt.current_rent == expected


ONS_CSV = '''"Title","CPI INDEX 00: ALL ITEMS 2015=100"
"CDID","D7BT"
"Source dataset ID","MM23"
"PreUnit",""
"Unit","Index, base year = 100"
"Release date","15-10-2026"
"Next release","19 November 2026"
"Important notes",""
"2025","138.2"
"2025 Q4","139.1"
"2025 DEC","139.6"
"2026 JAN","139.0"
"2026 FEB","139.8"
'''


def test_reads_the_ons_csv_and_plain_files():
    assert indexation.parse_figures(ONS_CSV) == {
        date(2025, 12, 1): D("139.6"), date(2026, 1, 1): D("139.0"), date(2026, 2, 1): D("139.8")}
    plain = "Month,Value\n2026-03,140.1\n04/2026,140.5\nMay 2026,140.9\n2026-06-01,141.2\nnot a month,1\n"
    assert indexation.parse_figures(plain) == {
        date(2026, 3, 1): D("140.1"), date(2026, 4, 1): D("140.5"), date(2026, 5, 1): D("140.9"),
        date(2026, 6, 1): D("141.2")}


def test_upload_adds_and_corrects_figures(client, make_user, db):
    admin = make_user("ann", "Administrators")
    rpi = IndexSeries.objects.get(code="RPI")
    IndexFigure.objects.create(series=rpi, month=date(2025, 12, 1), value=D("1"))
    client.force_login(admin)
    upload = SimpleUploadedFile("rpi.csv", ONS_CSV.encode(), content_type="text/csv")
    response = client.post("/leases/index-figures/", {"series": rpi.pk, "upload": "1", "file": upload}, follow=True)
    assert "2 figures added, 1 corrected" in response.content.decode()
    assert rpi.value_for(date(2025, 12, 15)) == D("139.6")


def test_only_administrators_change_figures(client, surveyor, db):
    client.force_login(surveyor)
    assert client.get("/leases/index-figures/").status_code == 200
    rpi = IndexSeries.objects.get(code="RPI")
    upload = SimpleUploadedFile("rpi.csv", ONS_CSV.encode(), content_type="text/csv")
    assert client.post("/leases/index-figures/", {"series": rpi.pk, "file": upload}).status_code == 403


def test_daily_update_skips_series_that_are_up_to_date(cpi, monkeypatch):
    calls = []
    monkeypatch.setattr(indexation, "fetch_from_ons", lambda series: calls.append(series.code) or (0, 0))
    # CPI's latest test figure is December 2026, so only CPIH and RPI (no figures) are fetched in January 2027.
    indexation.update_all(today=date(2027, 1, 20))
    assert sorted(calls) == ["CPIH", "RPI"]


def test_collar_above_cap_is_refused(lease):
    from django.core.exceptions import ValidationError

    lease.index_cap_pct, lease.index_collar_pct = D("2"), D("3")
    with pytest.raises(ValidationError):
        lease.full_clean()
    assert Lease.objects.filter(pk=lease.pk).exists()
