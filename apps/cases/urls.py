# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "cases"

urlpatterns = [
    path("", views.CaseListView.as_view(), name="list"),
    path("new/", views.case_new, name="new"),
    path("<int:pk>/", views.case_detail, name="detail"),
]
