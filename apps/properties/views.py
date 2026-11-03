# SPDX-License-Identifier: AGPL-3.0-or-later
import json
import os
import uuid
from datetime import date

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.db.models.functions import AsGeoJSON, Transform
from django.contrib.gis.geos import Point, Polygon
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.storage import default_storage
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods
from django.views.generic import DetailView, ListView

from apps.core.models import AuditEntry, ModuleSettings
from apps.core.roles import can_edit, is_administrator
from apps.core.tables import sortable

from . import importer
from .inspire import InspireImportError, import_uploaded_file
from .models import InspireParcel, Property, Title, inspire_attribution

COLUMNS = {
    "reference": (_("Reference"), ["reference"], False),
    "name": (_("Name"), ["name", "reference"], False),
    "type": (_("Type"), ["property_type", "reference"], False),
    "purpose": (_("Purpose"), ["holding_purpose", "reference"], False),
    "occupation": (_("Occupation"), ["occupation", "reference"], False),
    "postcode": (_("Postcode"), ["postcode", "reference"], False),
    "nia": (_("NIA m²"), ["nia_sqm", "reference"], True),
    "surveyor": (_("Managed by"), ["managing_surveyor__first_name", "managing_surveyor__last_name",
                                   "managing_surveyor__username", "reference"], False),
}
FILTERS = ("property_type", "holding_purpose", "occupation", "tenure")


def display_name(user):
    return (user.get_full_name() or user.username) if user else ""


def filter_properties(request, qs):
    """Apply the register's search box and filters (shared by the list, map and map data)."""
    get = request.GET
    q = get.get("q", "").strip()
    if q:
        qs = qs.filter(
            Q(reference__icontains=q) | Q(name__icontains=q) | Q(uprn=q)
            | Q(address_line_1__icontains=q) | Q(town__icontains=q)
            | Q(postcode__icontains=q) | Q(titles__title_number__iexact=q.replace(" ", ""))
        ).distinct()
    for f in FILTERS:
        if get.get(f):
            qs = qs.filter(**{f: get[f]})
    surveyor = get.get("surveyor", "")
    if surveyor == "me":
        qs = qs.filter(managing_surveyor=request.user)
    elif surveyor == "none":
        qs = qs.filter(managing_surveyor__isnull=True)
    elif surveyor.isdigit():
        qs = qs.filter(managing_surveyor_id=int(surveyor))
    return qs


def filter_context(request):
    get = request.GET
    surveyors = get_user_model().objects.filter(is_active=True).filter(
        Q(managed_properties__isnull=False) | Q(is_staff=True)
    ).distinct().order_by("first_name", "last_name", "username")
    params = get.copy()
    params.pop("page", None)
    return {
        "q": get.get("q", ""),
        "filters": [(f, Property._meta.get_field(f).verbose_name, Property._meta.get_field(f).choices, get.get(f, ""))
                    for f in FILTERS],
        "surveyor_options": [("me", _("My properties")), ("none", _("Unassigned"))]
        + [(str(u.pk), display_name(u)) for u in surveyors],
        "surveyor_selected": get.get("surveyor", ""),
        "querystring": params.urlencode(),
    }


def map_config():
    settings = ModuleSettings.load()
    return {
        "osKey": settings.os_maps_api_key,
        "osStyle": settings.os_map_style,
        "year": date.today().year,
        "inspireUrl": reverse("properties:inspire-geojson"),
        "inspireAttribution": inspire_attribution(),
    }


class PropertyListView(LoginRequiredMixin, ListView):
    model = Property
    paginate_by = 50
    template_name = "properties/property_list.html"

    def get_queryset(self):
        qs = filter_properties(self.request, Property.objects.select_related("parent", "managing_surveyor"))
        ordering, self.headings = sortable(self.request, COLUMNS, "reference")
        return qs.order_by(*ordering)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(filter_context(self.request))
        ctx["headings"] = self.headings
        return ctx


@login_required
def register_map(request):
    ctx = filter_context(request)
    ctx["map_config"] = map_config()
    ctx["features_url"] = reverse("properties:geojson") + ("?" + ctx["querystring"] if ctx["querystring"] else "")
    ctx["count"] = filter_properties(request, Property.objects.all()).count()
    return render(request, "properties/property_map.html", ctx)


