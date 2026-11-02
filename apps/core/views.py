# SPDX-License-Identifier: AGPL-3.0-or-later
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import render

from apps.properties.models import Property

from .models import AuditEntry


@login_required
def dashboard(request):
    by_type = (
        Property.objects.values("property_type").annotate(n=Count("id")).order_by("property_type")
    )
    labels = dict(Property.PropertyType.choices)
    context = {
        "property_count": Property.objects.count(),
        "vacant_count": Property.objects.filter(occupation=Property.Occupation.VACANT).count(),
        "by_type": [(labels.get(r["property_type"], r["property_type"]), r["n"]) for r in by_type],
        "recent_changes": AuditEntry.objects.select_related("user", "content_type")[:10],
    }
    return render(request, "core/dashboard.html", context)


def health(request):
    """Used by the container health check."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return JsonResponse({"status": "ok"})
