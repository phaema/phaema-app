# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "documents"

urlpatterns = [
    path("", views.library, name="library"),
    path("<slug:code>/", views.template_detail, name="template"),
    path("<slug:code>/create/", views.create, name="create"),
]
