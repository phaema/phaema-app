# SPDX-License-Identifier: AGPL-3.0-or-later
"""The IFRS 16 data pack: what finance needs from estates to account for the leases the council holds.

Since 1 April 2024 the Code of Practice on Local Authority Accounting applies IFRS 16 Leases, so most leases where
the council is the tenant go on the balance sheet as a right-of-use asset and a lease liability. Finance does the
accounting (discounting, depreciation, interest); this pack gives it the lease facts, every future payment and the
year's changes, for one financial year (1 April to 31 March), as an Excel workbook:

    Leases     one row per agreement the council holds, with its term, the IFRS 16 lease end, options, rent,
               review basis, treatment, whether the rent is nil or nominal, and undiscounted payment totals
    Payments   every payment from the start of the year to the end of the IFRS 16 lease term
    Changes    what changed during the year: new and ended leases, rent changes, and changes to the term
    Notes      how the pack is put together and what finance must add (the discount rate)

Payments are worked out as on Rents payable: in advance, on the agreement's payment dates, at the rent in force on
each date from the rent schedule, none before a rent-free period ends. Part periods are not apportioned.
Index-linked rents are shown at the rent in force now: under IFRS 16 they are remeasured when the index changes the
payments, which the next pack shows as a change.
"""
import copy
import io
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from apps.core.dates import add_months

from .models import Lease
from .workflow import PERIODS, payment_dates, rent_on

NOMINAL = Decimal("100")  # a rent at or below this a year is treated as nominal (a peppercorn)
PENNY = Decimal("0.01")
TERM_FIELDS = {"term_start": "Term start", "term_end": "Contractual expiry", "actual_end": "Date ended",
               "status": "Status", "ifrs16_lease_end": "IFRS 16 lease term ends",
               "ifrs16_treatment": "IFRS 16 treatment", "rent_frequency": "Rent payable",
               "rent_free_until": "Rent-free until", "direction": "Direction"}


def year_bounds(year):
    """The financial year starting 1 April `year`: (1 April, 31 March)."""
    return date(year, 4, 1), date(year + 1, 3, 31)


def current_year(today=None):
    today = today or date.today()
    return today.year if today.month >= 4 else today.year - 1


def year_label(year):
    return f"{year}/{str(year + 1)[-2:]}"


@dataclass
class LeaseRow:
    lease: Lease
    lease_end: date | None
    lease_end_source: str
    rent_now: Decimal
    nominal: bool
    payments: list = field(default_factory=list)  # (date, amount) from the start of the year to the lease end
    problems: list = field(default_factory=list)

    def total_from(self, day):
        return sum((amount for when, amount in self.payments if when >= day), Decimal("0"))

    def months_left(self, day):
        if not self.lease_end or self.lease_end < day:
            return 0
        return (self.lease_end.year - day.year) * 12 + self.lease_end.month - day.month


@dataclass
class Change:
    lease: Lease
    when: date
    what: str
    detail: str


@dataclass
class Pack:
    year: int
    start: date
    end: date
    rows: list
    changes: list


def lease_end(lease):
    """(the end of the lease term for IFRS 16, where it comes from)."""
    if lease.ifrs16_lease_end:
        return lease.ifrs16_lease_end, "IFRS 16 lease end set on the agreement"
    if lease.actual_end:
        return lease.actual_end, "Date ended"
    if lease.term_end:
        return lease.term_end, "Contractual expiry"
    return None, "No end date"


def payments(lease, start, end):
    """Every payment due from `start` to `end`, at the rent in force on each date."""
    periods = PERIODS.get(lease.rent_frequency)
    if not periods or end is None or end < start:
        return []
    first = start
    if lease.rent_free_until and lease.rent_free_until >= first:
        first = lease.rent_free_until + timedelta(days=1)
    shadow = copy.copy(lease)  # payment_dates stops at the contractual end; the IFRS 16 term may run past it
    shadow.term_end, shadow.actual_end, shadow.status = end, None, Lease.Status.CURRENT
    years = (end.year - first.year) + 2
    out = []
    for day in payment_dates(shadow, first, periods * years):
        if day > end:
            break
        out.append((day, (rent_on(lease, day) / periods).quantize(PENNY)))
    return out


def held_leases(start, end):
    """Agreements the council holds that were in force at some point in the year."""
    from django.db.models import Q

    return (Lease.objects.filter(direction=Lease.Direction.IN, term_start__lte=end)
            .exclude(status=Lease.Status.PROPOSED)
            .filter(Q(actual_end__isnull=True) | Q(actual_end__gte=start))
            .select_related("counterparty").prefetch_related("properties", "breaks", "options", "rent_schedule")
            .order_by("reference"))


