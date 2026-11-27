# SPDX-License-Identifier: AGPL-3.0-or-later
"""What one tenant is shown for a service charge year: the budget statement and the year-end statement. Used by
the staff pages and the tenant portal, so both show the same figures."""
from datetime import date
from decimal import Decimal

from apps.ledger.models import Charge

from . import apportion
from .models import ScheduleMember, ScheduleYear


def budget_context(year, member):
    from apps.leases.workflow import PERIODS

    share = next(s for s in apportion.shares(year.schedule)[0] if s.member.pk == member.pk)
    annual = apportion.on_account_annual(year, share)
    periods = PERIODS.get(member.lease.rent_frequency)
    return {
        "year": year, "member": member, "share": share, "annual": annual, "today": date.today(),
        "per_payment": (annual / periods).quantize(Decimal("0.01")) if periods else None,
        "rows": [(h, b) for h, b, _a in apportion.by_heading(year) if b],
        "budget": apportion.budget_total(year),
    }


def statement_context(year, member):
    recon = apportion.reconcile(year)
    line = next(line for line in recon.lines if line.share.member.pk == member.pk)
    return {
        "year": year, "member": member, "line": line, "recon": recon, "today": date.today(),
        "percent": (line.share.share * 100).quantize(Decimal("0.01")),
        "balancing": Charge.objects.filter(service_year=year, lease=member.lease, period_start__isnull=True),
    }


def published_years(lease):
    """[(member, year, budget issued, statement issued)] for the agreement's service charge schedules: only years
    whose budget or year-end statement has been issued to tenants, newest first."""
    out = []
    members = ScheduleMember.objects.filter(lease=lease, schedule__active=True).select_related("schedule")
    for member in members:
        for year in member.schedule.years.order_by("-start"):
            budget = bool(year.budget_issued_on) and year.status != ScheduleYear.Status.DRAFT
            statement = bool(year.statements_issued_on) and year.status == ScheduleYear.Status.RECONCILED
            if budget or statement:
                out.append((member, year, budget, statement))
    return out
