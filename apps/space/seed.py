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

# (name, notional, from maintenance jobs, active, what to include)
STARTING_COST_LINES = [
    ("Rent paid", False, False, True, "Rent the council pays where it leases the building in."),
    ("Business rates", False, False, True, "Rates payable for the year."),
    ("Energy", False, False, True, "Electricity, gas and other fuel."),
    ("Water", False, False, True, "Water and sewerage."),
    ("Cleaning", False, False, True, ""),
    ("Security", False, False, True, "Guarding, alarms and CCTV monitoring."),
    ("Repairs and maintenance", False, True, True,
     "Reactive and planned maintenance. Left blank, PHAEMA uses completed maintenance jobs at the council's cost."),
    ("Insurance", False, False, True, ""),
    ("Facilities management contracts", False, False, True, "Total FM, catering, waste and other contracts."),
    ("Capital charges", False, False, False, "Only if the council charges services for capital. Off to start with."),
    ("Notional rent", True, False, True,
     "For a freehold building: what it would cost to rent, usually the valuer's estimate of market rent."),
]


def ensure_cost_lines():
    from .models import CostLine

    if CostLine.objects.exists():
        return
    for order, (name, notional, from_jobs, active, help_text) in enumerate(STARTING_COST_LINES):
        CostLine.objects.create(name=name, notional=notional, from_jobs=from_jobs, active=active, help=help_text,
                                order=order)
