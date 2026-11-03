# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "ledger"

urlpatterns = [
    path("", views.home, name="home"),
    path("runs/new/", views.run_new, name="run-new"),
    path("runs/<int:pk>/", views.run_detail, name="run"),
    path("accounts/<int:lease_pk>/", views.account, name="account"),
    path("charges/<int:charge_pk>/credit/", views.credit, name="credit"),
    path("arrears/", views.arrears, name="arrears"),
    path("receipts/", views.receipts, name="receipts"),
    path("exports/", views.exports, name="exports"),
    path("exports/<int:pk>/", views.export_download, name="export"),
]
