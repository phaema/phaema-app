# SPDX-License-Identifier: AGPL-3.0-or-later
"""The property events pipeline report."""
import io
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from openpyxl import load_workbook

from apps.core.roles import ADMINISTRATORS, VIEWERS
from apps.leases.models import BreakOption, Lease, Party
from apps.projects.models import BudgetLine, BudgetYear, Project, ProjectProperty, ProjectType, financial_year_of
from apps.properties.models import AssetStrategy, AssetStrategyOption, Portfolio, Property

from . import pipeline

PASSWORD = "a-long-test-password"
TODAY = date.today()


@pytest.fixture
def estate(db, make_user):
    boss = make_user("boss", ADMINISTRATORS)
    viewer = make_user("val", VIEWERS)
    investment = Portfolio.objects.create(name="Pipeline test portfolio")
    shop = Property.objects.create(reference="S-1", name="Shop", property_type="unit", portfolio=investment)
    office = Property.objects.create(reference="O-1", name="Rented office", property_type="building")
    land = Property.objects.create(reference="L-1", name="Spare land", property_type="land",
                                   disposal_expected_on=TODAY + timedelta(days=200),
                                   disposal_expected_value=Decimal("250000"),
                                   purpose_review_date=TODAY - timedelta(days=5))
    tenant = Party.objects.create(name="Corner Cafe Ltd", party_type="company")
    landlord = Party.objects.create(name="Private Landlord Ltd", party_type="company")
    out = Lease.objects.create(reference="LO-1", agreement_type="lease", counterparty=tenant,
                               term_start=TODAY - timedelta(days=2000), term_end=TODAY + timedelta(days=700),
                               annual_rent=Decimal("12000"), next_review_date=TODAY - timedelta(days=30))
    out.properties.add(shop)
    BreakOption.objects.create(lease=out, break_date=TODAY - timedelta(days=60), exercisable_by="tenant")
    held = Lease.objects.create(reference="LI-1", agreement_type="lease", counterparty=landlord, direction="in",
                                term_start=TODAY - timedelta(days=1000), term_end=TODAY + timedelta(days=9000),
                                annual_rent=Decimal("40000"))
    held.properties.add(office)
    BreakOption.objects.create(lease=held, break_date=TODAY + timedelta(days=400), exercisable_by="tenant")
    return {"boss": boss, "viewer": viewer, "shop": shop, "office": office, "land": land, "out": out,
            "held": held, "investment": investment}


def _events(pipe, section):
    return pipe.events[section]


def test_lease_events_split_by_direction(estate):
    pipe = pipeline.build(estate["boss"])
    landlord = _events(pipe, "landlord")
    assert {e.what for e in landlord} == {"Rent review", "Contractual expiry"}
    review = next(e for e in landlord if e.what == "Rent review")
    assert review.bucket == "overdue" and "not yet settled" in review.note and review.value == Decimal("12000")
    # the lapsed break is left out
    assert not any("Break" in e.what for e in landlord)
    tenant = _events(pipe, "tenant")
    assert any("Break" in e.what for e in tenant) and all(e.value == Decimal("40000") for e in tenant)
    # the expiry 25 years away is beyond the five years
    assert pipe.beyond["tenant"] == 1
    assert all(isinstance(e.bucket, int) for e in tenant)


def test_financial_years_and_summary(estate):
    pipe = pipeline.build(estate["boss"])
    first = financial_year_of(TODAY)
    assert pipe.years == list(range(first, first + 5))
    assert pipe.buckets()[0] == "overdue" and pipe.buckets()[-1] == "nodate"
    rows = {r["key"]: r for r in pipe.summary()}
    assert rows["landlord"]["total"] == 2 and rows["landlord"]["counts"][0] == 1
    assert rows["reviews"]["total"] == 1 and rows["reviews"]["counts"][0] == 1


def test_disposals_from_property_strategy_and_project(estate):
    dispose = AssetStrategyOption.objects.get(name="Dispose now")
    AssetStrategy.objects.create(property=estate["office"], strategy=dispose, decided_on=TODAY, reason="Surplus")
    pipe = pipeline.build(estate["boss"])
    disposals = _events(pipe, "disposals")
    land = next(e for e in disposals if e.place.startswith("L-1"))
    assert land.value == Decimal("250000") and land.day == estate["land"].disposal_expected_on
    undated = next(e for e in disposals if e.place.startswith("O-1"))
    assert undated.bucket == "nodate" and "Dispose now" in undated.what
    # Put the land into a disposal project: it is then counted once, under the project, with its receipts.
    project = Project.objects.create(name="Land sale", project_type=ProjectType.objects.get(code="disposal"),
                                     lead=estate["boss"], target_date=TODAY + timedelta(days=300))
    ProjectProperty.objects.create(project=project, property=estate["land"], part="dispose")
    line = BudgetLine.objects.create(project=project, category="income", description="Receipt")
    BudgetYear.objects.create(line=line, year=financial_year_of(TODAY), forecast=Decimal("260000"))
    disposals = _events(pipeline.build(estate["boss"]), "disposals")
    assert not any(e.what == "Expected disposal" for e in disposals)
    row = next(e for e in disposals if e.record == project.display_reference)
    assert row.value == Decimal("260000") and row.place.startswith("L-1")


def test_confidential_acquisition_hidden_and_budget_withheld(estate):
    kind = ProjectType.objects.get(code="acquisition")
    secret = Project.objects.create(name="Secret site", project_type=kind, lead=estate["boss"], confidential=True,
                                    target_date=TODAY + timedelta(days=90))
    line = BudgetLine.objects.create(project=secret, category="land", description="Price")
    BudgetYear.objects.create(line=line, year=financial_year_of(TODAY), forecast=Decimal("500000"))
    open_one = Project.objects.create(name="Open purchase", project_type=kind, lead=estate["boss"],
                                      confidential=False)
    boss = _events(pipeline.build(estate["boss"]), "acquisitions")
    assert {e.what for e in boss} == {"Project: Secret site", "Project: Open purchase"}
    assert next(e for e in boss if "Secret" in e.what).value == Decimal("500000")
    assert next(e for e in boss if "Open" in e.what).bucket == "nodate"
    seen = _events(pipeline.build(estate["viewer"]), "acquisitions")
    assert [e.what for e in seen] == ["Project: Open purchase"] and seen[0].value is None
    assert open_one.pk


def test_portfolio_filter(estate):
    pipe = pipeline.build(estate["boss"], portfolio=estate["investment"])
    assert pipe.events["landlord"] and not pipe.events["tenant"] and not pipe.events["reviews"]


def test_page_word_and_excel(client, estate):
    client.login(username="val", password=PASSWORD)
    url = reverse("strategy:pipeline")
    page = client.get(url)
    assert page.status_code == 200
    assert b"Council as tenant" in page.content and b"Corner Cafe" in page.content
    word = client.get(url + "?format=docx")
    assert word["Content-Type"].startswith("application/vnd.openxmlformats-officedocument.wordprocessingml")
    excel = client.get(url + "?format=xlsx")
    wb = load_workbook(io.BytesIO(excel.content))
    assert wb.sheetnames == ["Key figures", "Council as landlord", "Council as tenant", "Disposals",
                             "Acquisitions", "Strategy reviews"]
    assert wb["Council as landlord"].max_row == 3
    assert "Property events pipeline" in pipeline.to_markup(pipeline.build(estate["viewer"]))
    client.login(username="boss", password=PASSWORD)
    assert b"Property events pipeline" in client.get(reverse("reports:list")).content


def test_needs_sign_in(client, db):
    assert client.get(reverse("strategy:pipeline")).status_code == 302
