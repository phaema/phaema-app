# SPDX-License-Identifier: AGPL-3.0-or-later
from calendar import monthrange
from datetime import date


def add_months(d, months):
    """The same day of the month, months later (or earlier), clamped to the month's last day."""
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    return date(year, month, min(d.day, monthrange(year, month)[1]))
