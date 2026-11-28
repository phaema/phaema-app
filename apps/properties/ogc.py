# SPDX-License-Identifier: AGPL-3.0-or-later
"""Map layers for desktop GIS: an OGC API - Features service (Part 1 Core and GeoJSON, with Part 2 for British
National Grid).

QGIS (Layer, Add Layer, Add WFS / OGC API - Features Layer) and ArcGIS Pro (Add Data, From Path or OGC API server)
connect to ``/api/ogc/`` with an API token, sent as ``Authorization: Bearer <token>``. QGIS sends it through an
authentication configuration of the "API Header" kind. Everything here is read only, sees only what the token's
account may see, and is refused to a token limited to other parts of the API than properties.

Two collections: every property in the register, and only the top-level holdings (sites, estates and stand-alone
buildings), which do not overlap their own parts and so suit thematic maps.
"""
import json
from datetime import datetime, timezone

from django.contrib.gis.db.models.functions import AsGeoJSON, Transform
from django.contrib.gis.geos import Point, Polygon
from django.db.models import Q
from django.urls import reverse
from drf_spectacular.utils import extend_schema
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Property

CRS84 = "http://www.opengis.net/def/crs/OGC/1.3/CRS84"
BNG = "http://www.opengis.net/def/crs/EPSG/0/27700"
SRIDS = {CRS84: 4326, BNG: 27700}
DEFAULT_LIMIT, MAX_LIMIT = 100, 1000

CONFORMANCE = [
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/core",
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/geojson",
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/oas30",
    "http://www.opengis.net/spec/ogcapi-features-2/1.0/conf/crs",
]

COLLECTIONS = {
    "properties": {
        "title": "Properties",
        "description": "Every property in the register: sites, estates, buildings, units and land, with their "
                       "boundaries where drawn and otherwise their grid reference as a point.",
        "top_level_only": False,
    },
    "sites": {
        "title": "Top-level holdings",
        "description": "Only properties that are not part of another (sites, estates and stand-alone buildings "
                       "and land), so the shapes do not overlap.",
        "top_level_only": True,
    },
}

FILTERS = ("property_type", "holding_purpose", "occupation", "tenure", "portfolio")


class GeoJSONRenderer(JSONRenderer):
    media_type = "application/geo+json"
    format = "geojson"


class OgcError(Exception):
    def __init__(self, status, code, description):
        super().__init__(description)
        self.status, self.code, self.description = status, code, description


class OgcView(APIView):
    """Read-only, token-limited to the properties part of the API, and left out of the REST API schema (the
    service describes itself)."""

    basename = "property"  # API tokens limited to parts of the API check this name
    renderer_classes = [JSONRenderer, GeoJSONRenderer]
    http_method_names = ["get", "head", "options"]

    def handle_exception(self, exc):
        if isinstance(exc, OgcError):
            return Response({"code": exc.code, "description": exc.description}, status=exc.status)
        return super().handle_exception(exc)

    def link(self, name, *args, **query):
        url = self.request.build_absolute_uri(reverse(name, args=args))
        query = {k: v for k, v in query.items() if v not in (None, "")}
        if query:
            from urllib.parse import urlencode

            url += "?" + urlencode(query)
        return url


@extend_schema(exclude=True)
class LandingPage(OgcView):
    def get(self, request):
        return Response({
            "title": "PHAEMA map layers",
            "description": "Property boundaries from PHAEMA as OGC API - Features, for QGIS, ArcGIS and other GIS.",
            "links": [
                {"href": self.link("ogc-landing"), "rel": "self", "type": "application/json",
                 "title": "This document"},
                {"href": self.link("ogc-conformance"), "rel": "conformance", "type": "application/json",
                 "title": "Conformance classes"},
                {"href": self.link("ogc-collections"), "rel": "data", "type": "application/json",
                 "title": "Collections"},
                {"href": self.link("api-schema"), "rel": "service-desc",
                 "type": "application/vnd.oai.openapi+json;version=3.0", "title": "The PHAEMA API definition"},
                {"href": request.build_absolute_uri("/help/maps/"), "rel": "service-doc", "type": "text/html",
                 "title": "Help: maps and GIS"},
            ],
        })


