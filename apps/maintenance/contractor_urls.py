# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import contractor_portal as views

app_name = "contractor"

urlpatterns = [
    path("", views.home, name="home"),
    path("sign-in/", views.sign_in, name="sign-in"),
    path("sign-in/code/", views.code, name="code"),
    path("sign-out/", views.sign_out, name="sign-out"),
    path("jobs/<int:pk>/", views.job_page, name="job"),
    path("jobs/<int:pk>/photos/<int:update_pk>/", views.update_photo, name="photo"),
    path("jobs/<int:pk>/documents/<int:doc_pk>/", views.document, name="document"),
]
