# SPDX-License-Identifier: AGPL-3.0-or-later
"""Condition surveys: entering a survey and its items, finishing it, raising jobs, the backlog, the programme and
importing survey items."""
import io
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import Workbook

from apps.core.dates import add_months
from apps.core.models import ModuleSettings
from apps.maintenance import surveys, workflow
from apps.maintenance.models import Component, ConditionSurvey, Job, SurveyItem
from apps.properties.models import Property


@pytest.fixture
def setup(db, make_user):
    settings = ModuleSettings.load()
    settings.maintenance_enabled = True
    settings.save()
    surveyor = make_user("surv", "Surveyors", email="surv@example.org")
    building = Property.objects.create(reference="B1", name="Library", property_type="building",
                                       managing_surveyor=surveyor)
    roof = Component.objects.create(property=building, name="Flat roof", category="roof", condition="B",
                                    condition_on=date(2020, 1, 1))
    return {"surveyor": surveyor, "building": building, "roof": roof}


def test_enter_finish_and_raise_a_job(client, setup):
    client.force_login(setup["surveyor"])
    b = setup["building"]
    page = client.get(f"/maintenance/property/{b.pk}/")
    assert "No condition survey recorded" in page.content.decode()
    resp = client.post(f"/maintenance/property/{b.pk}/surveys/new/", {
        "kind": "full", "surveyed_on": "2026-05-12", "surveyor": "A Surveyor MRICS", "overall_grade": "C"})
    survey = ConditionSurvey.objects.get()
    assert resp.status_code == 302 and survey.next_due == date(2031, 5, 12) and survey.status == "draft"
    for data in ({"element": "roof", "description": "Renew covering", "grade": "D", "priority": "1",
                  "estimated_cost": "95000", "capital": "on", "component": setup["roof"].pk},
                 {"element": "internal", "description": "Redecorate", "grade": "B", "priority": "4",
                  "estimated_cost": "3000"}):
        client.post(survey.get_absolute_url(), {"action": "add_item", **data})
    roof_item, paint = SurveyItem.objects.order_by("priority")
    assert roof_item.due_year == 2026 and paint.due_year == 2031  # from the priority
    assert survey.backlog == Decimal("95000")

    client.post(survey.get_absolute_url(), {"action": "finish", "update_components": "1"})
    survey.refresh_from_db()
    b.refresh_from_db()
    setup["roof"].refresh_from_db()
    assert survey.status == "finished" and b.condition_grade == "C" and b.condition_surveyed_on == date(2026, 5, 12)
    assert setup["roof"].condition == "D" and setup["roof"].condition_on == date(2026, 5, 12)

    resp = client.post(f"/maintenance/surveys/items/{roof_item.pk}/", {"action": "job"})
    job = Job.objects.get()
    roof_item.refresh_from_db()
    assert resp.status_code == 302 and roof_item.job == job and job.priority == "urgent"
    assert job.component == setup["roof"] and job.estimate == Decimal("95000") and job.how_reported == "inspection"
    assert roof_item.is_open and roof_item.status_label == "Job raised"
    client.post(f"/maintenance/surveys/items/{roof_item.pk}/", {"action": "job"})
    assert Job.objects.count() == 1  # never twice
    from apps.maintenance.models import Contractor

    job.contractor = Contractor.objects.create(name="Roofs Ltd")
    job.approval_status = "approved"  # over the order approval limit
    job.save()
    workflow.issue_order(job, email_contractor=False)
    workflow.complete(job, date.today(), Decimal("97000"), "Roof renewed.", "INV-1")
    roof_item.refresh_from_db()
    assert not roof_item.is_open and surveys.open_items().count() == 1

    client.post(f"/maintenance/surveys/items/{paint.pk}/", {"action": "not_needed", "note": "Building to close"})
    paint.refresh_from_db()
    assert paint.state == "not_needed" and not surveys.open_items().exists()
    page = client.get(f"/maintenance/property/{b.pk}/").content.decode()
    assert "Condition surveys" in page and "A Surveyor MRICS" in page


def test_a_later_grade_is_not_overwritten(setup):
    b = setup["building"]
    newer = ConditionSurvey.objects.create(property=b, surveyed_on=date(2026, 6, 1), surveyor="X", overall_grade="B")
    surveys.finish(newer)
    older = ConditionSurvey.objects.create(property=b, surveyed_on=date(2024, 6, 1), surveyor="Y", overall_grade="D")
    SurveyItem.objects.create(survey=older, element="roof", description="x", grade="D", priority=1,
                              component=setup["roof"])
    setup["roof"].condition_on = date(2025, 1, 1)
    setup["roof"].save()
    surveys.finish(older)
    b.refresh_from_db()
    setup["roof"].refresh_from_db()
    assert b.condition_grade == "B" and setup["roof"].condition == "B"