@extend_schema(exclude=True)
class Conformance(OgcView):
    def get(self, request):
        return Response({"conformsTo": CONFORMANCE})


def _extent(top_level_only):
    qs = Property.objects.exclude(boundary=None)
    if top_level_only:
        qs = qs.filter(parent=None)
    from django.contrib.gis.db.models import Extent

    box = qs.aggregate(e=Extent(Transform("boundary", 4326)))["e"]
    return [[round(v, 6) for v in box]] if box else [[-8.7, 49.8, 1.8, 60.9]]


@extend_schema(exclude=True)
class Collections(OgcView):
    def get(self, request):
        return Response({
            "links": [{"href": self.link("ogc-collections"), "rel": "self", "type": "application/json"}],
            "collections": [self.describe(cid) for cid in COLLECTIONS],
            "crs": [CRS84, BNG],
        })

    def describe(self, cid):
        meta = COLLECTIONS[cid]
        return {
            "id": cid, "title": meta["title"], "description": meta["description"], "itemType": "feature",
            "extent": {"spatial": {"bbox": _extent(meta["top_level_only"]), "crs": CRS84}},
            "crs": [CRS84, BNG], "storageCrs": BNG,
            "links": [
                {"href": self.link("ogc-collection", cid), "rel": "self", "type": "application/json"},
                {"href": self.link("ogc-items", cid), "rel": "items", "type": "application/geo+json",
                 "title": meta["title"]},
            ],
        }


@extend_schema(exclude=True)
class Collection(Collections):
    def get(self, request, cid):
        if cid not in COLLECTIONS:
            raise OgcError(404, "NotFound", f"There is no collection called {cid}.")
        return Response(self.describe(cid))


def _crs(value, name):
    if not value:
        return CRS84
    if value in SRIDS:
        return value
    raise OgcError(400, "InvalidParameterValue", f"{name} must be {CRS84} or {BNG}.")


def _number(value, name, default, low, high):
    if value in (None, ""):
        return default
    try:
        number = int(value)
    except ValueError:
        raise OgcError(400, "InvalidParameterValue", f"{name} must be a whole number.") from None
    if not low <= number <= high:
        raise OgcError(400, "InvalidParameterValue", f"{name} must be from {low} to {high}.")
    return number


def _bbox(value, crs):
    """The bbox as a polygon in British National Grid, or None."""
    if not value:
        return None
    try:
        parts = [float(v) for v in value.split(",")]
    except ValueError:
        raise OgcError(400, "InvalidParameterValue", "bbox must be four numbers separated by commas.") from None
    if len(parts) == 6:  # with heights: drop them
        parts = [parts[0], parts[1], parts[3], parts[4]]
    if len(parts) != 4 or parts[0] > parts[2] or parts[1] > parts[3]:
        raise OgcError(400, "InvalidParameterValue", "bbox must be minimum x, minimum y, maximum x, maximum y.")
    area = Polygon.from_bbox(parts)
    area.srid = SRIDS[crs]
    if area.srid != 27700:
        area.transform(27700)
    return area


def _queryset(cid, params):
    qs = Property.objects.select_related("parent", "portfolio", "managing_surveyor")
    if COLLECTIONS[cid]["top_level_only"]:
        qs = qs.filter(parent=None)
    for name in FILTERS:
        value = params.get(name)
        if value:
            qs = qs.filter(**{f"{name}_id" if name == "portfolio" else name: value})
    q = (params.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(reference__icontains=q) | Q(name__icontains=q) | Q(town__icontains=q)
                       | Q(postcode__icontains=q))
    return qs


