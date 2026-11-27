# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "portal"

urlpatterns = [
    path("", views.home, name="home"),
    path("sign-in/", views.sign_in, name="sign-in"),
    path("sign-in/code/", views.code, name="code"),
    path("sign-out/", views.sign_out, name="sign-out"),
    path("agreements/<int:pk>/", views.agreement, name="agreement"),
    path("agreements/<int:pk>/contact/", views.contact, name="contact"),
    path("agreements/<int:pk>/repair/", views.repair, name="repair"),
    path("agreements/<int:pk>/request/", views.request_new, name="request-new"),
    path("agreements/<int:pk>/service-charges/<int:year_pk>/budget/", views.sc_budget, name="sc-budget"),
    path("agreements/<int:pk>/service-charges/<int:year_pk>/statement/", views.sc_statement, name="sc-statement"),
    path("agreements/<int:pk>/service-charges/<int:year_pk>/query/", views.sc_query, name="sc-query"),
    path("agreements/<int:pk>/certificates/<int:req_pk>/", views.certificate, name="certificate"),
    path("agreements/<int:pk>/messages/", views.messages_page, name="messages"),
    path("agreements/<int:pk>/insurance/", views.insurance, name="insurance"),
    path("requests/<int:pk>/", views.request_detail, name="request"),
    path("requests/<int:pk>/documents/<int:doc>/", views.request_document, name="request-document"),
    path("documents/<int:pk>/", views.document, name="document"),
]
