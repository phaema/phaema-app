# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import date, timedelta
from decimal import Decimal
from email.message import EmailMessage

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.cases import workflow
from apps.cases.models import Case, CaseNote, CaseType, Correspondence
from apps.core.dates import add_working_days
from apps.core.models import ModuleSettings
from apps.leases.models import Lease, LeaseEvent, Party
from apps.properties.models import Property


@pytest.fixture
def setup(db, make_user):
    surveyor = make_user("surv", "Surveyors")
    unit = Property.objects.create(reference="U1", name="Unit 1", property_type="unit", managing_surveyor=surveyor)
    tenant = Party.objects.create(name="Tenant Ltd", party_type="company")
    lease = Lease.objects.create(reference="L1", agreement_type="lease", counterparty=tenant,
                                 term_start=date(2020, 1, 1), term_end=date.today() + timedelta(days=200),
                                 annual_rent=Decimal("10000"), next_review_date=date.today() + timedelta(days=100),
                                 review_basis="om_up", alienation="Not to assign without consent, not to be "
                                                                  "unreasonably withheld.")
    lease.properties.add(unit)
    return {"surveyor": surveyor, "unit": unit, "lease": lease, "tenant": tenant}


def test_case_types_are_seeded(db):
    assert CaseType.objects.count() >= 30
    assignment = CaseType.objects.get(code="assignment")
    assert assignment.statutory_1988 and assignment.target_days == 28 and assignment.fee is None
    assert CaseType.objects.get(code="other_activity").group == "other"
    assert CaseType.objects.get(code="rent_review").open_days_before == 270


def test_opening_a_case_numbers_it_and_fills_in_the_details(setup):
    case = workflow.open_case(CaseType.objects.get(code="assignment"), title="Assign to X", lease=setup["lease"],
                              received_on=date(2026, 11, 2))
    assert case.reference == f"CAS-2026-{case.number:04d}"
    assert case.display_reference == f"{case.reference}/U1"
    assert case.owner == setup["surveyor"] and case.party == setup["tenant"] and case.property == setup["unit"]
    assert case.target_date == date(2026, 11, 30)  # 28 days from receipt until the application is complete
    assert case.acknowledge_due == add_working_days(date(2026, 11, 2), 10)
    assert case.tasks.filter(stage="completing").exists()
    second = workflow.open_case(CaseType.objects.get(code="enquiry"), title="Q", received_on=date(2026, 12, 1))
    assert second.number == case.number + 1


def test_target_moves_when_application_is_complete(setup):
    case = workflow.open_case(CaseType.objects.get(code="assignment"), title="A", lease=setup["lease"],
                              received_on=date(2026, 11, 2))
    case.application_complete_on = date(2026, 11, 20)
    case.refresh_target()
    assert case.target_date == date(2026, 12, 18)


def test_cases_open_automatically_for_lease_events_and_close_with_them(setup):
    opened = workflow.auto_open()
    review = LeaseEvent.objects.get(lease=setup["lease"], event_type="review")
    case = review.cases.get()
    assert opened >= 2 and case.case_type.code == "rent_review" and case.target_date == review.due_date
    assert workflow.auto_open() == 0  # never twice
    from apps.leases.workflow import complete_review

    complete_review(review, setup["surveyor"], Decimal("11000"), review.due_date, None, "Agreed")
    case.refresh_from_db()
    assert case.status == Case.Status.CLOSED and "Agreed" in case.outcome


