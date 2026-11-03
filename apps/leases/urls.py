# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "leases"

urlpatterns = [
    path("", views.LeaseListView.as_view(), name="list"),
    path("<int:pk>/", views.LeaseDetailView.as_view(), name="detail"),
    path("parties/<int:pk>/", views.PartyDetailView.as_view(), name="party"),
]
