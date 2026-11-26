# SPDX-License-Identifier: AGPL-3.0-or-later
"""Occupier contacts: departmental liaisons and read-only people see their own buildings only, and liaisons
record headcount for the managing surveyor to check."""
from datetime import date

import pytest
from django.test import Client

from apps.core.models import AuditEntry, ModuleSettings
from apps.space.models import Headcount, Occupation, Occupier

from .test_costs import setup  # noqa: F401  (the fixture)


def _client(user):
    client = Client(HTTP_HOST="localhost")
    client.force_login(user)
    return client


@pytest.fixture
def people(make_user, setup):  # noqa: F811
    sam = make_user("sam", "Surveyors", first_name="Sam", last_name="Hughes", email="sam@example.org")
    setup["building"].managing_surveyor = sam
    setup["building"].save()
    lee = make_user("lee", first_name="Lee", last_name="Okafor")       # no role
    head = make_user("head", first_name="Hana", last_name="Read")      # no role
    nobody = make_user("nobody")                                        # no role, not named
    housing = setup["housing"]
    housing.liaison = lee
    housing.save()
    housing.readers.add(head)
    return {"sam": sam, "lee": lee, "head": head, "nobody": nobody, **setup}


def test_liaison_goes_to_their_buildings_and_nowhere_else(people):
    lee = _client(people["lee"])
    home = lee.get("/")
    assert home.status_code == 302 and home["Location"] == "/occupier/"
    page = lee.get("/occupier/").content.decode()
    assert "Civic Centre" in page and "Housing" in page
    for closed in ("/properties/", "/leases/", "/space/", "/api/properties/", "/admin/", "/changes/",
                   f"/properties/{people['building'].pk}/"):
        assert lee.get(closed).status_code in (302, 403, 404), closed
    assert lee.get("/account/password/").status_code == 200
    assert lee.get("/help/occupier-contacts/").status_code == 200


def test_shared_building_names_everyone_but_shows_own_figures_only(people):
    page = _client(people["lee"]).get(f"/occupier/building/{people['building'].pk}/").content.decode()
    assert "NHS clinic" in page          # named in the stacking plan
    table = page[page.index("Your space and people"):]
    assert "Housing" in table and "NHS clinic" not in table.split("Record how many")[0]
    assert "Sam Hughes" in page and "sam@example.org" in page


def test_other_buildings_are_not_found(people):
    from apps.properties.models import Property

    other = Property.objects.create(reference="X1", name="Depot", property_type="building")
    Occupation.objects.create(building=other, occupier=people["nhs"], starts=date(2025, 4, 1))
    assert _client(people["lee"]).get(f"/occupier/building/{other.pk}/").status_code == 404


def test_people_not_named_and_module_off_get_nothing(people):
    assert _client(people["nobody"]).get("/occupier/").status_code == 403
    settings = ModuleSettings.load()
    settings.space_enabled = False
    settings.save()
    assert _client(people["lee"]).get("/occupier/").status_code == 403


def test_teams_below_the_department_are_included(people):
    team = Occupier.objects.create(name="Housing options", level="team", parent=people["housing"])
    from apps.properties.models import Property

    annex = Property.objects.create(reference="AN1", name="Annex", property_type="building")
    Occupation.objects.create(building=annex, occupier=team, starts=date(2025, 4, 1))
    assert "Annex" in _client(people["lee"]).get("/occupier/").content.decode()


def test_liaison_records_headcount_for_the_surveyor_to_check(people):
    lee = _client(people["lee"])
    b = people["building"]
    response = lee.post(f"/occupier/building/{b.pk}/", {"occupier": people["housing"].pk, "people": "64",
                                                        "fte": "58.5", "counted_on": date.today().isoformat()})
    assert response.status_code == 302
    count = Headcount.objects.get(building=b, occupier=people["housing"], counted_on=date.today())
    assert count.people == 64 and count.from_department and count.checked_on is None
    assert "Lee Okafor" in count.source and count.created_by == people["lee"]
    assert AuditEntry.objects.filter(object_id=str(count.pk), action="create", user=people["lee"]).exists()
    # The managing surveyor sees it on the dashboard and marks it checked.
    sam = _client(people["sam"])
    assert "Headcount from a department to check" in sam.get("/").content.decode()
    check = f"/space/headcount/{count.pk}/check/"
    assert "60" in sam.get(check).content.decode()    # the earlier figure
    sam.post(check)
    count.refresh_from_db()
    assert count.checked_by == people["sam"] and count.checked_on == date.today()
    assert "Headcount from a department to check" not in sam.get("/").content.decode()


def test_bad_figures_are_refused(people):
    lee = _client(people["lee"])
    b = people["building"]
    for bad in ({"people": "lots"}, {"people": "-3"}, {"people": "5", "fte": "x"},
                {"people": "5", "counted_on": "2999-01-01"}):
        lee.post(f"/occupier/building/{b.pk}/", {"occupier": people["housing"].pk, **bad})
    assert not Headcount.objects.filter(from_department=True).exists()


def test_read_only_people_and_other_occupiers_cannot_record(people):
    b = people["building"]
    head = _client(people["head"])
    assert "Civic Centre" in head.get("/occupier/").content.decode()
    assert "Record how many people" not in head.get(f"/occupier/building/{b.pk}/").content.decode()
    assert head.post(f"/occupier/building/{b.pk}/", {"occupier": people["housing"].pk,
                                                    "people": "1"}).status_code == 404
    # The liaison cannot record for another occupier in the same building.
    assert _client(people["lee"]).post(f"/occupier/building/{b.pk}/", {"occupier": people["nhs"].pk,
                                                                      "people": "1"}).status_code == 404
    assert not Headcount.objects.filter(from_department=True).exists()


def test_only_the_managing_surveyor_or_an_administrator_checks(people, make_user):
    count = Headcount.objects.create(building=people["building"], occupier=people["housing"], people=70,
                                     from_department=True)
    other = _client(make_user("ola", "Surveyors"))
    assert other.post(f"/space/headcount/{count.pk}/check/").status_code == 404
    assert _client(people["lee"]).post(f"/space/headcount/{count.pk}/check/").status_code in (403, 404)
    _client(make_user("ann", "Administrators")).post(f"/space/headcount/{count.pk}/check/")
    count.refresh_from_db()
    assert count.checked_on is not None


def test_removing_the_contact_ends_access(people):
    housing = people["housing"]
    housing.liaison = None
    housing.save()
    housing.readers.clear()
    assert _client(people["lee"]).get("/occupier/").status_code == 403
    assert _client(people["head"]).get("/occupier/").status_code == 403
