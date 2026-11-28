# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import survey_views, views

app_name = "maintenance"

urlpatterns = [
    path("", views.home, name="home"),
    path("jobs/", views.JobListView.as_view(), name="jobs"),
    path("jobs/new/", views.job_new, name="job-new"),
    path("jobs/<int:pk>/", views.job_detail, name="job"),
    path("jobs/<int:pk>/order/", views.works_order, name="order"),
    path("reports/", views.reports, name="reports"),
    path("reports/<int:pk>/", views.report_detail, name="report"),
    path("planned/", views.planned, name="planned"),
    path("planned/<int:pk>/", views.planned_action, name="planned-action"),
    path("property/<int:pk>/", views.property_maintenance, name="property"),
    path("components/", views.components, name="components"),
    path("forecast/", views.forecast, name="forecast"),
    path("surveys/", survey_views.survey_list, name="surveys"),
    path("surveys/<int:pk>/", survey_views.survey_detail, name="survey"),
    path("surveys/items/<int:pk>/", survey_views.item_action, name="survey-item"),
    path("property/<int:pk>/surveys/new/", survey_views.survey_new, name="survey-new"),
    path("backlog/", survey_views.backlog, name="backlog"),
    path("contractors/", views.contractors, name="contractors"),
    path("contractors/<int:pk>/", views.contractor_detail, name="contractor"),
    path("contracts/", views.contracts, name="contracts"),
]
