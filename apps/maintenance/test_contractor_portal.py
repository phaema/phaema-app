# SPDX-License-Identifier: AGPL-3.0-or-later
"""Contractor portal: invitations and sign-in codes, only the firm's own issued orders, accepting, declining,
progress notes with photos, reporting the work done with certificates, and the staff side."""
import io
import re
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.core.models import ModuleSettings, OutgoingEmail
from apps.maintenance import workflow
from apps.maintenance.models import Contractor, ContractorAccount, ContractorSignInCode, Job, JobDocument, JobUpdate
from apps.properties.demo_media import placeholder_pdf
from apps.properties.models import Property


@pytest.fixture
def setup(db, make_user):
    settings = ModuleSettings.load()
    settings.maintenance_enabled = settings.contractor_portal_enabled = True
    settings.save()
    officer = make_user("surv", "Surveyors", email="surv@example.org")
    prop = Property.objects.create(reference="B1", name="Library", property_type="building", postcode="ZZ99 1AA",
                                   managing_surveyor=officer, site_hazards="Low roof in the plant room.")
    fixit = Contractor.objects.create(name="Fixit Ltd", email="orders@example.org",
                                      insurance_expires=date.today() + timedelta(days=100))
    other = Contractor.objects.create(name="Other Ltd", email="other@example.org")
    job = workflow.open_job(prop, "Fix the gutter", user=officer, contractor=fixit, estimate=Decimal("400"))
    workflow.issue_order(job, email_contractor=False)
    draft = workflow.open_job(prop, "Not ordered yet", user=officer, contractor=fixit)
    theirs = workflow.open_job(prop, "Someone else's", user=officer, contractor=other)
    workflow.issue_order(theirs, email_contractor=False)
    account = ContractorAccount.objects.create(contractor=fixit, name="Pat Fixit", email="Pat@Fixit.example")
    return {"officer": officer, "job": job, "draft": draft, "theirs": theirs, "account": account, "fixit": fixit}


def _sign_in(client, settings, email="pat@fixit.example"):
    settings.PHAEMA_PORTAL_SHOW_CODES = True
    client.post("/contractor/sign-in/", {"email": email})
    shown = client.session.get("phaema_contractor_shown_code")
    return client.post("/contractor/sign-in/code/", {"code": shown or "000000"})


def test_off_by_default_and_sign_in(client, setup, settings):
    modules = ModuleSettings.load()
    modules.contractor_portal_enabled = False
    modules.save()
    assert client.get("/contractor/sign-in/").status_code == 404
    modules.contractor_portal_enabled = True
    modules.save()
    assert client.get("/contractor/").status_code == 302
    # Unknown addresses get the same answer, and no code.
    client.post("/contractor/sign-in/", {"email": "nobody@example.org"})
    assert not ContractorSignInCode.objects.exists()
    resp = _sign_in(client, settings)
    assert resp.status_code == 302 and resp["Location"] == "/contractor/"
    email = OutgoingEmail.objects.get(kind="contractor_code")
    assert "••••••" in email.body and not re.search(r"\d{6}", email.body)
    home = client.get("/contractor/")
    assert [j.pk for j in home.context["waiting"]] == [setup["job"].pk]
    assert home["Content-Security-Policy"].startswith("default-src 'self'")


def test_only_own_issued_orders(client, setup, settings):
    _sign_in(client, settings)
    assert client.get(f"/contractor/jobs/{setup['job'].pk}/").status_code == 200
    assert client.get(f"/contractor/jobs/{setup['draft'].pk}/").status_code == 404
    assert client.get(f"/contractor/jobs/{setup['theirs'].pk}/").status_code == 404
    page = client.get(f"/contractor/jobs/{setup['job'].pk}/").content.decode()
    assert "Low roof in the plant room" in page and "surv@example.org" in page
    # Staff pages stay closed to a contractor session.
    assert client.get("/maintenance/").status_code in (302, 403)


