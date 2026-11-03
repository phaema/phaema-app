# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "help"

urlpatterns = [
    path("", views.index, name="index"),
    path("search/", views.search, name="search"),
    path("<slug:slug>/", views.page, name="page"),
    path("<slug:slug>", views.page),  # "Help with this page" links are built without the final slash
]
