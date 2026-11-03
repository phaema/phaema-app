# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "servicecharges"

urlpatterns = [
    path("", views.schedule_list, name="list"),
    path("schedules/<int:pk>/", views.schedule_detail, name="schedule"),
    path("years/<int:pk>/", views.year_detail, name="year"),
    path("years/<int:pk>/approve/", views.year_approve, name="approve"),
    path("years/<int:pk>/reconcile/", views.reconcile, name="reconcile"),
    path("years/<int:pk>/statement/<int:member_pk>/", views.statement, name="statement"),
]