def gather(year):
    start, end = year_bounds(year)
    rows = []
    for lease in held_leases(start, end):
        stop, source = lease_end(lease)
        rent = rent_on(lease, max(start, lease.term_start))
        row = LeaseRow(lease=lease, lease_end=stop, lease_end_source=source, rent_now=rent,
                       nominal=lease.rent_frequency == Lease.RentFrequency.PEPPERCORN or rent <= NOMINAL)
        if stop is None:
            row.problems.append("No end date: set the IFRS 16 lease term end for this periodic agreement.")
        elif stop >= start:
            row.payments = payments(lease, max(start, lease.term_start), stop)
        if row.nominal and not lease.ifrs16_treatment:
            row.problems.append("Nil or nominal rent: the right-of-use asset needs a current value.")
        if lease.is_index_linked:
            row.problems.append("Index-linked: payments shown at the rent in force now; remeasure when it changes.")
        rows.append(row)
    return Pack(year=year, start=start, end=end, rows=rows, changes=changes(start, end, rows))


def changes(start, end, rows):
    """What changed in the year: new and ended leases, rent changes and changes to the term."""
    from django.contrib.contenttypes.models import ContentType

    from apps.core.models import AuditEntry

    out = []
    leases = {row.lease.pk: row.lease for row in rows}
    for lease in leases.values():
        if start <= lease.term_start <= end:
            out.append(Change(lease, lease.term_start, "New lease", f"Term from {lease.term_start:%d %b %Y}"))
        if lease.actual_end and start <= lease.actual_end <= end:
            out.append(Change(lease, lease.actual_end, "Lease ended", lease.get_status_display()))
        previous = None
        for entry in lease.rent_schedule.all():
            if start <= entry.effective_from <= end and entry.reason != "initial":
                was = f"£{previous:,.2f}" if previous is not None else "–"
                out.append(Change(lease, entry.effective_from, f"Rent change: {entry.get_reason_display()}",
                                  f"{was} to £{entry.annual_rent:,.2f} a year. {entry.notes}".strip()))
            previous = entry.annual_rent
    lease_type = ContentType.objects.get_for_model(Lease)
    entries = AuditEntry.objects.filter(content_type=lease_type, object_id__in=[str(pk) for pk in leases],
                                        timestamp__date__gte=start, timestamp__date__lte=end,
                                        action=AuditEntry.Action.UPDATE).order_by("timestamp")
    for entry in entries:
        lease = leases.get(int(entry.object_id))
        for name, label in TERM_FIELDS.items():
            value = (entry.changes or {}).get(name)
            if isinstance(value, list) and len(value) == 2:
                old, new = (_shown(name, v) for v in value)
                out.append(Change(lease, entry.timestamp.date(), f"{label} changed", f"{old} to {new}"))
    return sorted(out, key=lambda c: (c.when, c.lease.reference))


def _shown(name, value):
    """A value from the change log as people read it: choices by their label, dates as dates."""
    if value in (None, ""):
        return "–"
    choices = dict(Lease._meta.get_field(name).choices or [])
    if choices:
        return str(choices.get(value, value))
    try:
        return date.fromisoformat(value).strftime("%d %b %Y")
    except (TypeError, ValueError):
        return str(value)


# ------------------------------------------------------------------ the workbook

def _options(lease):
    parts = [f"Break {b.break_date:%d %b %Y} ({b.get_exercisable_by_display().lower()})" for b in lease.breaks.all()]
    parts += [f"{o.get_option_type_display()}{f' by {o.exercise_by:%d %b %Y}' if o.exercise_by else ''}"
              for o in lease.options.all()]
    return "; ".join(parts)


