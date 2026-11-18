# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "strategy"

urlpatterns = [
    path("", views.home, name="home"),
    path("objectives/<int:pk>/", views.objective, name="objective"),
    path("report/", views.board_report, name="report"),
]
