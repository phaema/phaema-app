# SPDX-License-Identifier: AGPL-3.0-or-later
"""The public test site: keeping real sign-ins through a data reset, and the banner that warns testers."""
import io
import json

import pytest
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import Client

from apps.core.models import AccessArea, StaffProfile


def test_accounts_need_a_demo_site(settings, make_user):
    settings.PHAEMA_DEMO_SITE = False
    with pytest.raises(CommandError):
        call_command("demo_accounts", "export", stdout=io.StringIO())


@pytest.mark.own_areas
def test_accounts_survive_a_reset(settings, make_user):
    settings.PHAEMA_DEMO_SITE = True
    boss = make_user("t.boss", "Surveyors")
    tester = make_user("t.tester", "Surveyors")
    tester.set_password("tester-pass-2026")
    tester.save()
    estates = AccessArea.objects.get(code="estates")
    tester.access_areas.set([estates])
    StaffProfile.objects.create(user=tester, job_title="Estates surveyor", supervisor=boss)
    make_user("demo.someone", "Surveyors")  # demo people are recreated by the demo data, not saved

    out = io.StringIO()
    call_command("demo_accounts", "export", stdout=out)
    saved = json.loads(out.getvalue())
    assert {row["username"] for row in saved["accounts"]} == {"t.boss", "t.tester"}
    assert "tester-pass-2026" not in out.getvalue()  # only the password hash is kept

    get_user_model().objects.all().delete()
    call_command("demo_accounts", "import", stdin=io.StringIO(json.dumps(saved)), stderr=io.StringIO())

    restored = get_user_model().objects.get(username="t.tester")
    assert restored.check_password("tester-pass-2026")
    assert list(restored.access_areas.all()) == [estates]
    assert restored.groups.filter(name="Surveyors").exists()
    assert restored.staff_profile.supervisor.username == "t.boss"
    assert restored.staff_profile.job_title == "Estates surveyor"
    assert not get_user_model().objects.filter(username="demo.someone").exists()


def test_test_site_banner(settings, make_user):
    client = Client()
    client.force_login(make_user("t.viewer", "Viewers"))
    settings.PHAEMA_DEMO_SITE = False
    assert "reset every" not in client.get("/").content.decode()
    settings.PHAEMA_DEMO_SITE = True
    page = client.get("/").content.decode()
    assert "public test site with fictional data" in page and "reset every 48 hours" in page


def test_request_a_test_account(settings, make_user):
    from django.core import mail
    from django.core.cache import cache

    from apps.core.models import AccountRequest

    cache.clear()
    settings.PHAEMA_ACCOUNT_REQUEST_EMAIL = "owner@example.org"
    client = Client()
    settings.PHAEMA_DEMO_SITE = False
    assert client.get("/request-account/").status_code == 404
    settings.PHAEMA_DEMO_SITE = True
    assert "Request a test account" in client.get("/login/").content.decode()
    assert "Request a test account" in client.get("/request-account/").content.decode()

    bad = client.post("/request-account/", {"name": "", "email": "not-an-email"})
    assert "There is a problem" in bad.content.decode() and not AccountRequest.objects.exists()

    sent = client.post("/request-account/", {"name": "Pat Example", "email": "pat@example.org",
                                             "organisation": "Exampleton Council", "reason": "Rent reviews"})
    assert "Request sent" in sent.content.decode()
    req = AccountRequest.objects.get()
    assert (req.name, req.email, req.done) == ("Pat Example", "pat@example.org", False)
    assert len(mail.outbox) == 1 and mail.outbox[0].to == ["owner@example.org"]
    assert "pat@example.org" in mail.outbox[0].body and "Exampleton Council" in mail.outbox[0].body

    # A bot filling the hidden box gets the thank-you page, but nothing is kept or sent.
    client.post("/request-account/", {"name": "Bot", "email": "bot@example.org", "website": "http://spam"})
    assert AccountRequest.objects.count() == 1 and len(mail.outbox) == 1

    # Open requests survive a reset; finished ones do not need to.
    out = io.StringIO()
    call_command("demo_accounts", "export", stdout=out)
    data = json.loads(out.getvalue())
    AccountRequest.objects.all().delete()
    call_command("demo_accounts", "import", stdin=io.StringIO(json.dumps(data)), stderr=io.StringIO())
    assert AccountRequest.objects.get().email == "pat@example.org"


def test_too_many_requests(settings, db):
    from django.core.cache import cache

    from apps.core.models import AccountRequest

    cache.clear()
    settings.PHAEMA_DEMO_SITE = True
    client = Client()
    for i in range(6):
        page = client.post("/request-account/", {"name": f"Person {i}", "email": f"p{i}@example.org"})
    assert AccountRequest.objects.count() == 5 and "Too many requests" in page.content.decode()
