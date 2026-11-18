# SPDX-License-Identifier: AGPL-3.0-or-later
"""Estates strategy, step 1: holding purpose sub-categories, asset strategies, the Asset Challenge, suitability."""
from datetime import date, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.cases import workflow
from apps.cases.models import Case, CaseType
from apps.core.models import ModuleSettings
from apps.core.roles import SURVEYORS, VIEWERS
from apps.properties import importer, strategy
from apps.properties.models import (AssetStrategy, AssetStrategyOption, Property, PurposeCategory,
                                    SuitabilityAssessment)

PASSWORD = "a-long-test-password"
TODAY = date.today()


@pytest.fixture
def estate(db, make_user):
    sue = make_user("sue", SURVEYORS)
    park = Property.objects.create(reference="E-1", name="Business park", property_type="estate",
                                   holding_purpose="investment", managing_surveyor=sue)
    block = Property.objects.create(reference="E-1-B", name="Block A", property_type="building", parent=park,
                                    holding_purpose="investment")
    depot = Property.objects.create(reference="D-1", name="Depot", property_type="building",
                                    holding_purpose="operational", managing_surveyor=sue)
    return {"sue": sue, "park": park, "block": block, "depot": depot,
            "options": {o.name: o for o in AssetStrategyOption.objects.all()}}


def _login(client, user):
    client.login(username=user.username, password=PASSWORD)


def test_starting_lists(db):
    names = list(AssetStrategyOption.objects.values_list("name", flat=True))
    assert names[0] == "Retain as is" and "Community asset transfer" in names and len(names) == 7
    assert AssetStrategyOption.objects.get(name="Dispose now").follow_on == "disposal"
    assert PurposeCategory.objects.filter(holding_purpose="operational", name="Depots").exists()
    assert CaseType.objects.get(code="asset_challenge").asset_challenge


def test_sub_category_must_belong_to_the_purpose(estate):
    depot = estate["depot"]
    depot.purpose_category = PurposeCategory.objects.get(holding_purpose="investment", name="Retail")
    with pytest.raises(ValidationError):
        depot.full_clean()
    depot.purpose_category = PurposeCategory.objects.get(holding_purpose="operational", name="Depots")
    depot.full_clean()


def test_recording_a_strategy_sets_the_review_and_parts_follow(estate):
    settings = ModuleSettings.load()
    settings.strategy_review_years = 4
    settings.save()
    decided = TODAY - timedelta(days=10)
    AssetStrategy.objects.create(property=estate["park"], strategy=estate["options"]["Retain as is"],
                                 decided_on=decided, reason="Fully let")
    estate["park"].refresh_from_db()
    assert estate["park"].purpose_review_date == decided.replace(year=decided.year + 4)
    decision, inherited_from = estate["block"].asset_strategy()
    assert decision.strategy.name == "Retain as is" and inherited_from == estate["park"]
    AssetStrategy.objects.create(property=estate["block"], strategy=estate["options"]["Dispose later"],
                                 reason="Poor condition")
    decision, inherited_from = estate["block"].asset_strategy()
    assert decision.strategy.name == "Dispose later" and inherited_from is None
    effective = strategy.effective_strategies()
    assert effective[estate["block"].pk][1] is True and effective[estate["park"].pk][1] is True


def test_an_older_decision_does_not_move_the_review(estate):
    AssetStrategy.objects.create(property=estate["depot"], strategy=estate["options"]["Retain as is"],
                                 reason="Now", decided_on=TODAY)
    review = Property.objects.get(pk=estate["depot"].pk).purpose_review_date
    AssetStrategy.objects.create(property=estate["depot"], strategy=estate["options"]["Dispose now"],
                                 reason="Earlier", decided_on=TODAY - timedelta(days=900))
    assert Property.objects.get(pk=estate["depot"].pk).purpose_review_date == review
    assert estate["depot"].own_strategy().strategy.name == "Retain as is"


