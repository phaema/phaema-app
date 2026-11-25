# SPDX-License-Identifier: AGPL-3.0-or-later
"""The price indices used for index-linked rent reviews: the figures held, and adding new ones."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _

from apps.core.roles import is_administrator

from . import indexation
from .models import IndexSeries

MAX_UPLOAD = 2 * 1024 * 1024


@login_required
def index_figures(request):
    series = list(IndexSeries.objects.all())
    if request.method == "POST":
        if not is_administrator(request.user):
            raise PermissionDenied
        chosen = get_object_or_404(IndexSeries, pk=request.POST.get("series"))
        if "fetch" in request.POST:
            if not chosen.ons_series:
                messages.error(request, _("%(code)s has no ONS series ID, so its figures must be uploaded.")
                               % {"code": chosen.code})
                return redirect("leases:index-figures")
            try:
                added, changed = indexation.fetch_from_ons(chosen)
            except Exception:  # noqa: BLE001 (the reason is logged; the page says what to do instead)
                messages.error(request, _("PHAEMA could not fetch the figures from the ONS website. Download the "
                                          "CSV file from the ONS website and upload it here instead."))
                return redirect("leases:index-figures")
        else:
            upload = request.FILES.get("file")
            if upload is None or upload.size > MAX_UPLOAD:
                messages.error(request, _("Choose a CSV file of up to 2 MB."))
                return redirect("leases:index-figures")
            figures = indexation.parse_figures(upload.read().decode("utf-8-sig", "replace"))
            if not figures:
                messages.error(request, _("No monthly figures were found in the file. Use the ONS CSV download, or "
                                          "two columns: month (e.g. 2026-01) and value."))
                return redirect("leases:index-figures")
            added, changed = indexation.save_figures(chosen, figures)
        messages.success(request, _("%(code)s: %(added)s figures added, %(changed)s corrected.")
                         % {"code": chosen.code, "added": added, "changed": changed})
        return redirect("leases:index-figures")
    rows = [(s, s.latest, s.figures.order_by("-month")[:13]) for s in series]
    return render(request, "leases/index_figures.html", {
        "rows": rows, "series": series, "can_change": is_administrator(request.user)})
