# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "space"

urlpatterns = [
    path("", views.home, name="home"),
    path("building/<int:pk>/", views.building, name="building"),
    path("occupiers/", views.occupiers, name="occupiers"),
    path("occupiers/<int:pk>/", views.occupier, name="occupier"),
]