class PropertyDetailView(LoginRequiredMixin, DetailView):
    model = Property
    template_name = "properties/property_detail.html"

    def get_queryset(self):
        return Property.objects.select_related("parent", "managing_surveyor").prefetch_related("photos")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        obj = self.object
        ctx["children"] = obj.children.all()
        ctx["titles"] = obj.titles.prefetch_related("documents")
        ctx["photos"] = list(obj.photos.all())
        ctx["breakdown"] = obj.area_breakdown()
        ctx["surveyor_name"] = display_name(obj.managing_surveyor)
        ctx["leases"] = obj.leases.select_related("counterparty").order_by("status", "-term_start")
        ctx["map_config"] = map_config()
        ctx["has_location"] = bool(obj.boundary or obj.easting) or any(
            p.boundary or p.easting for p, _d in (ctx["breakdown"]["parts"] if ctx["breakdown"] else []))
        ctx["history"] = AuditEntry.objects.filter(
            content_type=ContentType.objects.get_for_model(Property), object_id=str(obj.pk)
        ).select_related("user")[:20]
        return ctx


class TitleDetailView(LoginRequiredMixin, DetailView):
    model = Title
    template_name = "properties/title_detail.html"

    def get_queryset(self):
        return Title.objects.prefetch_related("properties", "documents")


# ---------------------------------------------------------------- map data (GeoJSON, WGS84)

OCCUPATION_LABELS = dict(Property.Occupation.choices)


def _features(queryset, role_for=None):
    rows = queryset.annotate(gj=AsGeoJSON(Transform("boundary", 4326), precision=7))
    features = []
    for p in rows:
        if p.gj:
            geometry = json.loads(p.gj)
        elif p.easting and p.northing:
            pt = Point(p.easting, p.northing, srid=27700)
            pt.transform(4326)
            geometry = {"type": "Point", "coordinates": [round(pt.x, 7), round(pt.y, 7)]}
        else:
            continue
        features.append({
            "type": "Feature",
            "geometry": geometry,
            "properties": {
                "reference": p.reference, "name": p.name, "type": p.get_property_type_display(),
                "occupation": p.occupation, "occupationLabel": OCCUPATION_LABELS.get(p.occupation, ""),
                "url": p.get_absolute_url(), "role": role_for(p) if role_for else "property",
            },
        })
    return {"type": "FeatureCollection", "features": features}


@login_required
def register_geojson(request):
    qs = filter_properties(request, Property.objects.all())
    return JsonResponse(_features(qs.order_by("reference")))


@login_required
def property_geojson(request, pk):
    obj = get_object_or_404(Property, pk=pk)
    ids = {obj.pk} | obj._descendant_ids()
    if obj.parent_id:
        ids.add(obj.parent_id)

    def role(p):
        return "self" if p.pk == obj.pk else ("parent" if p.pk == obj.parent_id else "part")

    data = _features(Property.objects.filter(pk__in=ids), role)
    order = {"parent": 0, "self": 1, "part": 2}
    data["features"].sort(key=lambda f: order[f["properties"]["role"]])
    return JsonResponse(data)


@login_required
def inspire_geojson(request):
    """INSPIRE parcels inside a map view. bbox = minLon,minLat,maxLon,maxLat (WGS84)."""
    try:
        bbox = [float(v) for v in request.GET.get("bbox", "").split(",")]
        if len(bbox) != 4:
            raise ValueError
    except ValueError:
        return JsonResponse({"error": "bbox must be minLon,minLat,maxLon,maxLat"}, status=400)
    area = Polygon.from_bbox(bbox)
    area.srid = 4326
    area.transform(27700)
    if area.area > 25_000_000:  # larger than about 5 km x 5 km: zoom in first
        return JsonResponse({"type": "FeatureCollection", "features": [], "tooLarge": True})
    rows = (InspireParcel.objects.filter(geometry__intersects=area)
            .annotate(gj=AsGeoJSON(Transform("geometry", 4326), precision=7)).values("inspire_id", "gj")[:3000])
    return JsonResponse({"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": json.loads(r["gj"]), "properties": {"inspireId": r["inspire_id"], "role": "inspire"}}
        for r in rows
    ]})


# ---------------------------------------------------------------- boundary from INSPIRE

