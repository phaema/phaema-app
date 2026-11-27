# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import liaison_views

app_name = "occupier"
urlpatterns = [
    path("", liaison_views.home, name="home"),
    path("building/<int:pk>/", liaison_views.building, name="building"),
    path("building/<int:pk>/repair/", liaison_views.repair, name="repair"),
    path("building/<int:pk>/request/", liaison_views.request_new, name="request-new"),
    path("requests/<int:pk>/", liaison_views.request_detail, name="request"),
    path("requests/<int:pk>/documents/<int:doc>/", liaison_views.request_document, name="request-document"),
]
