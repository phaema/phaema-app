# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sortable table headings that keep the page's current filters."""


def sortable(request, columns, default):
    """Work out the ordering and the column headings for a sortable table.

    columns: {key: (heading, [orderings], numeric)}. Returns (ordering, headings).
    """
    raw = request.GET.get("sort", default)
    descending = raw.startswith("-")
    key = raw.lstrip("-")
    if key not in columns:
        key, descending = default.lstrip("-"), default.startswith("-")
    ordering = [f"-{o}" if descending else o for o in columns[key][1]]

    base = request.GET.copy()
    base.pop("page", None)
    headings = []
    for col, (label, _orderings, numeric) in columns.items():
        params = base.copy()
        active = col == key
        params["sort"] = f"-{col}" if active and not descending else col
        headings.append({
            "label": label,
            "url": "?" + params.urlencode(),
            "aria_sort": ("descending" if descending else "ascending") if active else "none",
            "numeric": numeric,
        })
    return ordering, headings
