# SPDX-License-Identifier: AGPL-3.0-or-later
"""Access areas: which modules people can open, the surveyor's patch, the supervision chain, cover and finance."""
from datetime import date, timedelta

import pytest
from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import Client

from apps.core import access
from apps.core.models import AccessArea, AuditEntry, Cover, ModuleSettings, StaffProfile
from apps.leases.models import Lease

pytestmark = pytest.mark.own_areas


@pytest.fixture
def demo(db):
    call_command("load_demo_data", verbosity=0)
    return {u.username: u for u in User.objects.filter(username__startswith="demo.")}


def _client(user):
    client = Client(HTTP_HOST="localhost")
    client.force_login(user)
    return client


def _area(code):
    return AccessArea.objects.get(code=code)


def _person(username, role="Surveyors", areas=()):
    user = User.objects.create_user(username, password="a-long-test-password", first_name=username.title())
    user.groups.add(Group.objects.get(name=role))
    user.access_areas.set([_area(c) for c in areas])
    return User.objects.get(pk=user.pk)


def _leases_with_charges(user, inside=True):
    patch = access.patch_leases(user)
    qs = Lease.objects.filter(charges__isnull=False).distinct()
    return (qs.filter(pk__in=patch) if inside else qs.exclude(pk__in=patch)).order_by("pk")


@pytest.mark.django_db
def test_five_standard_areas_exist():
    areas = {a.code: a for a in AccessArea.objects.all()}
    assert set(areas) == {"estates", "finance", "maintenance", "valuation", "legal"}
    assert areas["estates"].own_patch_finance and not areas["estates"].modules
    assert areas["finance"].finance_actions and "ledger" in areas["finance"].modules
    assert set(areas["maintenance"].modules) == {"maintenance", "compliance"}


def test_module_refused_without_area_and_menu_hides_it(demo):
    nobody = _person("no.areas")
    client = _client(nobody)
    response = client.get("/maintenance/jobs/")
    assert response.status_code == 403
    assert "You do not have access to Maintenance" in response.content.decode()
    assert 'href="/maintenance/' not in client.get("/").content.decode()

    nobody.access_areas.add(_area("maintenance"))
    client = _client(User.objects.get(pk=nobody.pk))
    assert client.get("/maintenance/jobs/").status_code == 200
    assert client.get("/compliance/").status_code == 200
    assert client.get("/valuations/").status_code == 403


def test_switched_off_module_stays_off_even_with_an_area(demo):
    settings = ModuleSettings.load()
    settings.maintenance_enabled = False
    settings.save()
    user = _person("maint.person", areas=("maintenance",))
    assert _client(user).get("/maintenance/jobs/").status_code == 404


def test_administrators_open_everything(demo):
    admin = _person("area.admin", role="Administrators")
    client = _client(admin)
    for url in ("/rents/", "/rents/exports/", "/service-charges/", "/maintenance/jobs/", "/compliance/", "/valuations/"):
        assert client.get(url).status_code == 200, url


def test_surveyor_sees_rent_for_own_patch_only(demo):
    lena = demo["demo.lchen"]
    client = _client(lena)
    mine, other = _leases_with_charges(lena).first(), _leases_with_charges(lena, inside=False).first()
    assert mine and other
    assert client.get(f"/rents/accounts/{mine.pk}/").status_code == 200
    assert client.get(f"/rents/accounts/{other.pk}/").status_code == 403
    page = client.get("/rents/").content.decode()
    assert "Showing rent for your patch" in page
    assert client.get("/rents/exports/").status_code == 403
    assert client.get("/rents/runs/new/").status_code == 403
    arrears = client.get("/rents/arrears/").content.decode()
    outside = [lease.reference for lease in _leases_with_charges(lena, inside=False)]
    assert not any(f">{ref}<" in arrears for ref in outside)


