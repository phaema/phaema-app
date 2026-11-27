# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "imports"

urlpatterns = [
    path("", views.hub, name="hub"),
    path("runs/", views.runs, name="runs"),
    path("runs/<int:pk>/", views.run_detail, name="run"),
    path("runs/<int:pk>/report.xlsx", views.run_report, name="run-report"),
    path("runs/<int:pk>/sign-off/", views.run_sign_off, name="run-sign-off"),
    path("<slug:key>/", views.upload, name="upload"),
    path("<slug:key>/template.xlsx", views.template, name="template"),
    path("<slug:key>/check.xlsx", views.check_report, name="check-report"),
]