def test_surveyor_records_a_strategy_directly(client, estate, make_user):
    _login(client, estate["sue"])
    url = reverse("properties:record-strategy", args=[estate["depot"].pk])
    assert client.get(url).status_code == 200
    page = client.post(url, {"strategy": estate["options"]["Release space"].pk, "decided_on": TODAY.isoformat(),
                             "reason": "Half the yard is unused", "decided_by": "Cabinet",
                             "minute_reference": "CAB/26/1"})
    assert page.status_code == 302
    decision = estate["depot"].own_strategy()
    assert decision.source == "direct" and decision.recorded_by == estate["sue"] and decision.decided_by == "Cabinet"
    assert client.post(url, {"strategy": estate["options"]["Release space"].pk,
                             "decided_on": (TODAY + timedelta(days=3)).isoformat(),
                             "reason": "x"}).status_code == 200  # a future date is refused
    other = make_user("tom", SURVEYORS)
    _login(client, other)
    assert client.get(url).status_code == 403
    _login(client, make_user("val", VIEWERS))
    assert client.get(url).status_code == 403


def test_suitability(client, estate):
    _login(client, estate["sue"])
    url = reverse("properties:record-suitability", args=[estate["depot"].pk])
    client.post(url, {"grade": "B", "assessed_on": (TODAY - timedelta(days=400)).isoformat(), "notes": "Fine"})
    client.post(url, {"grade": "C", "assessed_on": TODAY.isoformat(), "notes": "Yard too small"})
    assert estate["depot"].current_suitability().grade == "C"
    assert estate["depot"].suitability.count() == 2
    assert strategy.latest_grades()[estate["depot"].pk] == "C"
    page = client.get(estate["depot"].get_absolute_url()).content.decode()
    assert "Grade C" in page and 'id="strategy"' in page


def _challenge(estate):
    kind = CaseType.objects.get(code="asset_challenge")
    kind.approval_stages = []
    kind.save()
    case = workflow.open_case(kind, title="Asset Challenge: Depot", property=estate["depot"])
    assert case.tasks.count() == 7 and case.owner == estate["sue"]
    return case


def test_asset_challenge_outcome_goes_on_the_property(client, estate):
    case = _challenge(estate)
    _login(client, estate["sue"])
    option = estate["options"]["Remodel or share"]
    client.post(case.get_absolute_url(), {"action": "save_proposal", "proposed_strategy": option.pk})
    case.refresh_from_db()
    assert case.proposed_strategy == option
    # Reasons are required, and nothing is recorded without them.
    client.post(case.get_absolute_url(), {"action": "decide", "decision": "approved", "reasons": "",
                                          "date": TODAY.isoformat()})
    assert not AssetStrategy.objects.exists()
    client.post(case.get_absolute_url(), {"action": "decide", "decision": "approved", "strategy": option.pk,
                                          "reasons": "Share the yard with highways", "date": TODAY.isoformat(),
                                          "decided_by": "Cabinet", "meeting_on": TODAY.isoformat(),
                                          "minute_reference": "CAB/26/9"})
    decision = estate["depot"].own_strategy()
    assert decision.strategy == option and decision.case == case and decision.source == "challenge"
    assert decision.minute_reference == "CAB/26/9" and decision.reason == "Share the yard with highways"
    case.refresh_from_db()
    assert case.decision == "approved" and case.decided_by == "Cabinet"
    # Correcting the decision replaces it rather than adding a second.
    client.post(case.get_absolute_url(), {"action": "decide", "decision": "approved",
                                          "strategy": estate["options"]["Release space"].pk,
                                          "reasons": "Release the east yard", "date": TODAY.isoformat()})
    assert AssetStrategy.objects.filter(case=case).count() == 1
    assert estate["depot"].own_strategy().strategy.name == "Release space"


def test_refused_challenge_leaves_the_strategy(client, estate):
    AssetStrategy.objects.create(property=estate["depot"], strategy=estate["options"]["Retain as is"],
                                 reason="Needed", decided_on=TODAY - timedelta(days=2000))
    case = _challenge(estate)
    _login(client, estate["sue"])
    client.post(case.get_absolute_url(), {"action": "decide", "decision": "refused", "reasons": "Not now",
                                          "date": TODAY.isoformat()})
    assert estate["depot"].own_strategy().strategy.name == "Retain as is"
    assert not AssetStrategy.objects.filter(case=case).exists()


def test_challenge_needs_approval_by_default(client, estate):
    kind = CaseType.objects.get(code="asset_challenge")
    assert kind.approval_stages == ["decision"]
    case = workflow.open_case(kind, title="Asset Challenge: Depot", property=estate["depot"])
    _login(client, estate["sue"])
    client.post(case.get_absolute_url(), {"action": "decide", "decision": "approved", "reasons": "Go",
                                          "strategy": estate["options"]["Dispose now"].pk,
                                          "date": TODAY.isoformat()})
    assert not AssetStrategy.objects.exists()


