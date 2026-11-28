# SPDX-License-Identifier: AGPL-3.0-or-later
"""Map layers for GIS (OGC API - Features): token sign-in, collections, paging, bbox, CRS and token limits."""
import pytest
from django.contrib.gis.geos import MultiPolygon, Polygon

from apps.core.models import ApiToken
from apps.core.roles import SURVEYORS
from apps.core.test_api_tokens import bearer, make_token
from apps.properties.models import Property
from apps.properties.ogc import BNG, CONFORMANCE

E0, N0 = 445000, 295000


def square(dx, dy, size=100):
    poly = Polygon.from_bbox((E0 + dx, N0 + dy, E0 + dx + size, N0 + dy + size))
    return MultiPolygon(poly, srid=27700)


@pytest.fixture
def sue(make_user):
    return make_user("sue", SURVEYORS)


@pytest.fixture
def estate(db):
    site = Property.objects.create(reference="G-1", name="Mill Estate", property_type="estate",
                                   boundary=square(0, 0, 400), town="Exampleton")
    for i in range(3):
        Property.objects.create(reference=f"G-1-U{i + 1}", name=f"Unit {i + 1}", property_type="unit",
                                parent=site, boundary=square(10 + 100 * i, 10, 90), occupation="let")
    Property.objects.create(reference="G-2", name="Far field", property_type="land", boundary=square(5000, 5000))
    Property.objects.create(reference="G-3", name="Kiosk", property_type="building", easting=E0 + 50,
                            northing=N0 + 50)
    return site


def test_needs_sign_in(client, estate):
    assert client.get("/api/ogc/collections/properties/items").status_code in (401, 403)


def test_landing_conformance_and_collections(client, sue, estate):
    _token, key = make_token(sue)
    landing = client.get("/api/ogc/", **bearer(key)).json()
    rels = {link["rel"] for link in landing["links"]}
    assert {"self", "conformance", "data", "service-desc"} <= rels
    assert client.get("/api/ogc/conformance", **bearer(key)).json()["conformsTo"] == CONFORMANCE
    collections = client.get("/api/ogc/collections", **bearer(key)).json()["collections"]
    assert [c["id"] for c in collections] == ["properties", "sites"]
    one = client.get("/api/ogc/collections/sites", **bearer(key)).json()
    assert one["storageCrs"] == BNG and one["extent"]["spatial"]["bbox"][0][0] < -1
    assert client.get("/api/ogc/collections/nothing", **bearer(key)).status_code == 404


def test_items_geojson_paging_and_point_fallback(client, sue, estate):
    _token, key = make_token(sue)
    resp = client.get("/api/ogc/collections/properties/items?limit=2", **bearer(key))
    assert resp.status_code == 200 and resp["Content-Type"].startswith("application/geo+json")
    assert resp["Content-Crs"] == "<http://www.opengis.net/def/crs/OGC/1.3/CRS84>"
    data = resp.json()
    assert data["numberMatched"] == 6 and data["numberReturned"] == 2
    assert [f["id"] for f in data["features"]] == ["G-1", "G-1-U1"]
    lon, lat = data["features"][0]["geometry"]["coordinates"][0][0][0]
    assert -2 < lon < -1 and 52 < lat < 53  # CRS84: longitude first
    nxt = next(link["href"] for link in data["links"] if link["rel"] == "next")
    page2 = client.get(nxt, **bearer(key)).json()
    assert [f["id"] for f in page2["features"]] == ["G-1-U2", "G-1-U3"]
    kiosk = client.get("/api/ogc/collections/properties/items/G-3", **bearer(key)).json()
    assert kiosk["geometry"]["type"] == "Point" and kiosk["properties"]["phaema_url"].startswith("http")


def test_sites_bbox_crs_and_filters(client, sue, estate):
    _token, key = make_token(sue)
    sites = client.get("/api/ogc/collections/sites/items", **bearer(key)).json()
    assert {f["id"] for f in sites["features"]} == {"G-1", "G-2", "G-3"}
    bng = f"{E0 - 10},{N0 - 10},{E0 + 500},{N0 + 500}"
    near = client.get(f"/api/ogc/collections/properties/items?bbox={bng}&bbox-crs={BNG}&crs={BNG}",
                      **bearer(key))
    ids = {f["id"] for f in near.json()["features"]}
    assert ids == {"G-1", "G-1-U1", "G-1-U2", "G-1-U3", "G-3"} and near["Content-Crs"] == f"<{BNG}>"
    first = near.json()["features"][0]["geometry"]["coordinates"][0][0][0]
    assert first[0] > 400000  # eastings in British National Grid
    let = client.get("/api/ogc/collections/properties/items?occupation=let", **bearer(key)).json()
    assert let["numberMatched"] == 3
    bad = client.get("/api/ogc/collections/properties/items?bbox=1,2,3", **bearer(key))
    assert bad.status_code == 400 and bad.json()["code"] == "InvalidParameterValue"
    assert client.get("/api/ogc/collections/properties/items?limit=5000", **bearer(key)).status_code == 400
    assert client.get("/api/ogc/collections/properties/items/NOPE", **bearer(key)).status_code == 404


def test_read_only_and_token_limits(client, sue, estate):
    _token, key = make_token(sue, access=ApiToken.Access.CHANGE)
    assert client.post("/api/ogc/collections/properties/items", {}, **bearer(key)).status_code in (403, 405)
    _token, leases_only = make_token(sue, resources=["lease"])
    assert client.get("/api/ogc/collections/properties/items", **bearer(leases_only)).status_code == 403
    _token, props_only = make_token(sue, resources=["property"])
    assert client.get("/api/ogc/collections/properties/items", **bearer(props_only)).status_code == 200


def test_signed_in_browser_session_works(client, sue, estate):
    client.force_login(sue)
    assert client.get("/api/ogc/collections/properties/items", HTTP_ACCEPT="application/geo+json").status_code == 200
