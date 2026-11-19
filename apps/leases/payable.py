# SPDX-License-Identifier: AGPL-3.0-or-later
"""Rents payable: what the council pays for property it holds on leases and licences (council as tenant).

Built from the agreements themselves (direction "in"): the rent in force, how often it is paid, the payments due in
the next twelve months (none before a rent-free period ends), and the dates that could change it: reviews, breaks
and expiry. PHAEMA does not pay these rents; finance does. This is the view an estates team needs to check what is
due and plan ahead.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from apps.core.dates import add_months

from .models import Lease
from .workflow import LIVE, PERIODS, payment_dates, rent_on

MONTHS_AHEAD = 12


@dataclass
class Row:
    lease: Lease
    annual_rent: Decimal
    per_payment: Decimal | None
    payments: list = field(default_factory=list)      # (date, amount) in the next twelve months
    next_break: date | None = None

    @property
    def next_payment(self):
        return self.payments[0] if self.payments else None

    @property
    def year_total(self):
        return sum((amount for _d, amount in self.payments), Decimal("0"))


@dataclass
class Payable:
    today: date
    rows: list
    months: list                                       # first day of each of the next twelve months
    by_month: list                                     # total due in each of those months

    @property
    def annual_total(self):
        return sum((r.annual_rent for r in self.rows), Decimal("0"))

    @property
    def year_total(self):
        return sum(self.by_month, Decimal("0"))


def gather(today=None, leases=None):
    today = today or date.today()
    first = today.replace(day=1)
    end = add_months(first, MONTHS_AHEAD)    # this month and the next eleven, so the rows and months agree
    qs = leases if leases is not None else Lease.objects.all()
    qs = (qs.filter(direction=Lease.Direction.IN, status__in=LIVE)
          .select_related("counterparty").prefetch_related("properties", "breaks", "rent_schedule")
          .order_by("reference"))
    months = [add_months(first, n) for n in range(MONTHS_AHEAD)]
    by_month = [Decimal("0")] * MONTHS_AHEAD
    rows = []
    for lease in qs:
        periods = PERIODS.get(lease.rent_frequency)
        rent = rent_on(lease, today)
        start = today
        if lease.rent_free_until and lease.rent_free_until >= today:
            start = lease.rent_free_until + timedelta(days=1)
        payments = []
        if periods:
            for day in payment_dates(lease, start, periods * 2 + 1):
                if day >= end:
                    break
                payments.append((day, (rent_on(lease, day) / periods).quantize(Decimal("0.01"))))
        for day, amount in payments:
            index = (day.year - first.year) * 12 + day.month - first.month
            if 0 <= index < MONTHS_AHEAD:
                by_month[index] += amount
        breaks = sorted(b.break_date for b in lease.breaks.all() if b.break_date >= today)
        rows.append(Row(lease=lease, annual_rent=rent,
                        per_payment=(rent / periods).quantize(Decimal("0.01")) if periods else None,
                        payments=payments, next_break=breaks[0] if breaks else None))
    return Payable(today=today, rows=rows, months=months, by_month=by_month)


def to_xlsx(payable):
    import io

    from openpyxl import Workbook
    from openpyxl.styles import Font

    bold = Font(bold=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "Rents payable"
    ws.append([f"Rents payable: prepared {payable.today:%d %B %Y}"])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([])
    ws.append(["Agreement", "Landlord", "Premises", "Annual rent (£)", "Paid", "Each payment (£)", "Next payment",
               "Due in next 12 months (£)", "Rent free until", "Next review", "Next break", "Expiry"])
    for c in ws[ws.max_row]:
        c.font = bold
    for r in payable.rows:
        lease = r.lease
        ws.append([lease.reference, lease.counterparty.name,
                   lease.premises_description or "; ".join(p.name for p in lease.properties.all()),
                   float(r.annual_rent), lease.get_rent_frequency_display(),
                   float(r.per_payment) if r.per_payment is not None else None,
                   r.next_payment[0] if r.next_payment else None, float(r.year_total),
                   lease.rent_free_until, lease.next_review_date, r.next_break, lease.term_end])
        for col in (4, 6, 8):
            ws.cell(ws.max_row, col).number_format = "£#,##0.00"
        for col in (7, 9, 10, 11, 12):
            ws.cell(ws.max_row, col).number_format = "d mmm yyyy"
    ws.append(["Total", "", "", float(payable.annual_total), "", "", "", float(payable.year_total)])
    for c in ws[ws.max_row]:
        c.font = bold
    for col in (4, 8):
        ws.cell(ws.max_row, col).number_format = "£#,##0.00"
    for col, width in zip("ABCDEFGHIJKL", (12, 30, 40, 16, 34, 16, 14, 18, 14, 14, 14, 14)):
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "A4"
    months = wb.create_sheet("By month")
    months.append(["Month", "Due (£)"])
    for c in months[1]:
        c.font = bold
    for month, amount in zip(payable.months, payable.by_month):
        months.append([f"{month:%B %Y}", float(amount)])
        months.cell(months.max_row, 2).number_format = "£#,##0.00"
    months.append(["Total", float(payable.year_total)])
    months.cell(months.max_row, 2).number_format = "£#,##0.00"
    months.column_dimensions["A"].width = 18
    months.column_dimensions["B"].width = 16
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
