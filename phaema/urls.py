# SPDX-License-Identifier: AGPL-3.0-or-later
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from apps.core import views as core_views
from apps.properties.api import PropertyViewSet, TitleViewSet

router = DefaultRouter()
router.register("properties", PropertyViewSet)
router.register("titles", TitleViewSet)

admin.site.site_header = "PHAEMA administration"
admin.site.site_title = "PHAEMA"

urlpatterns = [
    path("", core_views.dashboard, name="dashboard"),
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("health/", core_views.health, name="health"),
    path("properties/", include("apps.properties.urls")),
    path("admin/", admin.site.urls),
    path("api/", include(router.urls)),
    path("api/schema/", SpectacularAPIView.as_view(), name="api-schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="api-schema"), name="api-docs"),
]
