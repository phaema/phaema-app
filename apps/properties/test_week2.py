# SPDX-License-Identifier: AGPL-3.0-or-later
import io
import shutil
import zipfile
from pathlib import Path

import pytest
from django.contrib.auth.models import Permission, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.urls import reverse
from openpyxl import load_workbook

from apps.core.models import ModuleSettings
from apps.properties.inspire import import_inspire
from apps.properties.models import InspireParcel, Property

SAMPLE = Path(__file__).parent / "testdata" / "inspire_sample.gml"


@pytest.fixture
def officer(db):
    return User.objects.create_superuser("officer", password="a-long-test-password", email="o@example.org")


@pytest.fixture
def demo(db):
    call_command("load_demo_data", verbosity=0)


@pytest.fixture
def client_in(client, officer):
    client.force_login(officer)
    return client


# ------------------------------------------------------------------ maps

def test_register_geojson_is_wgs84_and_filtered(client_in, demo):
    data = client_in.get(reverse("properties:geojson")).json()
    with_location = Property.objects.exclude(boundary=None).count() + Property.objects.filter(
        boundary=None, easting__isnull=False).count()
    assert len(data["features"]) == with_location
    lon, lat = data["features"][0]["geometry"]["coordinates"][0][0][0]
    assert -2 < lon < -1 and 52 < lat < 53  # the demo estate is in the Midlands
    vacant = client_in.get(reverse("properties:geojson"), {"occupation": "vacant"}).json()
    assert {f["properties"]["occupation"] for f in vacant["features"]} == {"vacant"}


def test_property_geojson_roles(client_in, demo):
    block = Property.objects.get(reference="DM-E01-B01")
    data = client_in.get(reverse("properties:detail-geojson", args=[block.pk])).json()
    roles = [f["properties"]["role"] for f in data["features"]]
    assert roles[0] == "parent" and roles.count("self") == 1 and roles.count("part") == 4


def test_inspire_geojson_bbox(client_in, demo):
    data = client_in.get(reverse("properties:inspire-geojson"), {"bbox": "-1.36,52.54,-1.32,52.57"}).json()
    assert data["features"] and all(f["properties"]["inspireId"].startswith("DEMO-") for f in data["features"])
    assert client_in.get(reverse("properties:inspire-geojson"), {"bbox": "-3,51,0,54"}).json()["tooLarge"]
    assert client_in.get(reverse("properties:inspire-geojson"), {"bbox": "x"}).status_code == 400


def test_map_pages_and_os_key(client_in, demo):
    html = client_in.get(reverse("properties:map")).content.decode()
    assert "data-phaema-map" in html and '"osKey": ""' in html
    settings = ModuleSettings.load()
    settings.os_maps_api_key = "test-key-123"
    settings.save()
    unit = Property.objects.get(reference="DM-E01-U01")
    html = client_in.get(unit.get_absolute_url()).content.decode()
    assert '"osKey": "test-key-123"' in html and "Ordnance Survey AC0000851063" in html


# ------------------------------------------------------------------ INSPIRE

def test_import_inspire_gml_and_zip(db, tmp_path):
    gml = tmp_path / "sample.gml"
    shutil.copy(SAMPLE, gml)
    assert import_inspire(str(gml), "sample.gml") == (2, 0, 0)
    parcel = InspireParcel.objects.get(inspire_id="90000001")
    assert parcel.geometry.srid == 27700 and parcel.geometry.area == 10000
    zipped = tmp_path / "inspire.zip"
    with zipfile.ZipFile(zipped, "w") as zf:
        zf.write(SAMPLE, "Land_Registry_Cadastral_Parcels.gml")
    assert import_inspire(str(zipped), "inspire.zip") == (0, 2, 0)


def test_inspire_upload_page(client_in):
    upload = SimpleUploadedFile("Land_Registry_Cadastral_Parcels.gml", SAMPLE.read_bytes())
    resp = client_in.post(reverse("properties:inspire-upload"), {"file": upload}, follow=True)
    assert "2 parcels added" in resp.content.decode()
    resp = client_in.post(reverse("properties:inspire-upload"),
                          {"file": SimpleUploadedFile("bad.zip", b"PK\x05\x06" + b"\0" * 18)}, follow=True)
    assert "does not contain a .gml file" in resp.content.decode()


def test_boundary_from_inspire_joins_parcels(client_in, demo):
    site = Property.objects.get(reference="DM-S06")
    resp = client_in.get(reverse("properties:boundary", args=[site.pk]))
    ids = [p.inspire_id for p in resp.context["parcels"]]
    two = [p.inspire_id for p in resp.context["parcels"] if round(p.geometry.area) in (8000, 6000)]
    assert len(two) == 2 and set(two) <= set(ids)
    resp = client_in.post(reverse("properties:boundary", args=[site.pk]), {"parcel": two})
    assert resp.status_code == 302
    site.refresh_from_db()
    assert round(site.boundary.area) == 14000 and str(site.site_area_ha) == "1.4000"
    assert site.boundary_source.startswith("HM Land Registry INSPIRE DEMO-")


