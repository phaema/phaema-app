# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import date, timedelta
from decimal import Decimal
from email.message import EmailMessage

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.cases import workflow
from apps.cases.models import Case, CaseNote, CaseType, Correspondence
from apps.core.dates import add_working_days
from apps.core.models import ModuleSettings, StaffProfile
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


def test_decisions_need_reasons_under_the_1988_act(client, make_user, setup):
    case = workflow.open_case(CaseType.objects.get(code="assignment"), title="A", lease=setup["lease"])
    _approved(case, setup["surveyor"], make_user)
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
    assert Case.objects.filter(crm_reference__startswith="DEMO").count() == 7
    assert Case.objects.filter(how_received="event").exists()
    assert Case.objects.get(crm_reference="DEMO-1").approvals.filter(status="pending").exists()
    call_command("load_demo_data", "--reset", verbosity=0)
    assert Case.objects.filter(crm_reference__startswith="DEMO").count() == 7


def _supervise(user, supervisor):
    StaffProfile.objects.update_or_create(user=user, defaults={"supervisor": supervisor})


def _approved(case, surveyor, make_user):
    head = make_user("head", "Surveyors")
    _supervise(surveyor, head)
    workflow.decide_approval(workflow.request_approval(case, surveyor, "decision", "Approve"), head, True)
    case.refresh_from_db()


def test_approval_is_needed_before_the_decision(client, make_user, mailoutbox, setup):
    head = make_user("head", "Surveyors", email="head@example.org")
    surveyor = setup["surveyor"]
    surveyor.email = "surv@example.org"
    surveyor.save()
    case = workflow.open_case(CaseType.objects.get(code="assignment"), title="A", lease=setup["lease"])
    case.stage = "assessing"
    case.save()
    url = case.get_absolute_url()
    client.force_login(surveyor)
    assert "No supervisor" in client.get(url).content.decode()
    client.post(url, {"action": "next_stage"})
    client.post(url, {"action": "decide", "decision": "approved", "date": "2026-11-20"})
    case.refresh_from_db()
    assert case.stage == "assessing" and case.decision == ""
    _supervise(surveyor, head)
    # A conflict of interest declaration comes first (RICS Conflicts of interest).
    client.post(url, {"action": "request_approval", "stage": "decision", "recommendation": "Grant, with an AGA"})
    assert not case.approvals.exists()
    client.post(url, {"action": "save_conflict", "conflict": "declared"})  # details are needed
    case.refresh_from_db()
    assert case.conflict == ""
    client.post(url, {"action": "save_conflict", "conflict": "none"})
    case.refresh_from_db()
    assert case.conflict == "none" and case.conflict_by == surveyor
    client.post(url, {"action": "request_approval", "stage": "decision", "recommendation": "Grant, with an AGA"})
    approval = case.approvals.get()
    assert approval.approver == head and approval.status == "pending"
    assert mailoutbox[-1].to == ["head@example.org"] and case.display_reference in mailoutbox[-1].subject
    # The surveyor cannot approve their own request.
    assert client.post(url, {"action": "approve"}).status_code == 403
    # The supervisor returns it, then approves the revised recommendation.
    client.force_login(head)
    assert client.get("/cases/?approval=mine").context["paginator"].count == 1
    assert "1 case waiting for your approval" in client.get("/").content.decode()
    client.post(url, {"action": "return", "comments": ""})  # comments are needed to return
    approval.refresh_from_db()
    assert approval.status == "pending"
    client.post(url, {"action": "return", "comments": "Ask for a rent deposit too"})
    approval.refresh_from_db()
    assert approval.status == "returned" and approval.decided_by == head and mailoutbox[-1].to == ["surv@example.org"]
    client.force_login(surveyor)
    client.post(url, {"action": "request_approval", "stage": "decision", "recommendation": "Grant, AGA and deposit"})
    client.force_login(head)
    client.post(url, {"action": "approve", "comments": "Agreed"})
    case.refresh_from_db()
    assert case.stage == "decision" and case.approvals.filter(status="approved").count() == 1
    client.force_login(surveyor)
    client.post(url, {"action": "decide", "decision": "conditions", "reasons": "AGA and deposit",
                      "date": "2026-11-20"})
    case.refresh_from_db()
    assert case.decision == "conditions"
    assert "Grant, AGA and deposit" in client.get(url).content.decode()  # the approval history


def test_other_users_and_administrators(client, make_user, setup):
    head, other = make_user("head", "Surveyors"), make_user("other", "Surveyors")
    admin_user = make_user("admin", "Administrators")
    _supervise(setup["surveyor"], head)
    case = workflow.open_case(CaseType.objects.get(code="assignment"), title="A", lease=setup["lease"])
    approval = workflow.request_approval(case, setup["surveyor"], "decision", "Grant")
    with pytest.raises(ValueError):
        workflow.request_approval(case, setup["surveyor"], "decision", "Again")
    client.force_login(other)
    assert client.post(case.get_absolute_url(), {"action": "approve"}).status_code == 403
    client.force_login(admin_user)
    client.post(case.get_absolute_url(), {"action": "reassign_approval", "approver": other.pk})
    approval.refresh_from_db()
    assert approval.approver == other
    client.post(case.get_absolute_url(), {"action": "approve"})  # administrators can approve
    approval.refresh_from_db()
    assert approval.status == "approved" and approval.decided_by == admin_user
    _supervise(head, head)
    with pytest.raises(ValueError):
        workflow.request_approval(case, head, "decision", "Mine")


