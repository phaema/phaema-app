# SPDX-License-Identifier: AGPL-3.0-or-later
"""Site visits (the visit sheet, level B): starting, answering by section, photos, finishing and the record."""
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from apps.cases import visit
from apps.cases.models import CaseNote, SiteVisit, SiteVisitPhoto
from apps.cases.test_site_visit import case_of, site  # noqa: F401  (the fixture)
from apps.core.roles import ADMINISTRATORS, SURVEYORS, VIEWERS
from apps.properties.models import PropertyPhoto

PASSWORD = "a-long-test-password"


def _jpeg(name="p.jpg"):
    buf = BytesIO()
    Image.new("RGB", (40, 30), "red").save(buf, "JPEG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/jpeg")


@pytest.fixture
def valuation(site):  # noqa: F811
    return case_of("asset_valuation", property=site["estate"], owner=site["sue"])


def test_start_copies_the_checklist_per_building(site, valuation):  # noqa: F811
    v = visit.start_visit(valuation, site["sue"])
    items = valuation.case_type.checklist_items.all()
    each = items.filter(each_building=True).count()
    whole = items.filter(each_building=False).count()
    assert v.answers.count() == whole + 2 * each  # two buildings on the site
    construction = v.answers.get(label="Construction as recorded", building=site["a"])
    assert "portal frame" in construction.recorded
    sections = visit.visit_sections(v)
    assert [s["key"] for s in sections] == ["0", str(site["a"].pk), str(site["b"].pk)]
    assert sections[0]["title"].startswith("The visit as a whole")


def test_who_can_start_and_fill_in(client, site, valuation, make_user):  # noqa: F811
    other = make_user("otto", SURVEYORS)
    make_user("val", VIEWERS)
    start = reverse("cases:visit-start", args=[valuation.pk])
    client.login(username="otto", password=PASSWORD)
    assert client.post(start).status_code == 403
    client.login(username="sue", password=PASSWORD)
    response = client.post(start)
    v = SiteVisit.objects.get(case=valuation)
    assert response.url == v.get_absolute_url() and v.visited_by == site["sue"]
    client.login(username="otto", password=PASSWORD)
    assert client.post(v.get_absolute_url(), {"action": "details", "weather": "Rain"}).status_code == 403
    # people who cannot fill it in are sent to the record
    assert client.get(v.get_absolute_url()).url == reverse("cases:visit-record", args=[valuation.pk, v.pk])
    client.login(username="val", password=PASSWORD)
    assert client.get(reverse("cases:visit-record", args=[valuation.pk, v.pk])).status_code == 200
    assert other.pk


def test_answer_a_section_details_photos_and_finish(client, site, valuation):  # noqa: F811
    v = visit.start_visit(valuation, site["sue"])
    client.login(username="sue", password=PASSWORD)
    url = v.get_absolute_url()
    assert client.get(url).status_code == 200
    tick = v.answers.filter(kind="tick").first()
    text = v.answers.filter(kind="text").first()
    other_section = v.answers.exclude(building=tick.building).first()
    section = str(tick.building_id or 0)
    client.post(url, {"action": "section", "section": section, f"v{tick.pk}": "checked", f"n{tick.pk}": "Seen",
                      f"v{other_section.pk}": "should be ignored"})
    tick.refresh_from_db()
    other_section.refresh_from_db()
    assert tick.value == "checked" and tick.note == "Seen" and tick.answered_at
    assert other_section.value == ""  # only the section being saved changes
    if text:
        client.post(url, {"action": "section", "section": str(text.building_id or 0),
                          f"v{text.pk}": "Some cracking to render"})
        text.refresh_from_db()
        assert text.value == "Some cracking to render"
    yes_no = v.answers.filter(kind="yes_no").first()
    if yes_no:
        client.post(url, {"action": "section", "section": str(yes_no.building_id or 0), f"v{yes_no.pk}": "maybe"})
        yes_no.refresh_from_db()
        assert yes_no.value == ""  # not a yes or no
    client.post(url, {"action": "details", "weather": "Dry", "people_met": "Ann Carpenter",
                      "visited_on": "2026-11-17", "follow_up": "Ask for the asbestos survey"})
    v.refresh_from_db()
    assert v.weather == "Dry" and str(v.visited_on) == "2026-11-17"
    # photos: one about an item, also added to the building's photos; one bad file refused
    client.post(url, {"action": "photos", "answer": tick.pk, "to_property": "1", "photos": [_jpeg()]})
    bad = SimpleUploadedFile("x.jpg", b"not an image", content_type="image/jpeg")
    client.post(url, {"action": "photos", "photos": [bad]})
    photo = SiteVisitPhoto.objects.get(visit=v)
    assert photo.answer == tick and photo.caption == tick.label
    target = tick.building or v.property
    assert PropertyPhoto.objects.filter(property=target).count() == 1 and photo.property_photo_id
    client.post(url, {"action": "finish"})
    v.refresh_from_db()
    assert v.is_finished and v.finished_on
    assert CaseNote.objects.filter(case=valuation, text__startswith="Site visit on").exists()
    # finished: no more changes, except an administrator reopening it
    assert client.post(url, {"action": "details", "weather": "Wet"}).status_code == 403
    assert client.post(url, {"action": "reopen"}).status_code == 403


def test_record_page_and_word(client, site, valuation, make_user):  # noqa: F811
    make_user("boss", ADMINISTRATORS)
    v = visit.start_visit(valuation, site["sue"])
    a = v.answers.filter(kind="tick").first()
    a.value, a.note = "checked", "All as recorded"
    a.save()
    text = visit.build_record(v)
    assert "Site visit record" in text and "All as recorded" in text and "Checked" in text
    client.login(username="boss", password=PASSWORD)
    record = reverse("cases:visit-record", args=[valuation.pk, v.pk])
    page = client.get(record)
    assert page.status_code == 200 and b"All as recorded" in page.content
    word = client.get(record + "?format=docx")
    assert word["Content-Type"].startswith("application/vnd.openxmlformats-officedocument.wordprocessingml")
    v.status = "finished"
    v.save()
    client.post(v.get_absolute_url(), {"action": "reopen"})
    v.refresh_from_db()
    assert v.status == "draft"


def test_checklist_change_does_not_rewrite_a_visit(site, valuation):  # noqa: F811
    v = visit.start_visit(valuation, site["sue"])
    item = valuation.case_type.checklist_items.first()
    old = item.label
    item.label = "Reworded"
    item.save()
    assert v.answers.filter(item=item).first().label == old


def test_case_page_lists_visits(client, site, valuation):  # noqa: F811
    visit.start_visit(valuation, site["sue"])
    client.login(username="sue", password=PASSWORD)
    page = client.get(valuation.get_absolute_url()).content.decode()
    assert "Start a site visit" in page and "In progress" in page
