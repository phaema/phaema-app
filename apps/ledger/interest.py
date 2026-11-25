# SPDX-License-Identifier: AGPL-3.0-or-later
"""Interest on late rent, as the lease provides.

The rent account is replayed day by day in the same way as the account itself: a credit note first reduces the charge
it credits, and payments clear the oldest debt first. That gives, for every charge, how much of it was unpaid on each
day. Interest runs on that amount at the lease's rate (Bank of England base rate plus a margin, or a fixed rate) for
every day it was unpaid, from the due date, once the charge has been unpaid for longer than the lease's grace period.
It is simple interest over a 365-day year, not compounded, and interest is never charged on interest.

Each interest charge covers the days up to a date. The next calculation starts the day after, so no day is charged
twice. The figures are a proposal: someone with finance rights checks them and raises the charge.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction

from .models import BaseRate, Charge

PENNY = Decimal("0.01")
ZERO = Decimal("0")
CHARGEABLE = (Charge.Kind.RENT, Charge.Kind.SERVICE, Charge.Kind.OTHER)


@dataclass
class ChargeInterest:
    charge: object
    days: int
    interest: Decimal
    paid_on: date = None  # when it was cleared, if it has been


@dataclass
class Result:
    lease: object
    since: date  # interest already charged up to this day (None: never)
    until: date
    lines: list = field(default_factory=list)
    total: Decimal = ZERO
    problem: str = ""

    @property
    def ok(self):
        return not self.problem


def rates(lease):
    """A function giving the yearly interest rate (as a percentage) on a day, or None where no rate is known."""
    margin = lease.interest_margin_pct
    if lease.interest_basis == lease.InterestBasis.FIXED:
        return lambda day: margin
    history = list(BaseRate.objects.order_by("effective_from").values_list("effective_from", "rate"))

    def on(day):
        rate = None
        for start, value in history:
            if start <= day:
                rate = value
            else:
                break
        return None if rate is None else rate + margin

    return on


def unpaid_history(charges, receipts):
    """{charge pk: [(date, amount still unpaid from that date)]} replaying the account in date order."""
    debts = sorted((c for c in charges if c.gross > 0), key=lambda c: (c.due_date, c.pk))
    credits = [c for c in charges if c.gross < 0]
    events = [(c.due_date, 0, "charge", c) for c in debts]
    events += [(c.due_date, 1, "credit", c) for c in credits]
    events += [(r.received_on, 1, "receipt", r) for r in receipts]
    events.sort(key=lambda e: (e[0], e[1], e[3].pk))
    owed, history, spare = {}, {c.pk: [] for c in debts}, ZERO

    def set_owed(charge, amount, day):
        owed[charge.pk] = amount
        history[charge.pk].append((day, amount))

    def pay(amount, day):
        for c in debts:
            if amount <= 0:
                break
            if owed.get(c.pk, ZERO) > 0:
                used = min(amount, owed[c.pk])
                set_owed(c, owed[c.pk] - used, day)
                amount -= used
        return amount

    for day, _order, kind, obj in events:
        if kind == "charge":
            set_owed(obj, obj.gross, day)
            if spare > 0:  # money paid in advance, or left over, is used as the charge falls due
                used = min(spare, obj.gross)
                set_owed(obj, obj.gross - used, day)
                spare -= used
            continue
        amount = -obj.gross if kind == "credit" else obj.amount
        if kind == "credit" and obj.credit_for_id in owed and owed[obj.credit_for_id] > 0:
            target = next(c for c in debts if c.pk == obj.credit_for_id)
            used = min(amount, owed[target.pk])
            set_owed(target, owed[target.pk] - used, day)
            amount -= used
        spare += pay(amount, day)
    return history


def calculate(lease, until=None):
    """The interest owed on the lease's late payments, for the days after the last interest charge up to `until`."""
    until = until or date.today()
    last = lease.charges.filter(kind=Charge.Kind.INTEREST, period_end__isnull=False).order_by("-period_end").first()
    since = last.period_end if last else None
    result = Result(lease=lease, since=since, until=until)
    if not lease.interest_basis or lease.interest_margin_pct is None:
        result.problem = "The agreement has no interest terms. Add them under Rent demands and arrears."
        return result
    rate_on = rates(lease)
    charges = list(lease.charges.all())
    receipts = list(lease.receipts.all())
    history = unpaid_history(charges, receipts)  # every charge, as on the account, so payments land the same way
    grace = lease.interest_grace_days
    missing_rate = set()
    for charge in (c for c in charges if c.kind in CHARGEABLE and c.gross > 0):
        steps = history.get(charge.pk, [])
        paid_on = next((day for day, amount in steps if amount <= 0), None)
        if paid_on is not None and (paid_on - charge.due_date).days <= grace:
            continue  # paid within the time the lease allows
        if paid_on is None and (until - charge.due_date).days <= grace:
            continue  # not late enough yet
        start = max(charge.due_date, since) if since else charge.due_date
        end = min(paid_on, until) if paid_on else until
        total, days, day = ZERO, 0, start + timedelta(days=1)  # interest for each day after the due date
        index, unpaid = 0, ZERO
        while day <= end:
            while index < len(steps) and steps[index][0] < day:
                unpaid = steps[index][1]
                index += 1
            if unpaid > 0:
                rate = rate_on(day)
                if rate is None:
                    missing_rate.add(day)
                else:
                    total += unpaid * rate / 100 / 365
                    days += 1
            day += timedelta(days=1)
        interest = total.quantize(PENNY, ROUND_HALF_UP)
        if interest > 0:
            result.lines.append(ChargeInterest(charge, days, interest, paid_on))
    if missing_rate:
        first = min(missing_rate)
        result.problem = (f"PHAEMA has no Bank of England base rate for {first:%d %B %Y}. Add the base rates under "
                          "Manage data, Bank of England base rates.")
        result.lines, result.total = [], ZERO
        return result
    result.total = sum((line.interest for line in result.lines), ZERO)
    return result


@transaction.atomic
def raise_charge(lease, until, issue_date=None):
    """Raise the interest worked out up to `until` as a charge on the account. Returns the charge, or None."""
    from .billing import _number

    result = calculate(lease, until)
    if not result.ok or result.total <= 0:
        return None
    issue_date = issue_date or date.today()
    start = (result.since + timedelta(days=1)) if result.since else min(line.charge.due_date for line in result.lines)
    charge = Charge(lease=lease, kind=Charge.Kind.INTEREST, issue_date=issue_date, due_date=issue_date,
                    period_start=start, period_end=until, net=result.total, vat_rate=ZERO, vat=ZERO,
                    gross=result.total,
                    description=f"Interest on late payment to {until:%d/%m/%Y}")
    _number([charge])
    charge.save()
    return charge
