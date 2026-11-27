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
    path("documents/<int:pk>/", views.document, name="document"),
]
