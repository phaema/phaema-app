# SPDX-License-Identifier: AGPL-3.0-or-later
"""Import HM Land Registry INSPIRE Index Polygons.

Councils download these free for their area from
https://use-land-property-data.service.gov.uk/datasets/inspire as a zip containing
Land_Registry_Cadastral_Parcels.gml (British National Grid). Importing the same
area again updates parcels by INSPIRE ID.
"""
import os
import tempfile
import zipfile

from django.contrib.gis.gdal import DataSource
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon
from django.db import transaction

from .models import InspireParcel

BATCH = 2000


class InspireImportError(Exception):
    pass


def _open(path):
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".gml") and not n.startswith("__MACOSX")]
        if not names:
            raise InspireImportError("The zip file does not contain a .gml file.")
        return [f"/vsizip/{path}/{n}" for n in names]
    return [path]


def _field(feature, *names):
    for name in names:
        try:
            value = feature.get(name)
        except (IndexError, KeyError):
            continue
        if value not in (None, ""):
            return value
    return None


def import_inspire(path, source_name=""):
    """Import parcels from a GML or zip file. Returns (created, updated, skipped)."""
    created = updated = skipped = 0
    for source in _open(path):
        try:
            ds = DataSource(source)
        except Exception as exc:  # GDAL raises its own error types
            raise InspireImportError(f"Could not read the file: {exc}") from exc
        for layer in ds:
            batch = {}
            for feature in layer:
                inspire_id = _field(feature, "INSPIREID", "inspireId", "INSPIRE_ID")
                geom = feature.geom
                if not inspire_id or geom is None:
                    skipped += 1
                    continue
                g = GEOSGeometry(geom.wkb, srid=geom.srid or 27700)
                if g.srid != 27700:
                    g.transform(27700)
                if g.geom_type == "Polygon":
                    g = MultiPolygon(g, srid=27700)
                elif g.geom_type != "MultiPolygon":
                    skipped += 1
                    continue
                batch[str(inspire_id)] = g
                if len(batch) >= BATCH:
                    c, u = _save(batch, source_name)
                    created, updated, batch = created + c, updated + u, {}
            if batch:
                c, u = _save(batch, source_name)
                created, updated = created + c, updated + u
    return created, updated, skipped


@transaction.atomic
def _save(batch, source_name):
    existing = {p.inspire_id: p for p in InspireParcel.objects.filter(inspire_id__in=batch.keys())}
    to_update = []
    for inspire_id, geom in batch.items():
        if inspire_id in existing:
            parcel = existing[inspire_id]
            parcel.geometry, parcel.source_file = geom, source_name
            to_update.append(parcel)
    if to_update:
        InspireParcel.objects.bulk_update(to_update, ["geometry", "source_file"])
    new = [InspireParcel(inspire_id=i, geometry=g, source_file=source_name)
           for i, g in batch.items() if i not in existing]
    InspireParcel.objects.bulk_create(new)
    return len(new), len(to_update)


def import_uploaded_file(uploaded):
    """Save an uploaded file to a temporary path (GDAL needs a real file) and import it."""
    suffix = os.path.splitext(uploaded.name)[1].lower() or ".gml"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        for chunk in uploaded.chunks():
            tmp.write(chunk)
        path = tmp.name
    try:
        return import_inspire(path, source_name=uploaded.name)
    finally:
        for leftover in (path, os.path.splitext(path)[0] + ".gfs"):  # GDAL writes a .gfs schema file
            if os.path.exists(leftover):
                os.unlink(leftover)
