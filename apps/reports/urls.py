# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("", views.report_list, name="list"),
    path("new/", views.report_new, name="new"),
    path("<int:pk>/", views.report_run, name="run"),
    path("<int:pk>/edit/", views.report_edit, name="edit"),
    path("<int:pk>/copy/", views.report_copy, name="copy"),
    path("<int:pk>/delete/", views.report_delete, name="delete"),
]
