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


# ------------------------------------------------------------------ part 2: differences, saved record, reporting

def _finished_with_differences(site, valuation):  # noqa: F811
    v = visit.start_visit(valuation, site["sue"])
    construction = v.answers.get(label="Construction as recorded", building=site["a"])
    construction.kind, construction.value, construction.note = "yes_no", "no", "Steel frame, not portal"
    construction.save()
    areas = v.answers.filter(checks="floor_areas").first()
    if areas is None:
        areas = construction
    else:
        areas.value = "GIA 1,250 m²"
        areas.save()
    v.status = "finished"
    v.save()
    return v, construction, areas


def test_differences_found(site, valuation):  # noqa: F811
    v, construction, _areas = _finished_with_differences(site, valuation)
    found = visit.differences(v)
    assert construction in found
    # a tick or an unanswered item is never a difference; nor is an answer that matches the record
    same = v.answers.exclude(pk__in=[a.pk for a in found]).filter(checks__gt="").first()
    if same:
        same.kind, same.value = "text", same.recorded
        same.save()
        assert not visit.is_difference(same)
    assert "Differences from the record" in visit.build_record(v)


def test_update_the_record_and_leave_it(client, site, valuation, make_user):  # noqa: F811
    v, construction, _areas = _finished_with_differences(site, valuation)
    record = reverse("cases:visit-record", args=[valuation.pk, v.pk])
    update = reverse("cases:visit-update", args=[valuation.pk, v.pk, construction.pk])
    # someone who cannot edit the building cannot update it
    make_user("otto", SURVEYORS)
    client.login(username="otto", password=PASSWORD)
    assert client.get(update).status_code == 403
    assert b"To decide by the managing surveyor" in client.get(record).content
    site["a"].managing_surveyor = site["sue"]  # the normal edit rule: the building's own managing surveyor
    site["a"].save()
    client.login(username="sue", password=PASSWORD)
    page = client.get(update)
    assert page.status_code == 200 and b"Steel frame, not portal" in page.content
    client.post(update, {"construction_type": "steel_frame", "construction_detail": "Steel frame, brick infill"})
    site["a"].refresh_from_db()
    construction.refresh_from_db()
    assert site["a"].construction_detail == "Steel frame, brick infill"
    assert construction.resolution == "applied" and construction.resolved_by == site["sue"]
    # a second difference left as it was
    other = v.answers.exclude(pk=construction.pk).filter(checks__gt="").first()
    other.kind, other.value = "text", "Something else entirely"
    other.save()
    client.post(v.get_absolute_url(), {"action": "keep", "answer": other.pk})
    other.refresh_from_db()
    assert other.resolution == "kept"
    assert construction not in visit.open_differences(v) and other not in visit.open_differences(v)


def test_check_measure_offers_areas(client, site, valuation):  # noqa: F811
    v = visit.start_visit(valuation, site["sue"])
    a = v.answers.filter(checks="floor_areas", building=site["a"]).first() or v.answers.filter(
        checks="floor_areas").first()
    if a is None:
        pytest.skip("this checklist has no floor areas item")
    a.value = "GIA 999 m²"
    a.save()
    v.status = "finished"
    v.save()
    a.target.managing_surveyor = site["sue"]
    a.target.save()
    client.login(username="sue", password=PASSWORD)
    url = reverse("cases:visit-update", args=[valuation.pk, v.pk, a.pk])
    page = client.get(url).content.decode()
    assert 'name="gia_sqm"' in page and 'value="survey" selected' in page
    client.post(url, {"gia_sqm": "999", "area_standard": "", "area_source": "survey",
                      "areas_measured_on": str(v.visited_on)})
    a.target.refresh_from_db()
    assert a.target.gia_sqm == 999 and a.target.areas_measured_on == v.visited_on


def test_finishing_saves_the_record_to_the_case(client, site, valuation):  # noqa: F811
    v = visit.start_visit(valuation, site["sue"])
    client.login(username="sue", password=PASSWORD)
    client.post(v.get_absolute_url(), {"action": "finish"})
    doc = valuation.documents.get()
    assert doc.description.startswith("Site visit record") and doc.file.name.endswith(".docx")


def test_hand_over_unfinished_visits(site, valuation, make_user):  # noqa: F811
    from apps.core import handover

    other = make_user("otto", SURVEYORS)
    v = visit.start_visit(valuation, site["sue"])
    done = visit.start_visit(valuation, site["sue"])
    done.status = "finished"
    done.save()
    moved = handover.hand_over(site["sue"], {"site_visits": other})
    v.refresh_from_db()
    done.refresh_from_db()
    assert moved["site_visits"] == 1 and v.visited_by == other and done.visited_by == site["sue"]


def test_my_work_and_reports(site, valuation):  # noqa: F811
    from apps.core import mywork
    from apps.reports.datasets import get as dataset

    v, _c, _a = _finished_with_differences(site, valuation)
    draft = visit.start_visit(valuation, site["sue"])
    notes = [str(i.note) for i in mywork.build(site["sue"])["now"] if str(i.kind) == "Site visit"]
    assert any("not yet finished" in n for n in notes) and any("to decide" in n for n in notes)
    ds = dataset("site_visits")
    row = next(r for r in ds.queryset() if r.pk == v.pk)
    assert ds.field("differences").value(row) >= 1
    cases = dataset("cases")
    case_row = next(c for c in cases.queryset() if c.pk == valuation.pk)
    assert cases.field("last_visited").value(case_row) == v.visited_on
    assert draft.pk
