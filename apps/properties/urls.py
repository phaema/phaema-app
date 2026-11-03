# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "properties"

urlpatterns = [
    path("", views.PropertyListView.as_view(), name="list"),
    path("<int:pk>/", views.PropertyDetailView.as_view(), name="detail"),
    path("titles/<int:pk>/", views.TitleDetailView.as_view(), name="title"),
]