def test_backlog_and_programme_pages(client, setup, make_user):
    b = setup["building"]
    other = Property.objects.create(reference="B2", name="Depot", property_type="building")
    old = ConditionSurvey.objects.create(property=b, surveyed_on=add_months(date.today(), -70), surveyor="X",
                                         overall_grade="C")
    for priority, cost in ((1, 1000), (2, 2000), (3, 3000), (4, 4000)):
        SurveyItem.objects.create(survey=old, element="roof", description=f"Item {priority}", grade="C",
                                  priority=priority, estimated_cost=cost)
    surveys.finish(old)
    client.force_login(setup["surveyor"])
    page = client.get("/maintenance/backlog/")
    assert page.context["summary"]["total"] == Decimal("6000") and page.context["count"] == 4
    by_year = dict(page.context["years"])
    assert by_year[date.today().year] == Decimal("10000")  # all overdue, so counted this year
    assert client.get("/maintenance/backlog/?priority=backlog").context["count"] == 3
    xlsx = client.get("/maintenance/backlog/?format=xlsx")
    assert xlsx.status_code == 200 and xlsx["Content-Type"].startswith("application/vnd.openxmlformats")
    rows = {r["property"].reference: r["state"] for r in client.get("/maintenance/surveys/").context["rows"]}
    assert rows["B1"] == "overdue" and rows["B2"] == "never" and other
    assert [r["property"].reference for r in client.get("/maintenance/surveys/?state=never").context["rows"]] == ["B2"]


def test_only_editors_change_surveys(client, setup, make_user):
    survey = ConditionSurvey.objects.create(property=setup["building"], surveyed_on=date.today(), surveyor="X")
    viewer = make_user("view", "Viewers")
    client.force_login(viewer)
    assert client.get(survey.get_absolute_url()).status_code == 200
    resp = client.post(survey.get_absolute_url(), {"action": "add_item", "element": "roof", "description": "x",
                                                   "grade": "C", "priority": "2"})
    assert resp.status_code == 403 and not survey.items.exists()
    assert client.get(f"/maintenance/property/{setup['building'].pk}/surveys/new/").status_code == 403


def test_import_survey_items(client, setup, make_user):
    admin = make_user("adm", "Administrators")
    client.force_login(admin)
    wb = Workbook()
    ws = wb.active
    ws.title = "Survey items"
    ws.append(["Property reference", "Survey date", "Surveyor", "Element", "Location", "Work needed", "Condition",
               "Priority", "Estimated cost", "Component"])
    ws.append(["B1", "12/05/2026", "Survey Co", "Roof", "Main", "Renew covering", "D", 1, 95000, "Flat roof"])
    ws.append(["B1", "12/05/2026", "", "Structure", "", "Repoint gable", "C", 3, "4,500", ""])
    ws.append(["B1", "12/05/2026", "", "Spaceship", "", "Nope", "C", 9, "", "No such thing"])
    out = io.BytesIO()
    wb.save(out)
    preview = client.post("/import/condition_surveys/", {"file": SimpleUploadedFile("s.xlsx", out.getvalue())})
    result = preview.context["result"]
    errors = " ".join(e for r in result.rows for e in r.errors)
    assert not result.ok and "Element" in errors and "Priority" in errors and "No such thing" in errors

    ws.delete_rows(4)
    out = io.BytesIO()
    wb.save(out)
    preview = client.post("/import/condition_surveys/", {"file": SimpleUploadedFile("s.xlsx", out.getvalue())})
    assert preview.context["result"].ok, [r.errors for r in preview.context["result"].rows]
    client.post("/import/condition_surveys/", {"confirm": "1", "token": preview.context["token"]})
    survey = ConditionSurvey.objects.get()
    assert survey.surveyor == "Survey Co" and survey.status == "draft" and survey.items.count() == 2
    assert survey.items.get(element="roof").component == setup["roof"]
    # Importing the same file again updates rather than duplicates.
    preview = client.post("/import/condition_surveys/", {"file": SimpleUploadedFile("s.xlsx", out.getvalue())})
    assert [r.action for r in preview.context["result"].rows] == ["unchanged", "unchanged"]


def test_demo_has_surveys(db):
    from django.core.management import call_command

    call_command("load_demo_data", verbosity=0)
    assert ConditionSurvey.objects.filter(property__reference="DM-N03", status="finished").exists()
    assert ConditionSurvey.objects.filter(status="draft").count() == 3  # one in each district
    assert surveys.open_items().filter(priority__in=SurveyItem.BACKLOG).exists()
    assert Property.objects.get(reference="DM-N03").condition_grade == "C"
    assert ConditionSurvey.objects.get(property__reference="DM-K09").next_due < date.today() + timedelta(days=1)
