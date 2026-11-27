# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "ledger"

urlpatterns = [
    path("", views.home, name="home"),
    path("runs/new/", views.run_new, name="run-new"),
    path("runs/<int:pk>/", views.run_detail, name="run"),
    path("runs/<int:pk>/email/", views.run_email, name="run-email"),
    path("accounts/<int:lease_pk>/", views.account, name="account"),
    path("charges/<int:charge_pk>/credit/", views.credit, name="credit"),
    path("arrears/", views.arrears, name="arrears"),
    path("credit-control/", views.credit_control, name="credit-control"),
    path("accounts/<int:lease_pk>/plan/", views.plan_new, name="plan-new"),
    path("plans/<int:pk>/cancel/", views.plan_cancel, name="plan-cancel"),
    path("accounts/<int:lease_pk>/interest/", views.raise_interest, name="interest"),
    path("receipts/", views.receipts, name="receipts"),
    path("exports/", views.exports, name="exports"),
    path("exports/<int:pk>/", views.export_download, name="export"),
]
