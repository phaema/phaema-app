# SPDX-License-Identifier: AGPL-3.0-or-later
"""Projects: starting them, who can see and change them, gateways, milestones, files and where they appear."""
from datetime import date, timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from apps.projects import workflow
from apps.projects.models import Milestone, Phase, Project, ProjectMember, ProjectProperty, ProjectType
from apps.properties.models import Property

PDF = b"%PDF-1.4 test document"


def _client(user):
    client = Client(HTTP_HOST="localhost")
    client.force_login(user)
    return client


def _project(lead, kind="development", **extra):
    project = Project(name="Northgate regeneration", project_type=ProjectType.objects.get(code=kind), lead=lead,
                      **extra)
    return workflow.start(project, lead)


@pytest.fixture
def people(make_user):
    return {"lead": make_user("p.lead", "Surveyors", first_name="Pat"),
            "other": make_user("p.other", "Surveyors"),
            "legal": make_user("p.legal", "Contributors"),
            "viewer": make_user("p.viewer", "Viewers"),
            "admin": make_user("p.admin", "Administrators")}


@pytest.mark.django_db
def test_standard_types():
    assert set(ProjectType.objects.values_list("code", flat=True)) >= {
        "development", "acquisition", "disposal", "programme", "review"}
    assert ProjectType.objects.get(code="acquisition").confidential_by_default


def test_start_a_project(people):
    client = _client(people["lead"])
    acquisition = ProjectType.objects.get(code="acquisition")
    response = client.post("/projects/new/", {
        "name": "Depot site", "project_type": acquisition.pk, "lead": people["lead"].pk,
        "start_date": date.today().isoformat(), "confidential": "False", "site_address": "Land at Mill Lane",
        "site_title_number": "ZZ999001"})
    assert response.status_code == 302
    project = Project.objects.get(name="Depot site")
    assert project.display_reference == f"PRJ-{date.today().year}-001"
    assert project.confidential  # acquisitions always start confidential
    assert project.phase == Phase.IDEA and project.tasks.count() >= 8
    assert _client(people["viewer"]).get("/projects/new/").status_code == 403


def test_confidential_projects_are_hidden(people):
    project = _project(people["lead"], kind="acquisition", confidential=True)
    other = _client(people["other"])
    assert other.get(project.get_absolute_url()).status_code == 404
    assert project.display_reference not in other.get("/projects/").content.decode()
    ProjectMember.objects.create(project=project, user=people["other"])
    assert other.get(project.get_absolute_url()).status_code == 200
    assert _client(people["admin"]).get(project.get_absolute_url()).status_code == 200


def test_who_can_change_what(people):
    project = _project(people["lead"])
    ProjectMember.objects.create(project=project, user=people["legal"], role=ProjectMember.Role.LEGAL)
    url = project.get_absolute_url()
    legal = _client(people["legal"])
    legal.post(url, {"action": "add_note", "text": "Title checked"})
    assert project.notes.filter(text="Title checked").exists()
    assert legal.post(url, {"action": "add_milestone", "name": "Planning"}).status_code == 403
    other = _client(people["other"])
    assert other.get(url).status_code == 200
    assert other.post(url, {"action": "add_note", "text": "x"}).status_code == 403
    viewer_page = _client(people["viewer"]).get(url).content.decode()
    assert "Record gateway" not in viewer_page and "Add a note" not in viewer_page


def test_gateways_move_the_project_through_its_phases(people):
    project = _project(people["lead"])
    client = _client(people["lead"])
    url, today = project.get_absolute_url(), date.today().isoformat()
    wrong = client.post(url, {"action": "record_gateway", "number": "2", "decision_maker": "officer",
                              "decided_on": today, "outcome": "approved"}, follow=True)
    assert "The next decision for this project is gateway 1" in wrong.content.decode()
    client.post(url, {"action": "record_gateway", "number": "1", "decision_maker": "officer", "decided_on": today,
                      "outcome": "approved"})
    project.refresh_from_db()
    assert project.phase == Phase.BUSINESS_CASE
    client.post(url, {"action": "record_gateway", "number": "2", "decision_maker": "cabinet", "decided_on": today,
                      "outcome": "deferred", "reference": "CAB/2026/14",
                      "report": SimpleUploadedFile("report.pdf", PDF, content_type="application/pdf")})
    project.refresh_from_db()
    assert project.phase == Phase.BUSINESS_CASE and project.is_open
    decision = project.gateway_decisions.get(number=2)
    assert decision.reference == "CAB/2026/14" and decision.report
    for number in (2, 3, 4):
        workflow.record_gateway(project, number, decision_maker="officer", decided_on=date.today(), outcome="approved")
    project.refresh_from_db()
    assert project.status == Project.Status.CLOSED and project.phase == Phase.CLOSE


