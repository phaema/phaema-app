# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "properties"

urlpatterns = [
    path("", views.PropertyListView.as_view(), name="list"),
    path("map/", views.register_map, name="map"),
    path("map.geojson", views.register_geojson, name="geojson"),
    path("inspire.geojson", views.inspire_geojson, name="inspire-geojson"),
    path("inspire/import/", views.inspire_upload, name="inspire-upload"),
    path("import/", views.import_properties, name="import"),
    path("import/template.xlsx", views.import_template, name="import-template"),
    path("<int:pk>/", views.PropertyDetailView.as_view(), name="detail"),
    path("<int:pk>/report/", views.property_report, name="report"),
    path("<int:pk>/map.geojson", views.property_geojson, name="detail-geojson"),
    path("<int:pk>/boundary/", views.boundary_from_inspire, name="boundary"),
    path("titles/<int:pk>/", views.TitleDetailView.as_view(), name="title"),
]
