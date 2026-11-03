# SPDX-License-Identifier: AGPL-3.0-or-later
"""Working out what rent is due, raising it, and the state of each account."""
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q, Sum

from apps.core.models import ModuleSettings
from apps.leases import workflow
from apps.leases.models import Lease

from .models import PENNY, Charge, DemandRun, Receipt

AGE_BANDS = [(30, "1–30 days"), (60, "31–60 days"), (90, "61–90 days"), (None, "Over 90 days")]


def settings_row():
    return ModuleSettings.load()


# ------------------------------------------------------------------ periods and amounts

def _lease_end(lease):
    if lease.status == Lease.Status.HOLDING_OVER:
        return lease.actual_end
    return lease.actual_end or lease.term_end


def rent_periods(lease, due_from, due_to):
    """Rent periods with a due date in [due_from, due_to]: [(period_start, period_end, due_date, full)].

    Rent is due in advance on each payment date. A first period that starts before the first
    payment date (e.g. a lease starting between quarter days) is due on the term start, and a
    last period cut short by the lease ending is apportioned.
    """
    if lease.rent_frequency not in workflow.PERIODS:
        return []
    end = _lease_end(lease)
    lookahead = workflow.payment_dates(lease, due_from, 1 + 12 * max(1, (due_to - due_from).days // 28 + 1))
    dates = [d for d in lookahead if d <= due_to]
    periods = []
    first_payment = (workflow.payment_dates(lease, lease.term_start, 1) or [None])[0]
    if (first_payment and lease.term_start < first_payment and due_from <= lease.term_start <= due_to
            and (not end or lease.term_start <= end)):
        periods.append((lease.term_start, first_payment - timedelta(days=1), lease.term_start, False))
    for due in dates:
        following = workflow.payment_dates(lease, due + timedelta(days=1), 1)
        natural_end = (following[0] if following else _next_natural(lease, due)) - timedelta(days=1)
        period_end = min(natural_end, end) if end else natural_end
        if period_end < due:
            continue
        periods.append((due, period_end, due, period_end == natural_end))
    return periods


def _next_natural(lease, due):
    """The payment date after `due`, ignoring the lease's end (used to size a final, cut-short period)."""
    from apps.core.dates import add_months

    return add_months(due, 12 // workflow.PERIODS[lease.rent_frequency])


def period_rent(lease, start, end, full):
    annual = workflow.rent_on(lease, start)
    if full:
        return (annual / workflow.PERIODS[lease.rent_frequency]).quantize(PENNY)
    days = (end - start).days + 1
    return (annual * days / 365).quantize(PENNY)


def billable_leases():
    return (Lease.objects.filter(direction=Lease.Direction.OUT, status__in=workflow.LIVE)
            .exclude(rent_frequency=Lease.RentFrequency.PEPPERCORN)
            .select_related("counterparty").prefetch_related("rent_schedule", "properties"))


def proposed_charges(due_from, due_to, issue_date=None, rent=True, service=None):
    """Unsaved charges due between two dates that have not been raised before: rent, and service
    charges on account when the service charge module is on (or `service` says so)."""
    issue_date = issue_date or date.today()
    settings = settings_row()
    vat_rate = settings.vat_rate
    if service is None:
        service = settings.service_charges_enabled
    extra = []
    if service:
        from apps.servicecharges.apportion import proposed_service_charges

        extra = proposed_service_charges(due_from, due_to, issue_date, vat_rate)
    if not rent:
        return sorted(extra, key=lambda c: (c.due_date, c.lease.reference, c.kind))
    done = set(Charge.objects.filter(kind=Charge.Kind.RENT, period_start__isnull=False)
               .values_list("lease_id", "period_start"))
    out = []
    for lease in billable_leases():
        for start, end, due, full in rent_periods(lease, due_from, due_to):
            if (lease.pk, start) in done:
                continue
            net = period_rent(lease, start, end, full)
            if net <= 0:
                continue
            rate = vat_rate if lease.vat_chargeable else Decimal("0")
            net, vat, gross = Charge.amounts(net, rate)
            label = "Rent" if full else "Rent (part period)"
            out.append(Charge(lease=lease, kind=Charge.Kind.RENT, period_start=start, period_end=end, due_date=due,
                              issue_date=issue_date, net=net, vat_rate=rate, vat=vat, gross=gross,
                              description=f"{label} {start:%d/%m/%Y} to {end:%d/%m/%Y}"))
    return sorted(out + extra, key=lambda c: (c.due_date, c.lease.reference, c.kind))


def _number(charges):
    """Give each charge the next invoice number, if PHAEMA raises the invoices."""
    settings_row()
    row = ModuleSettings.objects.select_for_update().get(pk=1)
    if row.invoicing != ModuleSettings.Invoicing.PHAEMA:
        return
    for charge in charges:
        charge.invoice_number = f"{row.invoice_prefix}{row.next_invoice_number:06d}"
        row.next_invoice_number += 1
    row.save(update_fields=["next_invoice_number"])


@transaction.atomic
def issue_run(due_from, due_to, issue_date=None, notes="", rent=True, service=None):
    """Raise every outstanding charge due between the dates. Returns the run (None if nothing to raise)."""
    issue_date = issue_date or date.today()
    charges = proposed_charges(due_from, due_to, issue_date, rent=rent, service=service)
    if not charges:
        return None
    run = DemandRun.objects.create(due_from=due_from, due_to=due_to, issue_date=issue_date, notes=notes)
    _number(charges)
    for c in charges:
        c.run = run
        c.save()
    return run


@transaction.atomic
def credit(charge, reason, amount=None, issue_date=None):
    """A credit note against a charge, for all of it or part (amount is the gross to credit)."""
    issue_date = issue_date or date.today()
    already = -(charge.credits.aggregate(t=Sum("gross"))["t"] or 0)
    available = charge.gross - already
    gross = available if amount is None else Decimal(amount).quantize(PENNY)
    if gross <= 0 or gross > available:
        raise ValueError(f"You can credit up to £{available:,.2f} of this charge.")
    net = (gross * 100 / (100 + charge.vat_rate)).quantize(PENNY)
    note = Charge(lease=charge.lease, kind=Charge.Kind.CREDIT, credit_for=charge, issue_date=issue_date,
                  due_date=issue_date, net=-net, vat_rate=charge.vat_rate, vat=-(gross - net), gross=-gross,
                  period_start=None, period_end=None,
                  description=f"Credit against {charge.reference}: {reason}"[:200])
    _number([note])
    note.save()
    return note


# ------------------------------------------------------------------ accounts

@dataclass
class Line:
    when: date
    kind: str  # charge or receipt
    obj: object
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")
    balance: Decimal = Decimal("0")
    outstanding: Decimal = Decimal("0")  # for charges: the part still unpaid


@dataclass
class Account:
    lease: object
    lines: list
    balance: Decimal
    overdue: Decimal
    aged: list = field(default_factory=list)  # [(label, amount)]
    unallocated: Decimal = Decimal("0")


def account(lease, today=None, charges=None, receipts=None):
    """The lease's account: every charge and receipt in date order with a running balance,
    and what is still owed on each charge, paying off the oldest debt first."""
    today = today or date.today()
    charges = list(charges if charges is not None else lease.charges.all())
    receipts = list(receipts if receipts is not None else lease.receipts.all())
    lines = [Line(c.due_date, "charge", c, debit=c.gross) for c in charges]
    lines += [Line(r.received_on, "receipt", r, credit=r.amount) for r in receipts]
    lines.sort(key=lambda line: (line.when, 0 if line.kind == "charge" else 1, line.obj.pk))
    balance = Decimal("0")
    for line in lines:
        balance += line.debit - line.credit
        line.balance = balance
    # Oldest debt first: credits (receipts and credit notes) pay off positive charges in due-date order.
    paying = sum((r.amount for r in receipts), Decimal("0")) + sum((-c.gross for c in charges if c.gross < 0),
                                                                   Decimal("0"))
    for line in sorted((x for x in lines if x.kind == "charge" and x.debit > 0),
                       key=lambda x: (x.obj.due_date, x.obj.pk)):
        used = min(paying, line.debit)
        line.outstanding = line.debit - used
        paying -= used
    owed = [x for x in lines if x.outstanding > 0]
    overdue = [x for x in owed if x.obj.due_date < today]
    aged = []
    for i, (limit, label) in enumerate(AGE_BANDS):
        low = 0 if i == 0 else AGE_BANDS[i - 1][0]
        total = sum((x.outstanding for x in overdue
                     if (today - x.obj.due_date).days > low and (limit is None or (today - x.obj.due_date).days
                                                                 <= limit)), Decimal("0"))
        aged.append((label, total))
    return Account(lease, lines, balance, sum((x.outstanding for x in overdue), Decimal("0")), aged,
                   unallocated=max(paying, Decimal("0")))


def accounts(today=None, leases=None):
    """Accounts for every lease with ledger activity, loaded efficiently."""
    today = today or date.today()
    qs = leases if leases is not None else Lease.objects.filter(Q(charges__isnull=False) | Q(receipts__isnull=False))
    qs = qs.distinct().select_related("counterparty").prefetch_related("charges", "receipts", "properties")
    return [account(lease, today, lease.charges.all(), lease.receipts.all()) for lease in qs]


def arrears_summary(today=None):
    """Totals across all accounts: overdue debt by age, and the number of leases in arrears."""
    rows = [a for a in accounts(today) if a.overdue > 0]
    bands = [(label, sum((dict(a.aged)[label] for a in rows), Decimal("0"))) for _l, label in AGE_BANDS]
    return {"accounts": sorted(rows, key=lambda a: -a.overdue), "total": sum((a.overdue for a in rows), Decimal("0")),
            "bands": bands, "count": len(rows)}


def collection(today=None, days=365):
    """Rent collected compared with rent that fell due, over the last `days` days."""
    today = today or date.today()
    since = today - timedelta(days=days)
    due = Charge.objects.filter(due_date__gt=since, due_date__lte=today).aggregate(t=Sum("gross"))["t"] or Decimal(0)
    received = Receipt.objects.filter(received_on__gt=since, received_on__lte=today).aggregate(
        t=Sum("amount"))["t"] or Decimal(0)
    rate = (received / due * 100).quantize(Decimal("0.1")) if due > 0 else None
    return {"due": due, "received": received, "rate": rate}
