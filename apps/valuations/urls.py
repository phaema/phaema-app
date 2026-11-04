# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "valuations"

urlpatterns = [
    path("", views.home, name="home"),
    path("property/<int:pk>/", views.property_valuations, name="property"),
    path("<int:pk>/", views.valuation_detail, name="valuation"),
    path("schedule/", views.schedule, name="schedule"),
    path("data-pack/", views.data_pack, name="data-pack"),
]
