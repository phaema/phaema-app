# SPDX-License-Identifier: AGPL-3.0-or-later
"""The annual asset management health check."""
from datetime import date

import pytest
from django.urls import reverse

from apps.core.roles import ADMINISTRATORS, SURVEYORS, VIEWERS
from apps.projects.models import financial_year_of

from . import health
from .models import EstateStrategy, HealthAnswer, HealthCheck, HealthNote, HealthQuestion, Objective

PASSWORD = "a-long-test-password"
YEAR = financial_year_of(date.today())


@pytest.fixture
def people(db, make_user):
    return {"boss": make_user("boss", ADMINISTRATORS), "head": make_user("head", SURVEYORS),
            "sue": make_user("sue", SURVEYORS), "val": make_user("val", VIEWERS)}


def _login(client, user):
    client.login(username=user.username, password=PASSWORD)


def test_starting_questions_loaded(db):
    assert HealthQuestion.objects.count() == len(health.STARTING_QUESTIONS) >= 25
    headings = set(HealthQuestion.objects.values_list("heading", flat=True))
    assert headings == set(HealthQuestion.Heading.values)


def test_admin_starts_the_year_and_lead_answers(client, people):
    _login(client, people["sue"])
    assert client.post(reverse("strategy:health-list"), {"lead": people["head"].pk}).status_code == 403
    _login(client, people["boss"])
    client.post(reverse("strategy:health-list"), {"lead": people["head"].pk})
    check = HealthCheck.objects.get(year=YEAR)
    assert check.lead == people["head"] and check.answers.count() == HealthQuestion.objects.count()
    first = check.answers.filter(heading="strategy").first()
    # someone who is not the lead cannot answer
    _login(client, people["sue"])
    url = check.get_absolute_url()
    assert client.post(url, {"action": "save", "heading": "strategy", f"answer-{first.pk}": "yes"}).status_code == 403
    _login(client, people["head"])
    client.post(url, {"action": "save", "heading": "strategy", f"answer-{first.pk}": "partly",
                      f"notes-{first.pk}": "Half done", f"evidence-{first.pk}": "https://example.org/strategy"})
    first.refresh_from_db()
    assert first.answer == "partly" and first.answered_by == people["head"] and first.notes == "Half done"
    assert first.evidence_lines() == ["https://example.org/strategy"]
    assert client.get(url).status_code == 200


def test_colleagues_add_notes_and_viewers_can_read(client, people):
    check = health.start(people["head"], YEAR)
    a = check.answers.first()
    _login(client, people["sue"])
    client.post(check.get_absolute_url(), {"action": "note", "answer": a.pk, "text": "We have the minutes."})
    client.post(check.get_absolute_url(), {"action": "note", "text": "Overall looks fair."})
    assert HealthNote.objects.filter(answer=a).count() == 1 and HealthNote.objects.filter(answer=None).count() == 1
    _login(client, people["val"])
    page = client.get(check.get_absolute_url())
    assert page.status_code == 200 and b"We have the minutes." in page.content


def test_gap_becomes_an_action(client, people):
    strategy = EstateStrategy.objects.create(title="AMS", starts_on=date(2026, 4, 1), ends_on=date(2031, 3, 31),
                                             status="adopted")
    objective = Objective.objects.create(strategy=strategy, number="1", title="Better data")
    check = health.start(people["head"], YEAR)
    a = check.answers.filter(heading="data").first()
    a.answer = "no"
    a.save()
    _login(client, people["head"])
    client.post(check.get_absolute_url(), {"action": "add_action", "answer": a.pk, "objective": objective.pk,
                                           "title": "Fill the gaps in the register"})
    a.refresh_from_db()
    assert a.action.objective == objective and a.action.title == "Fill the gaps in the register"
    assert a.action.owner == people["head"]


def test_comparison_with_last_year_and_wording_kept(people):
    last = health.start(people["head"], YEAR - 1)
    q = HealthQuestion.objects.order_by("order").first()
    last.answers.filter(question=q).update(answer="no")
    last.answers.exclude(question=q).update(answer="yes")
    last.status = "finished"
    last.save()
    q.text = "A reworded question"
    q.save()
    now = health.start(people["head"], YEAR)
    now.answers.filter(question=q).update(answer="partly")
    now.answers.exclude(question=q).update(answer="no")
    rows = [r for _label, group in health.sections(now) for r in group]
    mine = next(r for r in rows if r[0].question_id == q.pk)
    assert mine[0].wording == "A reworded question" and mine[1].wording != "A reworded question"
    assert mine[2] == "better"
    assert sum(1 for r in rows if r[2] == "worse") == len(rows) - 1
    text = health.build_report(now)
    assert "1 better" in text and "Gaps and improvement actions" in text and "RICS" in text


def test_finish_reopen_and_report(client, people):
    check = health.start(people["head"], YEAR)
    _login(client, people["head"])
    client.post(check.get_absolute_url(), {"action": "finish", "summary": "Good progress."})
    check.refresh_from_db()
    assert check.status == "finished" and check.finished_on and check.summary == "Good progress."
    # finished: the lead can no longer change answers; only an administrator can reopen
    a = check.answers.first()
    assert client.post(check.get_absolute_url(), {"action": "save", "heading": a.heading,
                                                   f"answer-{a.pk}": "yes"}).status_code == 403
    assert client.post(check.get_absolute_url(), {"action": "reopen"}).status_code == 403
    _login(client, people["boss"])
    client.post(check.get_absolute_url(), {"action": "reopen"})
    check.refresh_from_db()
    assert check.status == "draft"
    report = client.get(reverse("strategy:health-report", args=[check.pk]))
    assert report.status_code == 200 and b"Good progress." in report.content
    word = client.get(reverse("strategy:health-report", args=[check.pk]) + "?format=docx")
    assert word["Content-Type"].startswith("application/vnd.openxmlformats-officedocument.wordprocessingml")


def test_my_work_reminds_the_lead(client, people):
    from apps.core import mywork

    health.start(people["head"], YEAR)
    items = mywork.build(people["head"])["now"]
    assert any(str(i.kind) == "Health check" and "questions still to answer" in str(i.note) for i in items)


def test_question_list_changes_apply_to_new_checks_only(people):
    old = health.start(people["head"], YEAR - 1)
    n = old.answers.count()
    HealthQuestion.objects.filter(pk=HealthQuestion.objects.first().pk).update(active=False)
    new = health.start(people["head"], YEAR)
    assert old.answers.count() == n and new.answers.count() == n - 1
    assert HealthAnswer.objects.filter(health_check=old).count() == n


def test_demo_health_checks(db):
    from django.core.management import call_command

    call_command("load_demo_data", verbosity=0)
    assert HealthCheck.objects.filter(year=YEAR - 1, status="finished").exists()
    now = HealthCheck.objects.get(year=YEAR)
    assert now.status == "draft" and now.answers.exclude(answer="").count() == 15
    assert now.answers.exclude(action=None).exists()
    # the demonstration site visit, finished, with differences still to decide (it shares this slow test)
    from apps.cases import visit
    from apps.cases.models import SiteVisit

    sv = SiteVisit.objects.get(case__property__reference="DM-E01-U04")
    assert sv.is_finished and visit.open_differences(sv)
