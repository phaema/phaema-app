# SPDX-License-Identifier: AGPL-3.0-or-later
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from apps.core import views as core_views
from apps.leases import event_views
from apps.leases.api import LeaseViewSet, PartyViewSet
from apps.properties import opendata
from apps.properties.api import PropertyViewSet, TitleViewSet

router = DefaultRouter()
router.register("properties", PropertyViewSet)
router.register("titles", TitleViewSet)
router.register("leases", LeaseViewSet)
router.register("parties", PartyViewSet)

admin.site.site_header = "PHAEMA administration"
admin.site.site_title = "PHAEMA"

urlpatterns = [
    path("", core_views.dashboard, name="dashboard"),
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("health/", core_views.health, name="health"),
    path("changes/", core_views.change_list, name="changes"),
    path("changes/<int:pk>/", core_views.change_detail, name="change"),
    path("text-size/<str:size>/", core_views.set_text_size, name="text-size"),
    path("theme/<str:theme>/", core_views.set_theme, name="theme"),
    path("files/<path:path>", core_views.protected_file, name="file"),
    path("properties/", include("apps.properties.urls")),
    path("leases/", include("apps.leases.urls")),
    path("reports/", include("apps.reports.urls")),
    path("import/", include("apps.imports.urls")),
    path("help/", include("apps.help.urls")),
    path("rents/", include("apps.ledger.urls")),
    path("service-charges/", include("apps.servicecharges.urls")),
    path("maintenance/", include("apps.maintenance.urls")),
    path("compliance/", include("apps.compliance.urls")),
    path("open-data/", opendata.index, name="open-data"),
    path("open-data/<slug:slug>.<str:fmt>", opendata.dataset, name="open-data-file"),
    path("cases/", include("apps.cases.urls")),
    path("calendar/<str:token>.ics", event_views.calendar_feed, name="calendar-feed"),
    path("admin/", admin.site.urls),
    path("api/", include(router.urls)),
    path("api/schema/", SpectacularAPIView.as_view(), name="api-schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="api-schema"), name="api-docs"),
]