def _feature(p, crs, link):
    if p.gj:
        geometry = json.loads(p.gj)
    elif p.easting is not None and p.northing is not None:
        point = Point(p.easting, p.northing, srid=27700)
        if crs != BNG:
            point.transform(4326)
        geometry = json.loads(point.json)
    else:
        geometry = None
    surveyor = p.managing_surveyor
    return {
        "type": "Feature", "id": p.reference, "geometry": geometry,
        "properties": {
            "reference": p.reference, "name": p.name, "property_type": p.property_type,
            "parent": p.parent.reference if p.parent_id else None,
            "holding_purpose": p.holding_purpose, "tenure": p.tenure, "occupation": p.occupation,
            "use": p.use_description, "use_class": p.use_class, "address": p.address_line_1, "town": p.town,
            "postcode": p.postcode, "uprn": p.uprn, "portfolio": p.portfolio.name if p.portfolio_id else None,
            "managing_surveyor": (surveyor.get_full_name() or surveyor.username) if surveyor else None,
            "site_area_ha": float(p.site_area_ha) if p.site_area_ha is not None else None,
            "gia_sqm": float(p.gia_sqm) if p.gia_sqm is not None else None,
            "nia_sqm": float(p.nia_sqm) if p.nia_sqm is not None else None,
            "easting": p.easting, "northing": p.northing,
            "phaema_url": link(p),
        },
    }


@extend_schema(exclude=True)
class Items(OgcView):
    renderer_classes = [GeoJSONRenderer, JSONRenderer]

    def get(self, request, cid, reference=None):
        if cid not in COLLECTIONS:
            raise OgcError(404, "NotFound", f"There is no collection called {cid}.")
        params = request.query_params
        crs = _crs(params.get("crs"), "crs")
        precision = 7 if crs == CRS84 else 2
        qs = _queryset(cid, params)
        geometry = Transform("boundary", 4326) if crs == CRS84 else "boundary"
        qs = qs.annotate(gj=AsGeoJSON(geometry, precision=precision))

        def link(p):
            return request.build_absolute_uri(p.get_absolute_url())

        headers = {"Content-Crs": f"<{crs}>"}
        if reference is not None:
            p = qs.filter(reference=reference).first()
            if p is None:
                raise OgcError(404, "NotFound", f"There is no property {reference} in {cid}.")
            feature = _feature(p, crs, link)
            feature["links"] = [
                {"href": self.link("ogc-item", cid, reference), "rel": "self", "type": "application/geo+json"},
                {"href": self.link("ogc-collection", cid), "rel": "collection", "type": "application/json"},
                {"href": link(p), "rel": "alternate", "type": "text/html", "title": "In PHAEMA"},
            ]
            return Response(feature, headers=headers)

        area = _bbox(params.get("bbox"), _crs(params.get("bbox-crs"), "bbox-crs"))
        if area is not None:
            xmin, ymin, xmax, ymax = area.extent
            qs = qs.filter(Q(boundary__intersects=area)
                           | Q(boundary=None, easting__gte=xmin, easting__lte=xmax,
                               northing__gte=ymin, northing__lte=ymax))
        limit = _number(params.get("limit"), "limit", DEFAULT_LIMIT, 1, MAX_LIMIT)
        offset = _number(params.get("offset"), "offset", 0, 0, 10_000_000)
        qs = qs.order_by("reference")
        matched = qs.count()
        page = list(qs[offset:offset + limit])
        keep = {k: v for k, v in params.items() if k not in ("offset", "limit", "f")}
        links = [{"href": self.link("ogc-items", cid, **keep, limit=limit, offset=offset or None),
                  "rel": "self", "type": "application/geo+json"},
                 {"href": self.link("ogc-collection", cid), "rel": "collection", "type": "application/json"}]
        if offset + limit < matched:
            links.append({"href": self.link("ogc-items", cid, **keep, limit=limit, offset=offset + limit),
                          "rel": "next", "type": "application/geo+json"})
        if offset:
            links.append({"href": self.link("ogc-items", cid, **keep, limit=limit,
                                            offset=max(0, offset - limit) or None),
                          "rel": "prev", "type": "application/geo+json"})
        return Response({
            "type": "FeatureCollection",
            "features": [_feature(p, crs, link) for p in page],
            "numberMatched": matched, "numberReturned": len(page),
            "timeStamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "links": links,
        }, headers=headers)
