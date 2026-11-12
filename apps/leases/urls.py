# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import event_views, views

app_name = "leases"

urlpatterns = [
    path("", views.LeaseListView.as_view(), name="list"),
    path("<int:pk>/", views.LeaseDetailView.as_view(), name="detail"),
    path("<int:pk>/files/", views.lease_files, name="files"),
    path("events/", event_views.EventListView.as_view(), name="events"),
    path("events/<int:pk>/", event_views.event_detail, name="event"),
    path("<int:lease_pk>/events/add/", event_views.event_add, name="event-add"),
    path("<int:lease_pk>/rent/add/", event_views.rent_step_add, name="rent-add"),
    path("rent/<int:pk>/delete/", event_views.rent_step_delete, name="rent-delete"),
    path("documents/", views.DocumentListView.as_view(), name="documents"),
    path("calendar/", event_views.calendar_settings, name="calendar"),
    path("parties/", views.PartyListView.as_view(), name="parties"),
    path("parties/<int:pk>/", views.PartyDetailView.as_view(), name="party"),
]
