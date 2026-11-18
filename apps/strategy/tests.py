# SPDX-License-Identifier: AGPL-3.0-or-later
"""Estates strategy, step 2: the strategy, objectives, action plan, suggested status and board report."""
from datetime import date, timedelta

import pytest
from django.urls import reverse

from apps.cases import workflow
from apps.cases.models import CaseType
from apps.core.roles import ADMINISTRATORS, SURVEYORS, VIEWERS
from apps.projects.models import Milestone, Project, ProjectType
from apps.properties.models import Property

from . import progress, report
from .models import Action, EstateStrategy, Objective

PASSWORD = "a-long-test-password"
TODAY = date.today()


@pytest.fixture
def plan(db, make_user):
    boss = make_user("boss", ADMINISTRATORS)
    sue = make_user("sue", SURVEYORS)
    strategy = EstateStrategy.objects.create(title="Asset Management Strategy", starts_on=date(2026, 4, 1),
                                             ends_on=date(2031, 3, 31), status="adopted", approved_by="Cabinet")
    obj = Objective.objects.create(strategy=strategy, number="1", title="Rationalise the estate", owner=sue,
                                   target_date=TODAY + timedelta(days=900), corporate_aim="Efficient council")
    return {"boss": boss, "sue": sue, "strategy": strategy, "objective": obj}


def _login(client, user):
    client.login(username=user.username, password=PASSWORD)


def test_adopting_a_strategy_replaces_the_last(plan):
    newer = EstateStrategy.objects.create(title="Next", starts_on=date(2031, 4, 1), ends_on=date(2036, 3, 31),
                                          status="adopted")
    plan["strategy"].refresh_from_db()
    assert plan["strategy"].status == "replaced" and EstateStrategy.current() == newer


def test_suggested_status_follows_the_actions(plan, make_user):
    obj = plan["objective"]
    assert progress.objective_state(obj).suggested == ""
    a = Action.objects.create(objective=obj, title="Survey", target_date=TODAY + timedelta(days=200))
    assert progress.objective_state(obj).suggested == "green"
    a.target_date = TODAY + timedelta(days=10)
    a.save()
    assert progress.objective_state(obj).suggested == "amber"
    a.target_date = TODAY - timedelta(days=1)
    a.save()
    state = progress.objective_state(obj)
    assert state.suggested == "red" and state.late and state.exceptions
    a.status = "done"
    a.save()
    assert a.done_on == TODAY and progress.objective_state(obj).suggested == "done"
    obj.target_date = TODAY - timedelta(days=1)
    obj.save()
    Action.objects.create(objective=obj, title="Another", target_date=TODAY + timedelta(days=300))
    assert progress.objective_state(obj).suggested == "red"


def test_linked_project_and_case(plan):
    obj = plan["objective"]
    project = Project.objects.create(name="Depot move", project_type=ProjectType.objects.get(code="development"),
                                     lead=plan["sue"])
    Milestone.objects.create(project=project, name="Planning", target_date=TODAY - timedelta(days=3))
    Action.objects.create(objective=obj, project=project)
    prop = Property.objects.create(reference="D-1", name="Depot", property_type="building")
    case = workflow.open_case(CaseType.objects.get(code="asset_challenge"), title="Challenge", property=prop)
    Action.objects.create(objective=obj, case=case)
    state = progress.objective_state(obj)
    linked = next(s for s in state.actions if s.action.project_id)
    assert linked.rag == "red" and "Milestone missed" in linked.flags
    assert state.suggested == "red"
    case.status = "closed"
    case.save()
    assert progress.objective_state(obj).actions[-1].rag in ("done", "red")


def test_owner_updates_status_and_actions(client, plan, make_user):
    obj = plan["objective"]
    _login(client, plan["sue"])
    url = obj.get_absolute_url()
    client.post(url, {"action": "add", "title": "Agree sharing with the NHS", "owner": plan["sue"].pk,
                      "target_date": (TODAY + timedelta(days=60)).isoformat()})
    item = obj.actions.get()
    assert item.owner == plan["sue"]
    client.post(url, {"action": "action_status", "item": item.pk, "status": "done"})
    item.refresh_from_db()
    assert item.status == "done"
    client.post(url, {"action": "status", "reported_status": "amber", "progress_note": "Talks started"})
    obj.refresh_from_db()
    assert obj.reported_status == "amber" and obj.status_by == plan["sue"] and obj.status_on == TODAY
    page = client.get(url).content.decode()
    assert "Talks started" in page and "differs" in page  # all done, so PHAEMA suggests achieved


def test_link_by_reference_and_bad_reference(client, plan):
    obj = plan["objective"]
    project = Project.objects.create(name="Depot move", project_type=ProjectType.objects.get(code="development"),
                                     lead=plan["sue"])
    _login(client, plan["sue"])
    client.post(obj.get_absolute_url(), {"action": "add", "link": project.display_reference})
    assert obj.actions.get().project == project
    client.post(obj.get_absolute_url(), {"action": "add", "link": "PRJ-1999-999"})
    assert obj.actions.count() == 1


def test_confidential_project_is_hidden(plan, make_user):
    project = Project.objects.create(name="Secret site", project_type=ProjectType.objects.get(code="acquisition"),
                                     lead=plan["boss"], confidential=True)
    Action.objects.create(objective=plan["objective"], project=project)
    viewer = make_user("val", VIEWERS)
    state = progress.objective_state(plan["objective"], viewer)
    assert state.actions[0].hidden and "Secret" not in state.actions[0].label
    assert "Secret site" not in report.build(plan["strategy"], user=viewer)


def test_others_cannot_change(client, plan, make_user):
    obj = plan["objective"]
    _login(client, make_user("tom", SURVEYORS))
    assert client.post(obj.get_absolute_url(), {"action": "status", "reported_status": "red"}).status_code == 403
    _login(client, make_user("val", VIEWERS))
    assert client.get(obj.get_absolute_url()).status_code == 200
    assert client.post(obj.get_absolute_url(), {"action": "add", "title": "x"}).status_code == 403


def test_pages_board_report_and_word(client, plan):
    Action.objects.create(objective=plan["objective"], title="Late one", target_date=TODAY - timedelta(days=5))
    _login(client, plan["boss"])
    page = client.get(reverse("strategy:home")).content.decode()
    assert "Rationalise the estate" in page and "Off track" in page
    text = report.build(plan["strategy"], user=plan["boss"])
    assert "# 3. Exceptions" in text and "Late one" in text and "Efficient council" in text
    word = client.get(reverse("strategy:report") + "?format=docx")
    assert word.status_code == 200 and word["Content-Type"].startswith("application/vnd.openxml")


def test_my_work_shows_actions_and_objectives_to_report(client, plan):
    Action.objects.create(objective=plan["objective"], title="Draft the brief", owner=plan["sue"],
                          target_date=TODAY - timedelta(days=2))
    _login(client, plan["sue"])
    mine = client.get("/?view=mine").content.decode()
    assert "Draft the brief" in mine and "Report progress" in mine


def test_demo_strategy(db):
    from django.core.management import call_command

    call_command("load_demo_data", verbosity=0)
    strategy = EstateStrategy.current()
    assert strategy and strategy.objectives.count() == 4 and Action.objects.filter(case__isnull=False).exists()
    call_command("load_demo_data", "--reset", verbosity=0)
    assert EstateStrategy.objects.count() == 1
