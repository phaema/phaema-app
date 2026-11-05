# SPDX-License-Identifier: AGPL-3.0-or-later
"""Budget figures for a project: by line and by financial year, with costs and income kept apart."""
from collections import OrderedDict
from dataclasses import dataclass, field
from decimal import Decimal

from .models import BudgetLine, financial_year_label

ZERO = Decimal("0")


@dataclass
class Totals:
    approved: Decimal = ZERO
    forecast: Decimal = ZERO
    actual: Decimal = ZERO

    def add(self, year):
        self.approved += year.approved
        self.forecast += year.forecast
        self.actual += year.actual

    @property
    def variance(self):
        """Forecast over (positive) or under (negative) the approved budget."""
        return self.forecast - self.approved


@dataclass
class LineSummary:
    line: BudgetLine
    years: list
    totals: Totals = field(default_factory=Totals)


def summary(project):
    """Lines with their years and totals; a table by financial year; and overall cost and income totals."""
    lines, by_year = [], OrderedDict()
    cost, income = Totals(), Totals()
    for line in project.budget_lines.prefetch_related("years"):
        item = LineSummary(line, list(line.years.all()))
        for y in item.years:
            item.totals.add(y)
            if not line.is_income:
                by_year.setdefault(y.year, Totals()).add(y)
        for y in item.years:
            (income if line.is_income else cost).add(y)
        lines.append(item)
    years = [(financial_year_label(y), t) for y, t in sorted(by_year.items())]
    capital = Totals()
    for item in lines:
        if item.line.funding == BudgetLine.Funding.CAPITAL and not item.line.is_income:
            for y in item.years:
                capital.add(y)
    return {"lines": lines, "years": years, "cost": cost, "income": income, "capital": capital,
            "net_forecast": cost.forecast - income.forecast}
