# SPDX-License-Identifier: AGPL-3.0-or-later
from . import datasets, export


class ExportMixin:
    """Add ?format=xlsx or ?format=csv to a list page to download the whole filtered list."""

    export_dataset = None
    export_title = "PHAEMA export"

    def get(self, request, *args, **kwargs):
        if request.GET.get("format") in ("xlsx", "csv"):
            ds = datasets.get(self.export_dataset)
            return export.download(request, self.export_title, ds, self.get_queryset())
        return super().get(request, *args, **kwargs)
