# SPDX-License-Identifier: AGPL-3.0-or-later
"""Open data published without signing in, under the Open Government Licence v3.0.

The Local Government Transparency Code land and assets list, and property available to let.
Properties marked 'exclude from open data' never appear.
"""
import csv
import json

from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import cache_page

from apps.core.models import ModuleSettings

from .models import Property

LICENCE = "Open Government Licence v3.0"
LICENCE_URL = "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"

ASSET_COLUMNS = [
    ("asset_reference", "Asset reference"), ("uprn", "UPRN"), ("name", "Property name"),
    ("address", "Street address"), ("town", "Town"), ("postcode", "Postcode"), ("easting", "Easting"),
    ("northing", "Northing"), ("tenure", "Tenure"), ("property_type", "Type"), ("holding_purpose", "Purpose"),
    ("occupation", "Occupation"), ("site_area_ha", "Site area (ha)"), ("gia_sqm", "Gross internal area (m²)"),
]
AVAILABLE_COLUMNS = [
    ("asset_reference", "Asset reference"), ("uprn", "UPRN"), ("name", "Property name"), ("address", "Street address"),
    ("town", "Town"), ("postcode", "Postcode"), ("easting", "Easting"), ("northing", "Northing"),
    ("use", "Use"), ("use_class", "Use class"), ("nia_sqm", "Net internal area (m²)"),
    ("gia_sqm", "Gross internal area (m²)"), ("site_area_ha", "Site area (ha)"),
]


def _enabled():
    settings = ModuleSettings.load()
    if not settings.open_data_enabled:
        raise Http404
    return settings


def _without_excluded_parents():
    """Publishable properties: not excluded themselves, and not part of anything excluded."""
    everything = list(Property.objects.order_by("reference"))
    parent = {p.pk: p.parent_id for p in everything}
    excluded = {p.pk for p in everything if p.exclude_from_publication or p.disposed_on}

    def hidden(pk):
        while pk is not None:
            if pk in excluded:
                return True
            pk = parent.get(pk)
        return False

    return [p for p in everything if not hidden(p.pk)]


def _row(p):
    address = ", ".join(x for x in (p.address_line_1, p.address_line_2) if x)
    return {
        "asset_reference": p.reference, "uprn": p.uprn or "", "name": p.name, "address": address, "town": p.town,
        "postcode": p.postcode, "easting": p.easting or "", "northing": p.northing or "",
        "tenure": p.get_tenure_display() if p.tenure else "", "property_type": p.get_property_type_display(),
        "holding_purpose": p.get_holding_purpose_display() if p.holding_purpose else "",
        "occupation": p.get_occupation_display() if p.occupation else "",
        "site_area_ha": p.site_area_ha if p.site_area_ha is not None else "",
        "gia_sqm": p.gia_sqm if p.gia_sqm is not None else "", "nia_sqm": p.nia_sqm if p.nia_sqm is not None else "",
        "use": p.use_text(with_class=False), "use_class": p.use_class,
    }


def _available(rows):
    parents = set(Property.objects.exclude(parent=None).values_list("parent_id", flat=True))
    return [p for p in rows if p.occupation == Property.Occupation.VACANT and p.property_type != "estate"
            and p.pk not in parents]


DATASETS = {
    "land-and-assets": ("Land and assets", "Every piece of land and every building the council owns or uses, as the "
                        "Local Government Transparency Code requires.", ASSET_COLUMNS, lambda rows: rows),
    "available-property": ("Property available", "Vacant property the council may let.", AVAILABLE_COLUMNS,
                           _available),
}


def index(request):
    settings = _enabled()
    return render(request, "properties/open_data.html", {
        "settings": settings, "datasets": [(slug, d[0], d[1]) for slug, d in DATASETS.items()],
        "licence": LICENCE, "licence_url": LICENCE_URL})


@cache_page(300)
def dataset(request, slug, fmt):
    settings = _enabled()
    if slug not in DATASETS or fmt not in ("csv", "json", "geojson"):
        raise Http404
    title, description, columns, pick = DATASETS[slug]
    rows = pick(_without_excluded_parents())
    publisher = settings.organisation_name or "PHAEMA"
    if fmt == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{slug}.csv"'
        response.write("﻿")
        writer = csv.writer(response)
        writer.writerow([label for _k, label in columns])
        for p in rows:
            r = _row(p)
            writer.writerow([r[k] for k, _l in columns])
        return response
    if fmt == "json":
        return JsonResponse({"title": title, "publisher": publisher, "licence": LICENCE, "licence_url": LICENCE_URL,
                             "records": [{k: _json(_row(p)[k]) for k, _l in columns} for p in rows]},
                            json_dumps_params={"ensure_ascii": False})
    features = []
    for p in rows:
        geometry = None
        if p.boundary:
            geometry = json.loads(p.boundary.transform(4326, clone=True).geojson)
        elif p.easting and p.northing:
            from django.contrib.gis.geos import Point

            geometry = json.loads(Point(p.easting, p.northing, srid=27700).transform(4326, clone=True).geojson)
        features.append({"type": "Feature", "geometry": geometry,
                         "properties": {k: _json(_row(p)[k]) for k, _l in columns}})
    response = JsonResponse({"type": "FeatureCollection", "name": title, "publisher": publisher,
                             "licence": LICENCE, "features": features}, json_dumps_params={"ensure_ascii": False})
    response["Content-Type"] = "application/geo+json"
    return response


def _json(value):
    from decimal import Decimal

    return float(value) if isinstance(value, Decimal) else value