def administrators_only(view):
    def wrapped(request, *args, **kwargs):
        if not is_administrator(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    wrapped.__name__, wrapped.__doc__ = view.__name__, view.__doc__
    return login_required(wrapped)


@login_required
@require_http_methods(["GET", "POST"])
def boundary_from_inspire(request, pk):
    obj = get_object_or_404(Property, pk=pk)
    if not can_edit(request.user, obj):
        raise PermissionDenied
    if obj.boundary:
        search = obj.boundary.buffer(5)
    elif obj.easting and obj.northing:
        search = Point(obj.easting, obj.northing, srid=27700).buffer(25)
    else:
        search = None
    parcels = []
    if search is not None:
        parcels = list(InspireParcel.objects.filter(geometry__intersects=search)[:50])
        for parcel in parcels:
            parcel.area_ha = round(parcel.geometry.area / 10000, 3)

    if request.method == "POST":
        chosen = [p for p in parcels if p.inspire_id in request.POST.getlist("parcel")]
        if not chosen:
            messages.error(request, _("Choose at least one parcel."))
        else:
            union = chosen[0].geometry
            for p in chosen[1:]:
                union = union.union(p.geometry)
            if union.geom_type == "Polygon":
                from django.contrib.gis.geos import MultiPolygon

                union = MultiPolygon(union, srid=27700)
            obj.boundary = union
            obj.boundary_source = "HM Land Registry INSPIRE " + ", ".join(p.inspire_id for p in chosen)
            if obj.property_type in (Property.PropertyType.SITE, Property.PropertyType.LAND, Property.PropertyType.ESTATE):
                from decimal import Decimal

                obj.site_area_ha = Decimal(union.area / 10000).quantize(Decimal("0.0001"))
            obj.save()
            messages.success(request, _("Boundary updated from %(n)s INSPIRE parcel(s).") % {"n": len(chosen)})
            return redirect(obj)
    return render(request, "properties/boundary_from_inspire.html", {
        "object": obj, "parcels": parcels, "has_location": search is not None,
        "inspire_count": InspireParcel.objects.count(), "map_config": map_config(),
    })


@administrators_only
@require_http_methods(["GET", "POST"])
def inspire_upload(request):
    if request.method == "POST" and request.FILES.get("file"):
        try:
            created, updated, skipped = import_uploaded_file(request.FILES["file"])
        except InspireImportError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, _("INSPIRE import finished: %(c)s parcels added, %(u)s updated, %(s)s skipped.")
                             % {"c": created, "u": updated, "s": skipped})
            return redirect("properties:inspire-upload")
    return render(request, "properties/inspire_upload.html", {"inspire_count": InspireParcel.objects.count()})


# ---------------------------------------------------------------- spreadsheet import

@login_required
def import_template(request):
    response = HttpResponse(
        importer.template_workbook(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="phaema-property-import-template.xlsx"'
    return response


IMPORT_DIR = "imports"


@administrators_only
@require_http_methods(["GET", "POST"])
def import_properties(request):
    ctx = {}
    if request.method == "POST" and "confirm" in request.POST:
        token = request.POST.get("token", "")
        stored = request.session.get("property_import", {})
        if stored.get("token") != token or not default_storage.exists(stored.get("path", "")):
            messages.error(request, _("That import has expired. Please upload the file again."))
            return redirect("properties:import")
        with default_storage.open(stored["path"], "rb") as fh:
            fh.name = stored["name"]
            rows = importer.read_rows(fh)
        result, prepared = importer.validate(rows)
        default_storage.delete(stored["path"])
        request.session.pop("property_import", None)
        if not result.ok:
            messages.error(request, _("The data changed since the preview. Please upload the file again."))
            return redirect("properties:import")
        importer.apply([(obj, parent) for (obj, parent), r in zip(prepared, result.rows) if r.action != "unchanged"])
        messages.success(request, _("Import complete: %(c)s properties added and %(u)s updated.")
                         % {"c": result.count("create"), "u": result.count("update")})
        return redirect("properties:list")

    if request.method == "POST" and request.FILES.get("file"):
        uploaded = request.FILES["file"]
        try:
            if uploaded.size > 10 * 1024 * 1024:
                raise ValidationError(_("The file must be smaller than 10 MB."))
            rows = importer.read_rows(uploaded)
            result, _prepared = importer.validate(rows)
        except ValidationError as exc:
            ctx["file_error"] = " ".join(exc.messages)
        else:
            ctx["result"] = result
            if result.ok:
                ext = os.path.splitext(uploaded.name)[1].lower()
                token = uuid.uuid4().hex
                uploaded.seek(0)
                path = default_storage.save(f"{IMPORT_DIR}/{token}{ext}", uploaded)
                request.session["property_import"] = {"token": token, "path": path, "name": uploaded.name}
                ctx["token"] = token
            ctx["filename"] = uploaded.name
    elif request.method == "POST":
        ctx["file_error"] = _("Choose a file to upload.")
    return render(request, "properties/import.html", ctx)