def test_types_without_approval_move_freely(client, setup):
    case = workflow.open_case(CaseType.objects.get(code="enquiry"), title="Q", lease=setup["lease"])
    assert not CaseType.objects.get(code="enquiry").approval_stages
    client.force_login(setup["surveyor"])
    for _i in range(3):
        client.post(case.get_absolute_url(), {"action": "next_stage"})
    case.refresh_from_db()
    assert case.stage == "decision"


def test_lease_event_outcome_waits_for_approval(client, make_user, setup):
    workflow.auto_open()
    review = LeaseEvent.objects.get(lease=setup["lease"], event_type="review")
    case = review.cases.get()
    client.force_login(setup["surveyor"])
    data = {"record_outcome": "1", "new_rent": "11000", "effective_from": review.due_date.isoformat(),
            "notes": "Agreed"}
    response = client.post(review.get_absolute_url(), data)
    review.refresh_from_db()
    assert response.status_code == 200 and review.is_open and "Approval needed" in response.content.decode()
    _approved(case, setup["surveyor"], make_user)
    client.post(review.get_absolute_url(), data)
    review.refresh_from_db()
    assert not review.is_open


def test_dashboard_lists_surveyors_without_a_supervisor(client, make_user, setup):
    client.force_login(make_user("admin", "Administrators"))
    assert "No supervisor" in client.get("/").content.decode()
    _supervise(setup["surveyor"], make_user("head", "Administrators"))
    assert "No supervisor" not in client.get("/").content.decode()


def test_heads_of_terms_before_a_new_letting_decision(client, make_user, setup):
    from apps.cases import leasing

    case = workflow.open_case(CaseType.objects.get(code="new_letting"), title="Let", property=setup["unit"])
    case.stage = "assessing"
    case.save()
    _supervise(setup["surveyor"], make_user("head", "Surveyors"))
    client.force_login(setup["surveyor"])
    url = case.get_absolute_url()
    assert "0 of 16 items covered" in client.get(url).content.decode()
    client.post(url, {"action": "request_approval", "stage": "decision", "recommendation": "Let it"})
    assert not case.approvals.exists()
    data = {f"hot_{k}": "Agreed" for k in leasing.KEYS}
    data.update(action="save_heads", tenant_represented="no")
    client.post(url, data)
    case.refresh_from_db()
    assert len(leasing.answered(case)) == 16
    assert leasing.problems(case) and "supplemental guide" in str(leasing.problems(case)[0])
    data["code_given_on"] = "2026-11-02"
    client.post(url, data)
    case.refresh_from_db()
    assert leasing.problems(case) == [] and case.code_given_on == date(2026, 11, 2)
    client.post(url, {"action": "save_conflict", "conflict": "none"})
    client.post(url, {"action": "request_approval", "stage": "decision", "recommendation": "Let it"})
    assert case.approvals.filter(status="pending").exists()


def test_renewal_notice_dates(client, setup):
    from apps.cases import leasing

    case = workflow.open_case(CaseType.objects.get(code="renewal"), title="Renew", lease=setup["lease"])
    assert leasing.from_lease(setup["lease"])["rent"].startswith("£10,000.00 a year")
    client.force_login(setup["surveyor"])
    url = case.get_absolute_url()
    client.post(url, {"action": "save_notice", "notice_kind": "s26", "notice_served_on": "2026-01-10",
                      "notice_date": "2026-11-01"})
    case.refresh_from_db()
    dates = leasing.notice_dates(case)
    assert dates.counter_notice_due == date(2026, 3, 10) and dates.court_deadline == date(2026, 10, 31)
    assert case.target_date == date(2026, 10, 31)
    assert any("before the lease" in str(w) for w in dates.warnings)  # the lease runs beyond that date
    case.notice_kind, case.notice_date = "s25", date(2026, 3, 1)
    dates = leasing.notice_dates(case)
    assert dates.court_deadline == date(2026, 3, 1) and any("6 and 12 months" in str(w) for w in dates.warnings)
    assert "Last day to apply to court" in client.get(url).content.decode()


def test_new_lease_fields(client, setup):
    lease = setup["lease"]
    lease.special_rights, lease.rates_excluded, lease.deposit = "Two parking spaces", False, Decimal("2500")
    lease.deposit_held = "Council deposit account"
    lease.save()
    client.force_login(setup["surveyor"])
    page = client.get(lease.get_absolute_url()).content.decode()
    assert "Two parking spaces" in page and "Includes business rates" in page and "Council deposit account" in page
