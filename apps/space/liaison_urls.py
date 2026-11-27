# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import liaison_views

app_name = "occupier"
urlpatterns = [
    path("", liaison_views.home, name="home"),
    path("building/<int:pk>/", liaison_views.building, name="building"),
    path("building/<int:pk>/repair/", liaison_views.repair, name="repair"),
]
