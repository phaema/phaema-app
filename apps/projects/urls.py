# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "projects"

urlpatterns = [
    path("", views.ProjectListView.as_view(), name="list"),
    path("new/", views.project_new, name="new"),
    path("<int:pk>/", views.project_detail, name="detail"),
    path("<int:pk>/edit/", views.project_edit, name="edit"),
    path("<int:pk>/map.geojson", views.project_geojson, name="geojson"),
    path("<int:pk>/files/<str:kind>/<int:item>/", views.project_file, name="file"),
]