def test_permissions(client, make_user, setup):
    case = workflow.open_case(CaseType.objects.get(code="assignment"), title="A", lease=setup["lease"])
    viewer, contributor = make_user("view", "Viewers"), make_user("legal", "Contributors")
    other_surveyor = make_user("other", "Surveyors")
    assert workflow.can_work(setup["surveyor"], case) and not workflow.can_work(other_surveyor, case)
    assert not workflow.can_contribute(contributor, case)
    case.contributors.add(contributor)
    assert workflow.can_contribute(contributor, case) and not workflow.can_work(contributor, case)
    client.force_login(contributor)
    assert client.post(case.get_absolute_url(), {"action": "add_note", "text": "Licence drafted"}).status_code == 302
    assert client.post(case.get_absolute_url(), {"action": "next_stage"}).status_code == 403
    client.force_login(viewer)
    assert client.get(case.get_absolute_url()).status_code == 200
    assert client.post(case.get_absolute_url(), {"action": "add_note", "text": "x"}).status_code == 403
    assert client.get("/cases/new/").status_code == 403


def test_confidential_notes(client, make_user, setup):
    case = workflow.open_case(CaseType.objects.get(code="assignment"), title="A", lease=setup["lease"])
    CaseNote.objects.create(case=case, text="Secret price", confidential=True)
    CaseNote.objects.create(case=case, text="Open note")
    client.force_login(make_user("view", "Viewers"))
    page = client.get(case.get_absolute_url()).content.decode()
    assert "Open note" in page and "Secret price" not in page and "1 confidential note is not shown" in page
    client.force_login(setup["surveyor"])  # the owner
    assert "Secret price" in client.get(case.get_absolute_url()).content.decode()


def test_decisions_need_reasons_under_the_1988_act(client, setup):
    case = workflow.open_case(CaseType.objects.get(code="assignment"), title="A", lease=setup["lease"])
    client.force_login(setup["surveyor"])
    client.post(case.get_absolute_url(), {"action": "decide", "decision": "refused", "reasons": ""})
    case.refresh_from_db()
    assert case.decision == ""
    client.post(case.get_absolute_url(), {"action": "decide", "decision": "refused", "reasons": "Weak covenant",
                                          "date": "2026-11-20"})
    case.refresh_from_db()
    assert case.decision == "refused" and case.decision_on == date(2026, 11, 20) and case.stage == "decision"


def test_stages_tasks_hold_and_close(client, setup):
    case = workflow.open_case(CaseType.objects.get(code="enquiry"), title="Q", lease=setup["lease"])
    client.force_login(setup["surveyor"])
    url = case.get_absolute_url()
    client.post(url, {"action": "next_stage"})
    task = case.tasks.first()
    client.post(url, {"action": "task_done", "task": task.pk})
    client.post(url, {"action": "add_task", "description": "Ring the tenant", "stage": "assessing"})
    client.post(url, {"action": "hold", "reason": "Waiting for plans"})
    case.refresh_from_db()
    task.refresh_from_db()
    assert case.stage == "information" and task.done_on and case.status == "on_hold"
    assert case.tasks.filter(description="Ring the tenant", stage="assessing").exists()
    client.post(url, {"action": "resume"})
    client.post(url, {"action": "close", "outcome": "Answered"})
    case.refresh_from_db()
    assert case.status == "closed" and case.outcome == "Answered"


def _eml():
    msg = EmailMessage()
    msg["From"], msg["To"] = "Tenant <t@example.org>", "estates@example.org"
    msg["Subject"], msg["Date"] = "Request to assign", "Mon, 02 Nov 2026 09:30:00 +0000"
    msg.set_content("Please consent to the assignment.")
    msg.add_attachment(b"%PDF-1.4 accounts", maintype="application", subtype="pdf", filename="accounts.pdf")
    msg.add_attachment(b"<script>", maintype="text", subtype="html", filename="page.html")
    return bytes(msg)


def test_filing_an_email(client, setup):
    case = workflow.open_case(CaseType.objects.get(code="assignment"), title="A", lease=setup["lease"])
    client.force_login(setup["surveyor"])
    upload = SimpleUploadedFile("request.eml", _eml(), content_type="message/rfc822")
    client.post(case.get_absolute_url(), {"action": "file_email", "file": upload, "direction": "in"})
    item = Correspondence.objects.get(case=case)
    assert (item.subject, item.on, item.correspondent) == ("Request to assign", date(2026, 11, 2),
                                                           "Tenant <t@example.org>")
    assert "Please consent" in item.summary and item.file
    names = list(item.attachments.values_list("original_filename", flat=True))
    assert names == ["accounts.pdf"]  # the .html attachment is not a permitted file type


