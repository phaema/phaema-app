# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "compliance"

urlpatterns = [
    path("", views.home, name="home"),
    path("property/<int:pk>/", views.property_compliance, name="property"),
]