def test_supervisor_sees_whole_chain(demo):
    head, lena = demo["demo.head"], demo["demo.lchen"]
    director = _person("estates.director", areas=("estates",))
    StaffProfile.objects.update_or_create(user=head, defaults={"supervisor": director})
    assert lena.pk in access.chain(director)  # director -> Sam Hughes -> Lena Chen
    lease = _leases_with_charges(lena).first()
    assert _client(director).get(f"/rents/accounts/{lease.pk}/").status_code == 200


def test_cover_gives_access_until_its_last_day(demo):
    lena = demo["demo.lchen"]
    stand_in = _person("stand.in", areas=("estates",))
    lease = _leases_with_charges(lena).exclude(pk__in=access.patch_leases(stand_in)).first()
    assert _client(stand_in).get(f"/rents/accounts/{lease.pk}/").status_code == 403
    today = date.today()
    cover = Cover.objects.create(user=stand_in, covered=lena, starts_on=today, ends_on=today + timedelta(days=7))
    assert _client(stand_in).get(f"/rents/accounts/{lease.pk}/").status_code == 200
    cover.ends_on = today - timedelta(days=1)
    cover.save()
    assert _client(stand_in).get(f"/rents/accounts/{lease.pk}/").status_code == 403
    assert AuditEntry.objects.filter(content_type__model="cover").exists()


def test_service_charges_follow_the_patch(demo):
    lena = demo["demo.lchen"]
    nobody_patch = _person("empty.patch", areas=("estates",))
    assert "No service charge schedules yet." in _client(nobody_patch).get("/service-charges/").content.decode()
    page = _client(lena).get("/service-charges/").content.decode()
    assert "/service-charges/schedules/" in page


def test_finance_officer_can_raise_rent_but_viewer_cannot(demo):
    officer = demo["demo.finance"]
    client = _client(officer)
    assert client.get("/rents/runs/new/").status_code == 200
    assert client.get("/rents/exports/").status_code == 200
    assert client.get("/maintenance/jobs/").status_code == 200  # Finance reads maintenance
    assert client.get("/compliance/").status_code == 403
    hub = client.get("/import/").content.decode()
    assert "/import/receipts/" in hub and "/properties/import/" not in hub

    viewer = _person("finance.viewer", role="Viewers", areas=("finance",))
    client = _client(viewer)
    assert client.get("/rents/arrears/").status_code == 200
    assert client.get("/rents/runs/new/").status_code == 403
    assert client.get("/import/").status_code == 403


def test_area_changes_are_in_the_change_log(demo):
    user = _person("logged.person")
    user.access_areas.add(_area("finance"))
    entry = AuditEntry.objects.filter(object_id=str(user.pk), content_type__model="user").latest("timestamp")
    assert entry.changes["access areas"][1] == "added: Finance"


def test_cover_page_for_supervisors_and_administrators(demo):
    head, lena, rob = demo["demo.head"], demo["demo.lchen"], demo["demo.rbaker"]
    outsider = _person("not.a.supervisor", areas=("estates",))
    assert _client(outsider).get("/people/cover/").status_code == 403

    client = _client(head)
    page = client.get("/people/cover/").content.decode()
    assert f'value="{lena.pk}"' in page
    until = (date.today() + timedelta(days=5)).isoformat()
    response = client.post("/people/cover/", {"covered": lena.pk, "user": rob.pk, "starts_on": date.today().isoformat(),
                                              "ends_on": until, "reason": "Annual leave"})
    assert response.status_code == 302
    cover = Cover.objects.get(covered=lena)
    assert cover.user == rob and cover.created_by == head

    bad = client.post("/people/cover/", {"covered": lena.pk, "user": lena.pk, "starts_on": "2026-01-10",
                                         "ends_on": "2026-01-01"})
    assert "Someone cannot cover for themselves" in bad.content.decode()

    client.post("/people/cover/", {"end": cover.pk})
    assert not Cover.objects.filter(pk=cover.pk).exists()  # started today, so cancelled


def test_new_user_form_offers_areas(demo):
    admin = _person("form.admin", role="Administrators")
    page = _client(admin).get("/admin/auth/user/add/").content.decode()
    assert "Access areas" in page and "Finance: Rent ledger" in page
