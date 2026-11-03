# SPDX-License-Identifier: AGPL-3.0-or-later
"""Demonstration rent ledger: a year of rent charged on the fictional Exampleton leases, mostly paid,
with a few tenants in arrears, a credit note and an earlier finance export."""
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction

from apps.core.models import ModuleSettings
from apps.leases.models import Lease

from . import billing
from .models import Charge, DemandRun, ExportBatch, Receipt

NOTE = "Demonstration data."
UNPAID_LAST = {"DL-0016": 2, "DL-0024": 3}  # tenants who have missed their latest payments
PART_PAID = {"DL-0004": Decimal("0.5")}  # paid half of the latest charge


@transaction.atomic
def load(today=None):
    today = today or date.today()
    modules = ModuleSettings.load()
    if not modules.rent_ledger_enabled:
        modules.rent_ledger_enabled = True
        modules.rent_income_code = modules.rent_income_code or "EST-1000-9100"
        modules.save()
    start = today - timedelta(days=365)
    while start <= today:
        end = min(start + timedelta(days=91), today)
        billing.issue_run(start, end, issue_date=max(start - timedelta(days=21), date(2000, 1, 1)), notes=NOTE)
        start = end + timedelta(days=1)
    demo = Charge.objects.filter(lease__reference__startswith="DL-", kind=Charge.Kind.RENT, due_date__lt=today)
    by_lease = {}
    for c in demo.select_related("lease").order_by("due_date"):
        by_lease.setdefault(c.lease.reference, []).append(c)
    for ref, charges in by_lease.items():
        unpaid = UNPAID_LAST.get(ref, 0)
        for i, c in enumerate(charges):
            last = i >= len(charges) - unpaid
            if last:
                continue
            amount = c.gross
            if ref in PART_PAID and i == len(charges) - 1:
                amount = (c.gross * PART_PAID[ref]).quantize(Decimal("0.01"))
            Receipt.objects.get_or_create(
                payment_reference=f"DEMO-RCPT-{c.pk:06d}",
                defaults={"lease": c.lease, "received_on": c.due_date + timedelta(days=3 + c.pk % 9),
                          "amount": amount, "quoted_reference": c.reference, "notes": NOTE})
    allowance = Charge.objects.filter(lease__reference="DL-0015", kind=Charge.Kind.RENT).order_by("due_date").first()
    if allowance and not allowance.credits.exists():
        billing.credit(allowance, "rent allowance agreed for shop front repairs by the tenant",
                       Decimal("500.00"), issue_date=allowance.due_date + timedelta(days=14))
    if not ExportBatch.objects.exists():
        latest = DemandRun.objects.filter(notes=NOTE).order_by("-due_from").first()
        old = Charge.objects.filter(lease__reference__startswith="DL-").exclude(run=latest)
        if old.exists():
            batch = ExportBatch.objects.create()
            old.update(export=batch)
    return Charge.objects.filter(lease__reference__startswith="DL-").count()


def remove():
    leases = Lease.objects.filter(reference__startswith="DL-")
    Receipt.objects.filter(lease__in=leases).delete()
    Charge.objects.filter(lease__in=leases, credit_for__isnull=False).delete()
    Charge.objects.filter(lease__in=leases).delete()
    DemandRun.objects.filter(notes=NOTE, charges__isnull=True).delete()
    ExportBatch.objects.filter(charges__isnull=True).delete()
