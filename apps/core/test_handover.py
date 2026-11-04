# SPDX-License-Identifier: AGPL-3.0-or-later
"""Hand over work: moving a leaver's properties, cases, tasks and approvals to colleagues."""
import pytest
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.test import Client

from apps.cases.models import Case, CaseTask
from apps.core import handover
from apps.core.models import AuditEntry
from apps.leases.models import LeaseEvent
from apps.properties.models import Property


@pytest.fixture
def demo(db):
    call_command("load_demo_data", verbosity=0)
    return {u.username: u for u in User.objects.filter(username__startswith="demo.")}


def _admin(make_user):
    admin = make_user("handover.admin", "Administrators")
    client = Client(HTTP_HOST="localhost")
    client.force_login(admin)
    return admin, client


def test_page_is_for_administrators_only(make_user):
    surveyor = make_user("handover.surveyor", "Surveyors")
    client = Client(HTTP_HOST="localhost")
    client.force_login(surveyor)
    assert client.get("/people/hand-over/").status_code == 403
    assert 'href="/people/hand-over/"' not in client.get("/").content.decode()


def test_menu_link_for_administrators(make_user):
    _, client = _admin(make_user)
    assert 'href="/people/hand-over/">Hand over work</a>' in client.get("/").content.decode()


def test_hand_over_everything_and_stop_sign_in(demo, make_user):
    admin, client = _admin(make_user)
    lena, rob = demo["demo.lchen"], demo["demo.rbaker"]
    before = {item.key: count for item, count, _ in handover.summary(lena)}
    assert before["properties"] and before["cases"] and before["case_tasks"] and before["lease_events"]

    page = client.get(f"/people/hand-over/?from={lena.pk}&to={rob.pk}")
    assert page.status_code == 200
    assert f'value="{rob.pk}" selected' in page.content.decode()

    post = {"from": lena.pk, "deactivate": "1"}
    post.update({f"to_{item.key}": rob.pk for item in handover.items()})
    response = client.post("/people/hand-over/", post)
    assert response.status_code == 302

    assert all(count == 0 for _, count, _ in handover.summary(lena))
    assert Property.objects.filter(managing_surveyor=rob).count() >= before["properties"]
    lena.refresh_from_db()
    assert not lena.is_active
    # Each record was saved individually, so the change log shows who handed it over.
    moved = AuditEntry.objects.filter(user=admin, content_type=ContentType.objects.get_for_model(Property))
    assert moved.count() == before["properties"]


def test_choose_per_kind_and_leave_some(demo, make_user):
    _, client = _admin(make_user)
    lena, rob, head = demo["demo.lchen"], demo["demo.rbaker"], demo["demo.head"]
    tasks = CaseTask.objects.filter(owner=lena, done_on__isnull=True).exclude(case__status="closed").count()
    client.post("/people/hand-over/", {"from": lena.pk, "to_properties": rob.pk, "to_cases": head.pk})
    assert not Property.objects.filter(managing_surveyor=lena).exists()
    assert not Case.objects.filter(owner=lena).exclude(status="closed").exists()
    assert Case.objects.filter(owner=head).exists()
    assert CaseTask.objects.filter(owner=lena, done_on__isnull=True).exclude(case__status="closed").count() == tasks
    lena.refresh_from_db()
    assert lena.is_active


def test_limit_to_one_building(demo, make_user):
    _, client = _admin(make_user)
    lena, rob = demo["demo.lchen"], demo["demo.rbaker"]
    held = Property.objects.filter(managing_surveyor=lena)
    building = next(p for p in held if p.property_type in ("estate", "site", "building"))
    inside = set(handover.items()[0].records(lena, building.pk).values_list("pk", flat=True))
    assert inside and len(inside) < held.count()

    post = {"from": lena.pk, "building": building.pk}
    post.update({f"to_{item.key}": rob.pk for item in handover.items()})
    client.post("/people/hand-over/", post)
    assert set(Property.objects.filter(pk__in=inside).values_list("managing_surveyor", flat=True)) == {rob.pk}
    assert Property.objects.filter(managing_surveyor=lena).count() == held.count() - len(inside)


def test_supervisees_and_approvals_move(demo, make_user):
    admin, client = _admin(make_user)
    head = demo["demo.head"]
    supervisees = handover.items()[-1].records(head).count()
    assert supervisees
    client.post("/people/hand-over/", {"from": head.pk, "to_supervisees": admin.pk,
                                       "to_case_approvals": admin.pk, "to_job_approvals": admin.pk})
    assert all(count == 0 for item, count, _ in handover.summary(head)
               if item.key in ("supervisees", "case_approvals", "job_approvals"))


def test_viewer_cannot_receive_work(demo, make_user):
    _, client = _admin(make_user)
    viewer = make_user("handover.viewer", "Viewers")
    lena = demo["demo.lchen"]
    count = Property.objects.filter(managing_surveyor=lena).count()
    response = client.post("/people/hand-over/", {"from": lena.pk, "to_properties": viewer.pk}, follow=True)
    assert "Choose someone who can receive" in response.content.decode()
    assert Property.objects.filter(managing_surveyor=lena).count() == count
    assert not LeaseEvent.objects.filter(assigned_to=viewer).exists()