def test_rejected_gateway_stops_the_project(people):
    project = _project(people["lead"])
    workflow.record_gateway(project, 1, decision_maker="officer", decided_on=date.today(), outcome="rejected",
                            notes="Not affordable")
    project.refresh_from_db()
    assert project.status == Project.Status.STOPPED and project.status_reason == "Not affordable"
    with pytest.raises(ValueError):
        workflow.record_gateway(project, 2, decision_maker="officer", decided_on=date.today(), outcome="approved")


def test_milestones_set_the_status(people):
    project = _project(people["lead"])
    assert project.rag()[0] == "yellow" or project.rag()[0] == "green"
    project.tasks.update(due_date=None)
    assert project.rag()[0] == "green"
    m = Milestone.objects.create(project=project, name="Planning", target_date=date.today() + timedelta(days=30),
                                 forecast_date=date.today() + timedelta(days=60))
    assert project.rag()[0] == "yellow"
    m.target_date = date.today() - timedelta(days=1)
    m.save()
    assert project.rag() == ("red", "Milestone missed")


def test_properties_and_where_projects_appear(people):
    estate = Property.objects.create(reference="PX-E1", name="Test estate", property_type="estate")
    unit = Property.objects.create(reference="PX-U1", name="Unit 1", property_type="unit", parent=estate)
    project = _project(people["lead"])
    client = _client(people["lead"])
    client.post(project.get_absolute_url(), {"action": "add_property", "property": estate.pk, "part": "develop"})
    assert ProjectProperty.objects.filter(project=project, property=estate, part="develop").exists()
    assert project.display_reference in client.get(unit.get_absolute_url()).content.decode()
    mine = client.get("/?view=mine").content.decode()
    assert "My projects" in mine and project.display_reference in mine
    listing = client.get("/projects/", {"building": estate.pk}).content.decode()
    assert project.display_reference in listing


def test_project_files_stay_with_the_project(people):
    project = _project(people["lead"], confidential=True)
    client = _client(people["lead"])
    client.post(project.get_absolute_url(), {"action": "add_document", "title": "Heads of terms",
                                             "file": SimpleUploadedFile("hot.pdf", PDF, content_type="application/pdf")})
    doc = project.documents.get()
    assert client.get(f"/projects/{project.pk}/files/document/{doc.pk}/").status_code == 200
    assert client.get(f"/files/{doc.file.name}").status_code == 404
    assert _client(people["other"]).get(f"/projects/{project.pk}/files/document/{doc.pk}/").status_code == 404


# ------------------------------------------------------------------ part 2: budget, risks, linked work, reports

def _areas(user, *codes):
    from apps.core.models import AccessArea

    user.access_areas.set(AccessArea.objects.filter(code__in=codes))
    from django.contrib.auth.models import User

    return User.objects.get(pk=user.pk)


def test_budget_by_financial_year(people, make_user):
    project = _project(people["lead"], start_date=date(2026, 5, 1), target_date=date(2028, 3, 31))
    client = _client(people["lead"])
    url = project.get_absolute_url()
    client.post(url, {"action": "add_budget_line", "category": "works", "description": "Construction works",
                      "funding": "capital"})
    client.post(url, {"action": "add_budget_line", "category": "income", "description": "Sale of plot 3",
                      "funding": "capital"})
    works, income = project.budget_lines.order_by("pk")
    client.post(url, {"action": "set_budget", "line": works.pk, "year": "2026", "approved": "400,000",
                      "forecast": "450000", "actual": "120000"})
    client.post(url, {"action": "set_budget", "line": works.pk, "year": "2027", "approved": "600000",
                      "forecast": "600000"})
    client.post(url, {"action": "set_budget", "line": income.pk, "year": "2027", "forecast": "250000"})
    from apps.projects import budget

    data = budget.summary(project)
    assert data["cost"].approved == 1000000 and data["cost"].forecast == 1050000 and data["cost"].actual == 120000
    assert data["income"].forecast == 250000
    assert [label for label, _t in data["years"]] == ["2026/27", "2027/28"]
    page = client.get(url).content.decode()
    assert "£50,000 over budget" in page and "2026/27" in page
    bad = client.post(url, {"action": "set_budget", "line": works.pk, "year": "2026", "approved": "lots"}, follow=True)
    assert "Enter amounts in pounds" in bad.content.decode()

    # Who sees and edits the budget
    estates_only = _areas(make_user("budget.estates", "Surveyors"), "estates")
    assert "Construction works" not in _client(estates_only).get(url).content.decode()
    officer = _areas(make_user("budget.finance", "Surveyors"), "finance")
    page = _client(officer).get(url).content.decode()
    assert "Construction works" in page and "Enter figures for a year" in page
    _client(officer).post(url, {"action": "set_budget", "line": works.pk, "year": "2026", "approved": "400000",
                                "forecast": "450000", "actual": "130000"})
    assert works.years.get(year=2026).actual == 130000


