# SPDX-License-Identifier: AGPL-3.0-or-later
from decimal import Decimal
from io import BytesIO

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.urls import reverse
from PIL import Image

from apps.core.models import AuditEntry
from apps.properties.models import Property, PropertyPhoto, Title, TitleDocument


@pytest.fixture
def officer(make_user):
    return make_user("officer", "Administrators", first_name="Sam", last_name="Officer")


@pytest.fixture
def demo(db):
    call_command("load_demo_data", verbosity=0)


@pytest.fixture
def client_in(client, officer):
    client.force_login(officer)
    return client


def _jpeg_with_gps(size=(3000, 2000)):
    img = Image.new("RGB", size, "red")
    exif = Image.Exif()
    exif[0x8825] = {2: (51.0, 30.0, 0.0)}  # GPS IFD with a latitude
    exif[0x010F] = "PhoneMaker"
    out = BytesIO()
    img.save(out, "JPEG", exif=exif)
    return out.getvalue()


def test_dashboard_shows_vacancy_and_floor_space(client_in, demo):
    resp = client_in.get(reverse("dashboard"))
    ctx = resp.context
    assert ctx["unit_count"] == Property.objects.filter(property_type="unit").count()
    # Vacant leaves in the demo: units 3 and 8, shop 3 and suite 3 (NIA 480 + 640 + 72 + 60)
    assert ctx["vacant_space"]["nia"] == Decimal("1252")
    assert ctx["vacancy_rate"] is not None
    html = resp.content.decode()
    assert "?property_type=unit" in html and "occupation=vacant" in html
    assert reverse("change", args=[AuditEntry.objects.first().pk]) in html


def test_change_detail_shows_who_when_and_readable_values(client_in, officer, demo):
    from apps.core.middleware import _current_user

    p = Property.objects.get(reference="DM-S06")
    token = _current_user.set(officer)
    try:
        p.occupation = "council"
        p.save()
    finally:
        _current_user.reset(token)
    entry = AuditEntry.objects.filter(object_id=str(p.pk), action="update").first()
    html = client_in.get(reverse("change", args=[entry.pk])).content.decode()
    assert "Sam Officer" in html and "Vacant" in html and "Occupied by the council" in html
    assert client_in.get(reverse("changes"), {"user": officer.pk}).context["page_obj"].paginator.count == 1


def test_register_sort_and_surveyor_filter(client_in, demo, officer):
    url = reverse("properties:list")
    names = [p.name for p in client_in.get(url, {"sort": "-name"}).context["page_obj"]]
    assert names == sorted(names, reverse=True)
    priya = User.objects.get(username="demo.pshah")
    listed = client_in.get(url, {"surveyor": priya.pk}).context["page_obj"].paginator.count
    assert listed == Property.objects.filter(managing_surveyor=priya).count() > 0
    unassigned = client_in.get(url, {"surveyor": "none"}).context["page_obj"]
    assert {p.reference for p in unassigned} == {"DM-S06", "DM-S10"}
    Property.objects.filter(reference="DM-S06").update(managing_surveyor=officer)
    assert [p.reference for p in client_in.get(url, {"surveyor": "me"}).context["page_obj"]] == ["DM-S06"]
    # Units inherit their estate's surveyor in the demo data
    assert Property.objects.get(reference="DM-E01-U03").managing_surveyor.username == "demo.amorgan"


def test_area_breakdown(demo):
    block = Property.objects.get(reference="DM-E01-B01")
    b = block.area_breakdown()
    assert b["leaf_count"] == 4 and b["leaf_nia"] == Decimal("2400")
    assert b["gia"] == block.gia_sqm and b["non_lettable"] == block.gia_sqm - Decimal("2400")
    estate = Property.objects.get(reference="DM-E01").area_breakdown()
    assert estate["gia_source"] == "buildings" and estate["leaf_count"] == 8
    assert Property.objects.get(reference="DM-E01-U01").area_breakdown() is None


def test_photo_upload_is_resized_and_location_removed(db):
    p = Property.objects.create(reference="P1", name="Test", property_type="building")
    photo = PropertyPhoto(property=p, image=SimpleUploadedFile("site.jpg", _jpeg_with_gps(), "image/jpeg"))
    photo.full_clean()
    photo.save()
    with Image.open(photo.image.path) as img:
        assert max(img.size) == 2000
        assert not img.getexif().get(0x8825) and not img.getexif().get(0x010F)
    path = photo.image.path
    photo.delete()
    import os
    assert not os.path.exists(path)


def test_only_one_main_photo(db):
    p = Property.objects.create(reference="P2", name="Test", property_type="building")
    a = PropertyPhoto.objects.create(property=p, is_main=True, image=SimpleUploadedFile("a.jpg", _jpeg_with_gps((50, 50))))
    PropertyPhoto.objects.create(property=p, is_main=True, image=SimpleUploadedFile("b.jpg", _jpeg_with_gps((50, 50))))
    a.refresh_from_db()
    assert not a.is_main and p.photos.filter(is_main=True).count() == 1


def test_invalid_uploads_are_rejected(db):
    p = Property.objects.create(reference="P3", name="Test", property_type="building")
    with pytest.raises(ValidationError):
        PropertyPhoto(property=p, image=SimpleUploadedFile("x.jpg", b"not an image")).full_clean()
    t = Title.objects.create(title_number="ZZ1", tenure="freehold")
    with pytest.raises(ValidationError):
        TitleDocument(title=t, document_type="register", file=SimpleUploadedFile("x.pdf", b"<html>")).full_clean()


def test_files_require_sign_in(client, officer, demo):
    doc = TitleDocument.objects.first()
    url = doc.file.url
    assert url.startswith("/files/titles/")
    assert client.get(url).status_code == 302
    client.force_login(officer)
    resp = client.get(url)
    assert resp.status_code == 200 and resp["Content-Type"] == "application/pdf"
    assert b"".join(resp.streaming_content).startswith(b"%PDF-")
    assert client.get("/files/../settings.py").status_code == 404


def test_property_and_title_pages(client_in, demo):
    unit3 = Property.objects.get(reference="DM-E01-U03")
    html = client_in.get(unit3.get_absolute_url()).content.decode()
    assert "data-phaema-gallery" in html and "Photo 1 of 3" in html and "Alex Morgan" in html
    block = Property.objects.get(reference="DM-E01-B01")
    html = client_in.get(block.get_absolute_url()).content.decode()
    assert "How the floor area is made up" in html and "Net to gross" in html
    title = Title.objects.get(title_number="ZZ100001")
    html = client_in.get(title.get_absolute_url()).content.decode()
    assert "Official copy of the register" in html and "PDF" in html


def test_text_size_setting(client, db):
    resp = client.get(reverse("text-size", args=["large"]), {"next": "/properties/"})
    assert resp.status_code == 302 and resp["Location"] == "/properties/"
    assert resp.cookies["phaema_text_size"].value == "large"
    assert client.get(reverse("text-size", args=["x"])).status_code == 404
    resp = client.get(reverse("text-size", args=["large"]), {"next": "https://evil.example/"})
    assert resp["Location"] == "/"
    assert b"phaema-text-large" in client.get(reverse("login")).content


def test_unchanged_decimal_is_not_logged_as_change(db):
    p = Property.objects.create(reference="D1", name="Test", property_type="unit", nia_sqm=Decimal("480"))
    p.name = "Renamed"
    p.save()
    change = AuditEntry.objects.filter(object_id=str(p.pk), action="update").get()
    assert list(change.changes) == ["name"]
