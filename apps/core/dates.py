# SPDX-License-Identifier: AGPL-3.0-or-later
from calendar import monthrange
from datetime import date


def add_months(d, months):
    """The same day of the month, months later (or earlier), clamped to the month's last day."""
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    return date(year, month, min(d.day, monthrange(year, month)[1]))


# Bank holidays in England and Wales (gov.uk), used for working-day targets.
BANK_HOLIDAYS = {
    date(2025, 1, 1), date(2025, 4, 18), date(2025, 4, 21), date(2025, 5, 5), date(2025, 5, 26), date(2025, 8, 25),
    date(2025, 12, 25), date(2025, 12, 26),
    date(2026, 1, 1), date(2026, 4, 3), date(2026, 4, 6), date(2026, 5, 4), date(2026, 5, 25), date(2026, 8, 31),
    date(2026, 12, 25), date(2026, 12, 28),
    date(2027, 1, 1), date(2027, 3, 26), date(2027, 3, 29), date(2027, 5, 3), date(2027, 5, 31), date(2027, 8, 30),
    date(2027, 12, 27), date(2027, 12, 28),
    date(2028, 1, 3), date(2028, 4, 14), date(2028, 4, 17), date(2028, 5, 1), date(2028, 5, 29), date(2028, 8, 28),
    date(2028, 12, 25), date(2028, 12, 26),
}


def is_working_day(day):
    return day.weekday() < 5 and day not in BANK_HOLIDAYS


def add_working_days(start, days):
    """The date `days` working days after `start` (weekends and bank holidays skipped)."""
    from datetime import timedelta

    current, left = start, days
    while left > 0:
        current += timedelta(days=1)
        if is_working_day(current):
            left -= 1
    return current