def test_accept_note_and_complete(client, setup, settings, mailoutbox):
    job = setup["job"]
    _sign_in(client, settings)
    url = f"/contractor/jobs/{job.pk}/"
    client.post(url, {"action": "accept", "attend_on": (date.today() + timedelta(days=2)).isoformat(),
                      "note": "Booked in"})
    job.refresh_from_db()
    assert job.contractor_response == "accepted" and job.attend_on == date.today() + timedelta(days=2)
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), "red").save(buf, "JPEG")
    client.post(url, {"action": "note", "text": "Scaffold up", "photo": SimpleUploadedFile("p.jpg", buf.getvalue())})
    note = JobUpdate.objects.get(kind="note")
    assert note.photo and client.get(f"/contractor/jobs/{job.pk}/photos/{note.pk}/").status_code == 200
    bad = client.post(url, {"action": "complete", "completed_on": (date.today() + timedelta(days=5)).isoformat(),
                            "notes": "Done", "cost": "380"})
    assert bad.status_code == 200 and "future" in bad.content.decode()
    resp = client.post(url, {"action": "complete", "completed_on": date.today().isoformat(), "notes": "Gutter fixed",
                             "cost": "380.50", "invoice": "INV-77",
                             "certificates": [SimpleUploadedFile("cert.pdf", placeholder_pdf("Cert", ["x"]))]})
    job.refresh_from_db()
    assert resp.status_code == 302 and job.status == "completed" and job.actual_cost == Decimal("380.50")
    assert job.invoice_reference == "INV-77" and job.completion_notes == "Gutter fixed"
    doc = JobDocument.objects.get(job=job)
    assert doc.from_contractor and client.get(f"/contractor/jobs/{job.pk}/documents/{doc.pk}/").status_code == 200
    assert [u.kind for u in job.updates.all()] == ["accepted", "note", "completed"]
    assert any("Work reported done" in m.subject for m in mailoutbox)
    # A finished job takes no more changes.
    assert client.post(url, {"action": "note", "text": "More"}).status_code == 404

    # Contractors' updates and the account are in the change log; signing in is not (core.audit._EXCLUDED).
    assert len(_logged(JobUpdate, "create")) == 3
    assert _logged(ContractorAccount, "create") and not _logged(ContractorAccount, field="last_sign_in")
    setup["account"].refresh_from_db()
    assert setup["account"].last_sign_in is not None

    # The officer sees it all on the job.
    client.force_login(setup["officer"])
    page = client.get(f"/maintenance/jobs/{job.pk}/").content.decode()
    assert "From the contractor" in page and "Scaffold up" in page


def test_decline_tells_the_officer_and_a_new_order_resets(client, setup, settings, mailoutbox):
    job = setup["job"]
    _sign_in(client, settings)
    client.post(f"/contractor/jobs/{job.pk}/", {"action": "decline", "reason": "No roofer free this month"})
    job.refresh_from_db()
    assert job.contractor_response == "declined" and "declined" in mailoutbox[-1].subject
    assert client.post(f"/contractor/jobs/{job.pk}/", {"action": "accept"}).status_code == 404
    workflow.issue_order(job, email_contractor=False)
    job.refresh_from_db()
    assert job.contractor_response == ""


def test_staff_add_invite_and_stop_accounts(client, setup, settings, make_user):
    client.force_login(setup["officer"])
    fixit = setup["fixit"]
    page = client.get(f"/maintenance/contractors/{fixit.pk}/")
    assert "Contractor portal" in page.content.decode()
    client.post(f"/maintenance/contractors/{fixit.pk}/", {"action": "add_account", "name": "Sam", "email": "sam@f.example"})
    sam = ContractorAccount.objects.get(email="sam@f.example")
    assert sam.invited_at and OutgoingEmail.objects.filter(kind="contractor_invite", to="sam@f.example").exists()
    client.post(f"/maintenance/contractors/{fixit.pk}/", {"action": "stop", "account": sam.pk})
    sam.refresh_from_db()
    assert not sam.active
    viewer = make_user("view", "Viewers")
    client.force_login(viewer)
    assert client.post(f"/maintenance/contractors/{fixit.pk}/", {"action": "restart", "account": sam.pk}).status_code == 403
    # A stopped account cannot sign in.
    client.logout()
    resp = _sign_in(client, settings, "sam@f.example")
    assert resp.status_code == 200 and "not right" in resp.content.decode()


def test_works_order_email_mentions_the_portal(setup, mailoutbox):
    job = workflow.open_job(setup["job"].property, "Another", contractor=setup["fixit"])
    workflow.issue_order(job)
    assert "/contractor/sign-in/" in mailoutbox[-1].body
    assert Job.objects.filter(contractor=setup["fixit"]).count() == 3


def _logged(model, action=None, field=None):
    """Change log entries for a model, optionally of one action or touching one field."""
    from django.contrib.contenttypes.models import ContentType

    from apps.core.models import AuditEntry

    rows = AuditEntry.objects.filter(content_type=ContentType.objects.get_for_model(model))
    if action:
        rows = rows.filter(action=action)
    return [r for r in rows if field is None or field in r.changes]