def test_boundary_page_needs_permission(client, demo):
    user = User.objects.create_user("viewer", password="a-long-test-password")
    client.force_login(user)
    site = Property.objects.get(reference="DM-S06")
    assert client.get(reverse("properties:boundary", args=[site.pk])).status_code == 403
    assert client.get(reverse("properties:import")).status_code == 403


# ------------------------------------------------------------------ spreadsheet import

def _csv(text):
    return SimpleUploadedFile("properties.csv", text.encode("utf-8"), "text/csv")


def test_template_is_valid_workbook(client_in):
    resp = client_in.get(reverse("properties:import-template"))
    wb = load_workbook(io.BytesIO(resp.content))
    assert wb.sheetnames == ["Properties", "Lists", "Guidance"]
    assert wb["Properties"]["A1"].value == "Reference*"


def test_import_preview_errors_then_success(client_in, officer, demo):
    bad = ("Reference,Name,Type,Part of,Postcode,Occupation,GIA m2\n"
           "NEW-1,New unit,Lettable unit,NOPE,ZZ99 1AA,Vacant,100\n"
           "NEW-2,Another,Spaceship,,,,\n"
           "NEW-2,Duplicate,Site,,,,\n")
    resp = client_in.post(reverse("properties:import"), {"file": _csv(bad)})
    result = resp.context["result"]
    assert not result.ok and "token" not in resp.context
    errors = {r.number: " ".join(r.errors) for r in result.rows}
    assert "no property with reference NOPE" in errors[2]
    assert "Spaceship" in errors[3] and "more than once" in errors[4]
    assert not Property.objects.filter(reference__startswith="NEW-").exists()

    # The unit comes before its new parent in the file: the import must still work.
    good = ("Reference,Name,Type,Part of,Postcode,Occupation,NIA m2,Managing surveyor,Exclude from open data\n"
            "NEW-U1,New unit,Lettable unit,NEW-B,zz99 1aa,Vacant,95.5,officer,No\n"
            "NEW-B,New building,building,DM-E01,,Partly let,,,\n"
            "DM-E01-U03,Unit 3,Lettable unit,,,Let to a third party,,o@example.org,\n"
            "DM-E01-U01,Unit 1,Lettable unit,,,,,,\n")
    resp = client_in.post(reverse("properties:import"), {"file": _csv(good)})
    result = resp.context["result"]
    assert result.ok, [r.errors for r in result.rows]
    assert (result.count("create"), result.count("update"), result.count("unchanged")) == (2, 1, 1)
    assert "occupation" in result.rows[2].changed
    resp = client_in.post(reverse("properties:import"), {"confirm": "1", "token": resp.context["token"]})
    assert resp.status_code == 302
    unit = Property.objects.get(reference="NEW-U1")
    assert unit.parent.reference == "NEW-B" and unit.parent.parent.reference == "DM-E01"
    assert unit.postcode == "ZZ99 1AA" and str(unit.nia_sqm) == "95.50" and unit.managing_surveyor == officer
    u3 = Property.objects.get(reference="DM-E01-U03")
    assert u3.occupation == "let" and u3.managing_surveyor == officer and u3.nia_sqm == 480  # blanks unchanged


def test_import_xlsx_from_template(client_in):
    wb = load_workbook(io.BytesIO(client_in.get(reverse("properties:import-template")).content))
    ws = wb["Properties"]
    ws.delete_rows(2)
    ws.append(["X-1", "Park", "Site", None, None, None, None, None, "Exampleton", None, "Community",
               "Freehold", "Not applicable", "Park", None, None, None, 3.25, 445100, 295200])
    out = io.BytesIO()
    wb.save(out)
    upload = SimpleUploadedFile("props.xlsx", out.getvalue())
    resp = client_in.post(reverse("properties:import"), {"file": upload})
    assert resp.context["result"].ok
    client_in.post(reverse("properties:import"), {"confirm": "1", "token": resp.context["token"]})
    park = Property.objects.get(reference="X-1")
    assert (park.easting, park.northing, str(park.site_area_ha)) == (445100, 295200, "3.2500")


def test_import_token_cannot_be_reused(client_in):
    resp = client_in.post(reverse("properties:import"), {"file": _csv("Reference,Name,Type\nT-1,Test,Site\n")})
    token = resp.context["token"]
    client_in.post(reverse("properties:import"), {"confirm": "1", "token": token})
    resp = client_in.post(reverse("properties:import"), {"confirm": "1", "token": token}, follow=True)
    assert "expired" in resp.content.decode() and Property.objects.filter(reference="T-1").count() == 1


def test_import_detects_loops(client_in):
    resp = client_in.post(reverse("properties:import"),
                          {"file": _csv("Reference,Name,Type,Part of\nA,A,Site,B\nB,B,Site,A\n")})
    assert not resp.context["result"].ok
    assert "loop" in " ".join(resp.context["result"].rows[0].errors)
