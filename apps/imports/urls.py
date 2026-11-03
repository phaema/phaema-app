# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "imports"

urlpatterns = [
    path("", views.hub, name="hub"),
    path("<slug:key>/", views.upload, name="upload"),
    path("<slug:key>/template.xlsx", views.template, name="template"),
]