def to_xlsx(pack, organisation=""):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    bold, money, day = Font(bold=True), "£#,##0.00", "d mmm yyyy"
    fill = PatternFill("solid", start_color="FFF2CC")  # cells for finance to complete
    wb = Workbook()

    ws = wb.active
    ws.title = "Leases"
    ws.append([f"IFRS 16 data pack {year_label(pack.year)}{': ' + organisation if organisation else ''}"])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([f"Leases the council holds, in force at any time from {pack.start:%d %B %Y} to {pack.end:%d %B %Y}. "
               f"Prepared {date.today():%d %B %Y}. Yellow columns are for finance."])
    ws.append([])
    head = ["Agreement", "Landlord", "Premises", "Property references", "UPRNs", "Type", "Status", "Term start",
            "Contractual expiry", "IFRS 16 lease term ends", "Lease end taken from", "Months left at 1 April",
            "Months left at 31 March", "IFRS 16 treatment", "Rent a year (£)", "Rent payable", "Rent-free until",
            "Nil or nominal rent", "Review basis", "Index", "Next review", "Breaks and options",
            "Payments from 1 April (£, undiscounted)", "Payments after 31 March (£, undiscounted)",
            "Number of payments after 31 March", "Notes for finance", "Discount rate (%)", "Right-of-use asset value"]
    ws.append(head)
    for cell in ws[ws.max_row]:
        cell.font = bold
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    after = pack.end + timedelta(days=1)
    for row in pack.rows:
        lease = row.lease
        props = list(lease.properties.all())
        notes = "; ".join(filter(None, [lease.ifrs16_notes] + row.problems))
        ws.append([
            lease.reference, lease.counterparty.name,
            lease.premises_description or "; ".join(p.name for p in props),
            "; ".join(p.reference for p in props), "; ".join(p.uprn for p in props if p.uprn),
            str(lease.get_agreement_type_display()), str(lease.get_status_display()), lease.term_start, lease.term_end,
            row.lease_end, row.lease_end_source, row.months_left(pack.start), row.months_left(after),
            str(lease.get_ifrs16_treatment_display() if lease.ifrs16_treatment
                else Lease.Ifrs16Treatment.ON_BALANCE_SHEET.label),
            float(row.rent_now), str(lease.get_rent_frequency_display()), lease.rent_free_until,
            "Yes" if row.nominal else "", str(lease.get_review_basis_display()),
            lease.index_series.code if lease.index_series_id else "", lease.next_review_date, _options(lease),
            float(row.total_from(pack.start)), float(row.total_from(after)),
            sum(1 for when, _a in row.payments if when >= after), notes, None, None])
        r = ws.max_row
        for col in (8, 9, 10, 17, 21):
            ws.cell(r, col).number_format = day
        for col in (15, 23, 24):
            ws.cell(r, col).number_format = money
        for col in (27, 28):
            ws.cell(r, col).fill = fill
    for col in (27, 28):
        ws.cell(4, col).fill = fill
    widths = (12, 28, 32, 18, 16, 12, 12, 12, 12, 14, 22, 10, 10, 30, 14, 22, 12, 10, 20, 8, 12, 36, 16, 16, 10, 50, 12,
              16)
    for n, width in enumerate(widths, start=1):
        ws.column_dimensions[ws.cell(4, n).column_letter].width = width
    ws.freeze_panes = "B5"

    pay = wb.create_sheet("Payments")
    pay.append(["Agreement", "Landlord", "Payment date", "Amount (£)", "In the year", "Financial year"])
    for cell in pay[1]:
        cell.font = bold
    for row in pack.rows:
        for when, amount in row.payments:
            fy = current_year(when)
            pay.append([row.lease.reference, row.lease.counterparty.name, when, float(amount),
                        "Yes" if when <= pack.end else "", year_label(fy)])
            pay.cell(pay.max_row, 3).number_format = day
            pay.cell(pay.max_row, 4).number_format = money
    for col, width in zip("ABCDEF", (12, 30, 14, 14, 10, 12)):
        pay.column_dimensions[col].width = width
    pay.freeze_panes = "A2"

    ch = wb.create_sheet("Changes in the year")
    ch.append(["Date", "Agreement", "Landlord", "Change", "Detail"])
    for cell in ch[1]:
        cell.font = bold
    for c in pack.changes:
        ch.append([c.when, c.lease.reference, c.lease.counterparty.name, str(c.what), str(c.detail)])
        ch.cell(ch.max_row, 1).number_format = day
    if not pack.changes:
        ch.append(["", "", "", "No changes recorded in the year."])
    for col, width in zip("ABCDE", (12, 12, 30, 30, 60)):
        ch.column_dimensions[col].width = width

    notes = wb.create_sheet("Notes")
    for line in NOTES:
        notes.append([line])
    notes.column_dimensions["A"].width = 120
    for row in notes.iter_rows():
        row[0].alignment = Alignment(wrap_text=True, vertical="top")
    notes["A1"].font = Font(bold=True, size=14)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


NOTES = [
    "How this pack is put together",
    "It lists the agreements PHAEMA records as held by the council (the council is the tenant or licensee), in force at "
    "any time in the financial year. Finance does the IFRS 16 accounting; PHAEMA provides the lease facts.",
    "Lease term. The IFRS 16 lease term ends on the date set on the agreement (IFRS 16 lease term ends), or else the "
    "contractual expiry. Set it on the agreement where the council is reasonably certain to use a break, or to renew "
    "or extend, and for periodic tenancies, which otherwise have no end date and no payments in this pack.",
    "Payments. In advance, on the agreement's payment dates, at the rent in force on each date from the rent "
    "schedule (including fixed steps already agreed), and none before a rent-free period ends. Part periods are not "
    "apportioned. Amounts are as recorded, without VAT. They are undiscounted.",
    "Index-linked rents are shown at the rent in force now. Remeasure the liability when an index review changes the "
    "payments; the next pack lists the change.",
    "Nil or nominal rents (peppercorns, or a rent of £100 a year or less) are flagged: the Code brings these into "
    "IFRS 16, with the right-of-use asset measured at current value, so a valuation is usually needed.",
    "Treatment. The treatment recorded on the agreement (on the balance sheet, short-term, low-value or not a lease) "
    "is finance's decision; agreements with none recorded are shown as on the balance sheet.",
    "For finance to add: the discount rate (the rate implicit in the lease, or the council's incremental borrowing "
    "rate) and any right-of-use asset value.",
    "Changes in the year come from the agreements, their rent schedules and the change log: new and ended leases, "
    "rent changes, and changes to the term, dates, treatment or rent frequency.",
]