def test_documents_are_checked(client, setup):
    case = workflow.open_case(CaseType.objects.get(code="enquiry"), title="Q", lease=setup["lease"])
    client.force_login(setup["surveyor"])
    fake = SimpleUploadedFile("plan.pdf", b"not really a pdf")
    client.post(case.get_absolute_url(), {"action": "add_document", "file": fake, "description": "Plan"})
    assert not case.documents.exists()
    real = SimpleUploadedFile("plan.pdf", b"%PDF-1.4 plan")
    client.post(case.get_absolute_url(), {"action": "add_document", "file": real, "description": "Plan"})
    doc = case.documents.get()
    assert client.get(doc.file.url).status_code == 200


def test_fixed_fee_goes_to_the_rent_account(client, make_user, setup):
    settings = ModuleSettings.load()
    settings.rent_ledger_enabled = True
    settings.save()
    case_type = CaseType.objects.get(code="assignment")
    case_type.fee = Decimal("400")
    case_type.save()
    case = workflow.open_case(case_type, title="A", lease=setup["lease"])
    client.force_login(make_user("admin", "Administrators"))
    client.post(case.get_absolute_url(), {"action": "raise_fee"})
    client.post(case.get_absolute_url(), {"action": "raise_fee"})  # not twice
    case.refresh_from_db()
    assert case.fee_charge.gross == Decimal("400.00") and case.fee_charge.kind == "other"
    assert setup["lease"].charges.count() == 1


def test_lists_pages_and_reports(client, make_user, setup):
    workflow.auto_open()
    client.force_login(make_user("view", "Viewers"))
    for url in ("/cases/", "/cases/?owner=me", "/cases/?when=past&sort=-target", "/cases/?format=xlsx",
                setup["lease"].get_absolute_url(), setup["unit"].get_absolute_url(), "/"):
        assert client.get(url).status_code == 200, url
    number = Case.objects.first().number
    assert client.get("/cases/", {"q": f"CAS-2026-{number:04d}"}).context["paginator"].count >= 1
    from apps.reports.models import Report

    for report in Report.objects.filter(starter__in=["open_cases", "cases_past_target", "consent_decisions",
                                                     "cases_closed_12m"]):
        assert client.get(report.get_absolute_url()).status_code == 200


def test_start_case_from_event_page(client, setup):
    event = LeaseEvent.objects.get(lease=setup["lease"], event_type="expiry")
    client.force_login(setup["surveyor"])
    response = client.post("/cases/new/", {"event": event.pk})
    case = event.cases.get()
    assert response["Location"] == case.get_absolute_url() and case.case_type.code == "expiry"
    client.post("/cases/new/", {"event": event.pk})
    assert event.cases.count() == 1


def test_new_case_form(client, setup):
    client.force_login(setup["surveyor"])
    response = client.post("/cases/new/", {"case_type": CaseType.objects.get(code="other_activity").pk,
                                           "title": "Filming", "property": setup["unit"].pk,
                                           "how_received": "online", "received_on": "2026-11-03"})
    case = Case.objects.get(title="Filming")
    assert response.status_code == 302 and case.property == setup["unit"]


def test_demo_cases(db):
    from django.core.management import call_command

    call_command("load_demo_data", verbosity=0)
    assert Case.objects.filter(crm_reference__startswith="DEMO").count() == 5
    assert Case.objects.filter(how_received="event").exists()
    call_command("load_demo_data", "--reset", verbosity=0)
    assert Case.objects.filter(crm_reference__startswith="DEMO").count() == 5
