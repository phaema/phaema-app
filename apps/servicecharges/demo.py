# SPDX-License-Identifier: AGPL-3.0-or-later
"""Demonstration service charges: Riverside Industrial Estate's shared estate services, with a year
that has ended and is ready to reconcile, and the current year part way through."""
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction

from apps.core.dates import add_months
from apps.core.models import ModuleSettings
from apps.leases.models import Lease
from apps.properties.models import Property

from .models import BudgetLine, CostHeading, Expenditure, Schedule, ScheduleMember, ScheduleYear, ensure_headings

NAME = "Riverside Industrial Estate services"
BUDGET = {"MAN": 3500, "GRN": 9000, "ROAD": 6500, "SEC": 12000, "WASTE": 4000, "INS": 3000, "REP": 5000}
SUPPLIERS = {"MAN": "Exampleton Council estates team", "GRN": "Example Grounds Ltd", "ROAD": "Exampleton Highways Services",
             "SEC": "Example Security Patrols Ltd", "WASTE": "Example Waste Ltd", "INS": "Example Mutual Insurance",
             "REP": "Example Building Maintenance Ltd"}
SPEND_FACTOR = {"MAN": 1, "GRN": 1.04, "ROAD": 1.22, "SEC": 0.97, "WASTE": 1.08, "INS": 1, "REP": 1.31}
MEMBERS = ["DL-0001", "DL-0002", "DL-0003", "DL-0004", "DL-0005", "DL-0006"]
CAPS = {"DL-0005": Decimal("2900.00")}  # a capped lease, to show the council bearing the excess


def _year_start(today):
    return date(today.year if today.month >= 4 else today.year - 1, 4, 1)


@transaction.atomic
def setup(today=None):
    today = today or date.today()
    ensure_headings()
    modules = ModuleSettings.load()
    if not modules.service_charges_enabled:
        modules.service_charges_enabled = True
        modules.service_charge_income_code = modules.service_charge_income_code or "EST-1000-9200"
        modules.save()
    estate = Property.objects.filter(reference="DM-E01").first()
    if estate is None or Schedule.objects.filter(name=NAME).exists():
        return Schedule.objects.filter(name=NAME).first()
    schedule = Schedule.objects.create(
        name=NAME, basis=Schedule.Basis.AREA,
        description="Estate roads, lighting, landscaping, security patrols and waste for the units on the estate. "
                    "Fictional demonstration data.")
    schedule.properties.add(estate)
    for ref in MEMBERS:
        lease = Lease.objects.filter(reference=ref).first()
        if lease:
            ScheduleMember.objects.create(schedule=schedule, lease=lease, annual_cap=CAPS.get(ref))
    headings = {h.code: h for h in CostHeading.objects.all()}
    current = _year_start(today)
    for start, growth in ((date(current.year - 1, 4, 1), Decimal("1")), (current, Decimal("1.04"))):
        end = date(start.year + 1, 3, 31)
        year = ScheduleYear.objects.create(
            schedule=schedule, start=start, end=end, status=ScheduleYear.Status.APPROVED,
            budget_approved_on=start - timedelta(days=50), budget_issued_on=start - timedelta(days=40),
            budget_commentary="Security patrols re-tendered last year; landscaping and waste contracts rise with "
                              "inflation. Repairs allow for pothole repairs to the estate road.")
        for code, amount in BUDGET.items():
            BudgetLine.objects.create(year=year, heading=headings[code], amount=(Decimal(amount) * growth).quantize(
                Decimal("1")))
        last = min(end, today - timedelta(days=1))
        month = start
        n = 0
        while month <= last:
            for code, amount in BUDGET.items():
                if code in ("INS", "MAN") and month != start:
                    continue  # paid once a year
                yearly = Decimal(amount) * growth * Decimal(str(SPEND_FACTOR[code]))
                value = yearly if code in ("INS", "MAN") else yearly / 12
                n += 1
                Expenditure.objects.create(
                    year=year, heading=headings[code], spent_on=month + timedelta(days=14),
                    supplier=SUPPLIERS[code], description=f"{headings[code].name}, {month:%B %Y}",
                    invoice_reference=f"DEMO-SC-{start:%y}-{n:04d}", amount=value.quantize(Decimal("0.01")))
            month = add_months(month, 1)
        if start < current:  # last year: interest earned, an insurance commission rebate, and an improvement
            for code, desc, amount, kind, recoverable in [
                    ("INC", "Interest on the service charge account", "185.40", "income", True),
                    ("INC", "Insurance commission returned to the service charge", "240.00", "income", True),
                    ("ROAD", "LED street lighting upgrade (improvement, not recoverable)", "3800.00", "cost", False)]:
                n += 1
                Expenditure.objects.create(year=year, heading=headings[code], spent_on=end - timedelta(days=20),
                                           description=desc, invoice_reference=f"DEMO-SC-{start:%y}-{n:04d}",
                                           amount=Decimal(amount), kind=kind, recoverable=recoverable)
    return schedule


def remove():
    Schedule.objects.filter(name=NAME).delete()