def test_risks(people):
    project = _project(people["lead"])
    client = _client(people["lead"])
    client.post(project.get_absolute_url(), {"action": "add_risk", "description": "Planning refused",
                                             "likelihood": "4", "impact": "5", "owner": people["lead"].pk})
    risk = project.risks.get()
    assert risk.score == 20 and risk.level[0] == "red"
    assert "High" in client.get(project.get_absolute_url()).content.decode()
    client.post(project.get_absolute_url(), {"action": "update_risk", "risk": risk.pk})
    risk.refresh_from_db()
    assert risk.status == "closed"


def test_linking_cases_and_who_sees_the_link(people):
    from apps.cases.models import Case, CaseType

    case = Case.objects.create(case_type=CaseType.objects.first(), title="Wayleave for new substation",
                               owner=people["lead"])
    project = _project(people["lead"], confidential=True)
    client = _client(people["lead"])
    client.post(project.get_absolute_url(), {"action": "link", "kind": "case", "reference": case.display_reference})
    case.refresh_from_db()
    assert case.project == project
    assert project.display_reference in client.get(case.get_absolute_url()).content.decode()
    assert project.display_reference not in _client(people["other"]).get(case.get_absolute_url()).content.decode()
    client.post(project.get_absolute_url(), {"action": "unlink", "kind": "case", "id": case.pk})
    case.refresh_from_db()
    assert case.project is None


def test_confidential_access_is_logged(people):
    project = _project(people["lead"], confidential=True)
    ProjectMember.objects.create(project=project, user=people["other"])
    _client(people["other"]).get(project.get_absolute_url())
    assert project.access_log.filter(user=people["other"]).exists()
    page = _client(people["lead"]).get(project.get_absolute_url()).content.decode()
    assert "Who has opened it" in page
    assert "Who has opened it" not in _client(people["other"]).get(project.get_absolute_url()).content.decode()


def test_spending_import(people):
    from apps.projects.importing import SpendWorkbook

    project = _project(people["lead"])
    line = project.budget_lines.create(category="works", description="Construction works")
    csv = (f"Project,Budget line,Financial year,Actual\n{project.display_reference},Construction works,2026/27,"
           f"98765.43\n{project.display_reference},Nonsense,2026/27,1\n").encode()
    result, _prepared = SpendWorkbook().validate(SimpleUploadedFile("spend.csv", csv))
    assert not result.ok and "has no line called 'Nonsense'" in " ".join(e for r in result.rows for e in r.errors)
    csv = f"Project,Budget line,Financial year,Actual\n{project.display_reference},Construction works,2026/27,98765.43\n"
    workbook = SpendWorkbook()
    result, prepared = workbook.validate(SimpleUploadedFile("spend.csv", csv.encode()))
    assert result.ok
    workbook.apply(prepared)
    from decimal import Decimal

    assert line.years.get(year=2026).actual == Decimal("98765.43")


def test_project_reports_follow_visibility(people):
    from apps.reports.models import Report
    from apps.reports.views import _queryset

    open_project = _project(people["lead"])
    secret = _project(people["lead"], kind="acquisition", confidential=True)
    report = Report(dataset="projects", columns=["reference"], owner=people["other"])
    _ds, rows = _queryset(report, people["other"])
    assert open_project in rows and secret not in rows
    listing = _client(people["other"]).get("/projects/?format=csv").content.decode()
    assert open_project.display_reference in listing and secret.display_reference not in listing
