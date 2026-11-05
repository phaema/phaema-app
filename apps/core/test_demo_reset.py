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
    assert {row["username"] for row in saved} == {"t.boss", "t.tester"}
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
