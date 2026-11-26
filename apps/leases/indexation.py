# SPDX-License-Identifier: AGPL-3.0-or-later
"""Index-linked rent reviews: the new rent worked out from a price index, with any cap, collar and upwards-only rule.

The usual drafting, which PHAEMA follows:

    new rent = current rent × (index for the review month ÷ index for the base month)

where the review month is the month a set number of months before the review date (the lag in the lease), and the
base month is the month the current rent was based on (the last review, or the start of the lease). A cap and a
collar are given as a percentage a year, compounded over the years between the two months unless the lease says
otherwise. Upwards only means the rent never falls. The result is a proposal: the surveyor checks it against the
lease and records the outcome as usual.
"""
import csv
import io
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from apps.core.dates import add_months

log = logging.getLogger(__name__)
PENNY = Decimal("0.01")
MONTHS = {m: i for i, m in enumerate(
    ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"), start=1)}


def month_of(day):
    return day.replace(day=1)


def months_between(start, end):
    return (end.year - start.year) * 12 + end.month - start.month


@dataclass
class Calculation:
    """The working for one index-linked review. `problem` explains why no rent could be worked out."""

    lease: object
    review_date: date
    current_rent: Decimal
    series: object = None
    base_month: date = None
    review_month: date = None
    base_value: Decimal = None
    review_value: Decimal = None
    years: Decimal = None
    change_pct: Decimal = None
    indexed_rent: Decimal = None
    cap_rent: Decimal = None
    collar_rent: Decimal = None
    new_rent: Decimal = None
    applied: list = field(default_factory=list)  # which limits changed the rent: "cap", "collar", "upwards only"
    problem: str = ""

    @property
    def ok(self):
        return not self.problem and self.new_rent is not None

    @property
    def years_text(self):
        if self.years is None:
            return ""
        n = self.years.normalize()
        return "1 year" if n == 1 else f"{n:f} years"

    def summary(self):
        """One line for the review outcome notes and the rent schedule."""
        if not self.ok:
            return ""
        text = (f"{self.series.code} {self.review_month:%b %Y} {self.review_value} ÷ {self.base_month:%b %Y} "
                f"{self.base_value} = {self.change_pct:+.2f}%")
        if self.applied:
            text += f"; {', '.join(self.applied)} applied"
        return text


def _factor(pct, years, compounded):
    rate = Decimal(pct) / 100
    if compounded:
        return (1 + rate) ** int(years) * (1 + rate * (years - int(years)))  # whole years compound, part years pro rata
    return 1 + rate * years


def calculate(lease, review_date, current_rent=None):
    """Work out the index-linked rent for a review on `review_date`."""
    from .workflow import rent_on

    current = Decimal(current_rent if current_rent is not None else rent_on(lease, review_date))
    calc = Calculation(lease=lease, review_date=review_date, current_rent=current, series=lease.index_series)
    if not lease.is_index_linked:
        calc.problem = "The agreement's review basis is not index-linked."
        return calc
    if lease.index_series is None:
        calc.problem = "No index is set on the agreement. Add the index terms under Rent review on the agreement."
        return calc
    if lease.index_base_month is None:
        calc.problem = ("No base index month is set on the agreement. Add it under Rent review (usually the month "
                        "of the last review's figure, or the start of the lease).")
        return calc
    calc.base_month = month_of(lease.index_base_month)
    calc.review_month = month_of(add_months(review_date, -lease.index_lag_months))
    if calc.review_month <= calc.base_month:
        calc.problem = "The review month is not after the base month. Check the base month and the lag."
        return calc
    calc.base_value = lease.index_series.value_for(calc.base_month)
    calc.review_value = lease.index_series.value_for(calc.review_month)
    missing = [f"{m:%B %Y}" for m, v in ((calc.base_month, calc.base_value), (calc.review_month, calc.review_value))
               if v is None]
    if missing:
        calc.problem = (f"PHAEMA does not hold the {lease.index_series.code} figure for {' or '.join(missing)}. "
                        "It may not be published yet: figures come out about the middle of the next month.")
        return calc
    calc.years = Decimal(months_between(calc.base_month, calc.review_month)) / 12
    ratio = calc.review_value / calc.base_value
    calc.change_pct = ((ratio - 1) * 100).quantize(PENNY, ROUND_HALF_UP)
    calc.indexed_rent = (current * ratio).quantize(PENNY, ROUND_HALF_UP)
    rent = calc.indexed_rent
    if lease.index_cap_pct is not None:
        calc.cap_rent = (current * _factor(lease.index_cap_pct, calc.years, lease.index_compounded)).quantize(
            PENNY, ROUND_HALF_UP)
        if rent > calc.cap_rent:
            rent = calc.cap_rent
            calc.applied.append("cap")
    if lease.index_collar_pct is not None:
        calc.collar_rent = (current * _factor(lease.index_collar_pct, calc.years, lease.index_compounded)).quantize(
            PENNY, ROUND_HALF_UP)
        if rent < calc.collar_rent:
            rent = calc.collar_rent
            calc.applied.append("collar")
    if lease.index_upward_only and rent < current:
        rent = current
        calc.applied.append("upwards only")
    calc.new_rent = rent
    return calc


# ------------------------------------------------------------------ index figures

ONS_MONTH = re.compile(r"^(\d{4}) ([A-Z]{3})$")


def parse_figures(text):
    """Monthly figures from a CSV file: {first day of month: value}.

    Reads the file the Office for National Statistics publishes for a time series (rows such as "2026 JAN","135.6",
    with yearly and quarterly rows ignored), or a plain two-column file of month and value, where the month is
    written 2026-01, 2026-01-01, 01/2026 or Jan 2026."""
    found = {}
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 2:
            continue
        label, raw = row[0].strip().strip('"'), row[1].strip().replace(",", "")
        month = _month_label(label)
        if month is None:
            continue
        try:
            value = Decimal(raw)
        except ArithmeticError:
            continue
        if value > 0:
            found[month] = value
    return found


def _month_label(label):
    m = ONS_MONTH.match(label.upper())
    if m and m.group(2) in MONTHS:
        return date(int(m.group(1)), MONTHS[m.group(2)], 1)
    for pattern, order in ((r"^(\d{4})-(\d{1,2})(?:-\d{1,2})?$", "ym"), (r"^(\d{1,2})/(\d{4})$", "my"),
                           (r"^\d{1,2}/(\d{1,2})/(\d{4})$", "my")):
        m = re.match(pattern, label)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            year, month = (a, b) if order == "ym" else (b, a)
            if 1 <= month <= 12:
                return date(year, month, 1)
    m = re.match(r"^([A-Za-z]{3})[a-z]* (\d{4})$", label)
    if m and m.group(1).upper() in MONTHS:
        return date(int(m.group(2)), MONTHS[m.group(1).upper()], 1)
    return None


def save_figures(series, figures):
    """Add new figures and correct changed ones. Returns (added, changed)."""
    from .models import IndexFigure

    held = dict(series.figures.values_list("month", "value"))
    added = changed = 0
    for month, value in sorted(figures.items()):
        if month not in held:
            IndexFigure.objects.create(series=series, month=month, value=value)
            added += 1
        elif held[month] != value:
            IndexFigure.objects.filter(series=series, month=month).update(value=value)
            changed += 1
    return added, changed


def ons_url(series):
    return (f"https://www.ons.gov.uk/generator?format=csv&uri=/economy/inflationandpriceindices/timeseries/"
            f"{series.ons_series.lower()}/{(series.ons_dataset or 'mm23').lower()}")


def fetch_from_ons(series, timeout=20):
    """Download the series from the ONS website and save any new figures. Returns (added, changed)."""
    import urllib.request

    request = urllib.request.Request(ons_url(series), headers={"User-Agent": "PHAEMA (estate management)"})  # noqa: S310
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed https address
        text = response.read().decode("utf-8", "replace")
    figures = parse_figures(text)
    if not figures:
        raise ValueError("The ONS file had no monthly figures.")
    return save_figures(series, figures)


def update_all(today=None):
    """Fetch new figures for every series with an ONS ID whose latest figure is over a month old. Never raises."""
    from .models import IndexSeries

    today = today or date.today()
    added = 0
    for series in IndexSeries.objects.exclude(ons_series=""):
        latest = series.latest
        if latest and months_between(latest.month, month_of(today)) <= 1:
            continue  # the next figure is not due yet
        try:
            added += fetch_from_ons(series)[0]
        except Exception as err:  # a council server may not reach the internet: the figures can be uploaded instead
            log.warning("Could not fetch %s figures from the ONS: %s", series.code, err)
    return added
