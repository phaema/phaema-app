# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views, visit_views

app_name = "cases"

urlpatterns = [
    path("", views.CaseListView.as_view(), name="list"),
    path("new/", views.case_new, name="new"),
    path("documents/<int:pk>/share/", views.document_share, name="document-share"),
    path("<int:pk>/", views.case_detail, name="detail"),
    path("<int:pk>/site-visit/", views.site_visit_sheet, name="site-visit"),
    path("<int:pk>/visits/start/", visit_views.visit_start, name="visit-start"),
    path("<int:pk>/visits/<int:visit_pk>/", visit_views.visit_page, name="visit"),
    path("<int:pk>/visits/<int:visit_pk>/record/", visit_views.visit_record, name="visit-record"),
    path("<int:pk>/visits/<int:visit_pk>/update/<int:answer_pk>/", visit_views.visit_update, name="visit-update"),
]