def test_review_reaches_my_work_and_the_overview(client, estate):
    AssetStrategy.objects.create(property=estate["depot"], strategy=estate["options"]["Retain as is"],
                                 reason="Old", decided_on=TODAY - timedelta(days=2000))
    _login(client, estate["sue"])
    mine = client.get("/?view=mine").content.decode()
    assert "Strategy review" in mine and "D-1 Depot" in mine
    page = client.get(reverse("properties:estate-strategy"))
    assert page.status_code == 200
    assert page.context["overdue"] == 1 and page.context["without_strategy"] == 2
    listed = client.get(reverse("properties:list") + f"?strategy={estate['options']['Retain as is'].pk}")
    assert [p.reference for p in listed.context["object_list"]] == ["D-1"]
    listed = client.get(reverse("properties:list") + "?purpose_review=overdue")
    assert [p.reference for p in listed.context["object_list"]] == ["D-1"]


def test_dispose_now_offers_a_disposal_project_with_the_property(client, estate):
    AssetStrategy.objects.create(property=estate["depot"], strategy=estate["options"]["Dispose now"],
                                 reason="Surplus")
    _login(client, estate["sue"])
    page = client.get(estate["depot"].get_absolute_url()).content.decode()
    assert "Start a disposal project" in page
    form = client.get(reverse("projects:new") + f"?type=disposal&property={estate['depot'].pk}")
    assert form.context["form"].initial["name"] == "Disposal: Depot"
    data = {k: v for k, v in form.context["form"].initial.items() if v is not None}
    data.update({"project_type": data["project_type"], "lead": estate["sue"].pk, "start_date": TODAY.isoformat(),
                 "confidential": "False", "from_property": estate["depot"].pk})
    assert client.post(reverse("projects:new"), data).status_code == 302
    from apps.projects.models import ProjectProperty

    link = ProjectProperty.objects.get(property=estate["depot"])
    assert link.part == "dispose" and link.project.project_type.code == "disposal"


def test_import_sub_category_strategy_and_suitability(estate):
    csv = ("Reference,Name,Type,Holding purpose,Purpose sub-category,Asset strategy,Asset strategy decided on,"
           "Asset strategy reason,Suitability grade\n"
           "D-1,Depot,Building,Operational,Depots,Release space,01/04/2026,CAB/26/2,c\n"
           "N-9,New site,Land,Investment,Offices,Hold forever,,,\n")
    rows = importer.read_rows(SimpleUploadedFile("s.csv", csv.encode()))
    result, prepared = importer.validate(rows)
    errors = {r.reference: r.errors for r in result.rows}
    assert errors["D-1"] == []
    assert any("Asset strategy" in e for e in errors["N-9"])
    importer.apply([p for p in prepared if p[0].reference == "D-1"])
    depot = Property.objects.get(reference="D-1")
    assert depot.purpose_category.name == "Depots"
    assert depot.own_strategy().strategy.name == "Release space" and depot.own_strategy().source == "imported"
    assert depot.own_strategy().decided_on == date(2026, 4, 1)
    assert depot.current_suitability().grade == "C"
    # The same file again adds nothing.
    rows = importer.read_rows(SimpleUploadedFile("s.csv", csv.encode()))
    _result, prepared = importer.validate(rows)
    importer.apply([p for p in prepared if p[0].reference == "D-1"])
    assert depot.strategies.count() == 1 and depot.suitability.count() == 1


def test_report_and_report_builder(estate):
    from apps.properties import report
    from apps.reports.datasets import _property_fields

    AssetStrategy.objects.create(property=estate["park"], strategy=estate["options"]["Retain and invest"],
                                 reason="Phase 2", decided_by="Board", minute_reference="AMB/1")
    SuitabilityAssessment.objects.create(property=estate["block"], grade="B")
    text = report.build(estate["block"])
    assert "Retain and invest" in text and "follows E-1 Business park" in text and "Grade B" in text
    fields = {f.key: f for f in _property_fields()}
    assert fields["asset_strategy"].value(estate["block"]) == "Retain and invest"
    assert fields["strategy_followed"].value(estate["block"]) == "E-1 Business park"
    assert fields["suitability"].value(estate["block"]) == "B"
