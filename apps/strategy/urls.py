# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import health_views, views

app_name = "strategy"

urlpatterns = [
    path("", views.home, name="home"),
    path("objectives/<int:pk>/", views.objective, name="objective"),
    path("report/", views.board_report, name="report"),
    path("pipeline/", views.pipeline_report, name="pipeline"),
    path("health/", health_views.health_list, name="health-list"),
    path("health/<int:pk>/", health_views.health_check, name="health"),
    path("health/<int:pk>/report/", health_views.health_report, name="health-report"),
]
