# SPDX-License-Identifier: AGPL-3.0-or-later
"""Starting list of public use measures. Councils change it in Manage data; a measure in use cannot be deleted."""

STARTING_MEASURES = [
    ("Visits", "visits", "People coming through the door (footfall), from a door counter or a count."),
    ("Bookings", "bookings", "Bookings of rooms, halls or facilities."),
    ("Hours used", "hours", "Hours the building or room was booked or in use; give the hours open as \"out of\"."),
    ("Registered members", "members", "People registered, for example library members or gym members."),
]


def ensure_measures():
    from .models import UseMeasure

    if UseMeasure.objects.exists():
        return
    for order, (name, unit, help_text) in enumerate(STARTING_MEASURES):
        UseMeasure.objects.create(name=name, unit=unit, help=help_text, order=order)
