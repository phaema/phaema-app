# SPDX-License-Identifier: AGPL-3.0-or-later
"""Service charge pages: schedules, years (budget against actual), reconciliation and tenant statements."""
from collections import namedtuple
from datetime import date
from decimal import Decimal
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core.models import ModuleSettings
from apps.core.roles import administrators_only, is_administrator
from apps.ledger.models import Charge
from apps.reports.export import csv_response, xlsx_response

from . import apportion
from .models import Schedule, ScheduleMember, ScheduleYear

Col = namedtuple("Col", "label type")


def service_view(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not ModuleSettings.load().service_charges_enabled:
            return render(request, "servicecharges/off.html", status=404)
        return view(request, *args, **kwargs)

    return login_required(wrapped)


def _year_summary(year):
    return {"year": year, "budget": apportion.budget_total(year), "actual": apportion.actual_total(year),
            "demanded": Charge.objects.filter(service_year=year, period_start__isnull=False)
            .aggregate(t=Sum("net"))["t"] or Decimal("0")}


@service_view
def schedule_list(request):
    rows = []
    for schedule in Schedule.objects.prefetch_related("properties", "members"):
        current = schedule.years.filter(start__lte=date.today()).first() or schedule.years.first()
        rows.append({"schedule": schedule, "current": _year_summary(current) if current else None})
    return render(request, "servicecharges/schedule_list.html", {
        "rows": rows, "ledger_on": ModuleSettings.load().rent_ledger_enabled})


@service_view
def schedule_detail(request, pk):
    schedule = get_object_or_404(Schedule, pk=pk)
    share_list, total_area, void = apportion.shares(schedule)
    current = schedule.years.filter(start__lte=date.today(), status=ScheduleYear.Status.APPROVED).first()
    rows = [(s, apportion.on_account_annual(current, s) if current else None) for s in share_list]
    return render(request, "servicecharges/schedule_detail.html", {
        "schedule": schedule, "rows": rows, "total_area": total_area, "void": void,
        "units": sorted(apportion.units(schedule), key=lambda u: u.reference), "current": current,
        "years": [_year_summary(y) for y in schedule.years.all()],
    })


BUDGET_COLUMNS = [Col("Heading", "text"), Col("Budget", "money"), Col("Actual", "money"), Col("Difference", "money")]


@service_view
def year_detail(request, pk):
    year = get_object_or_404(ScheduleYear.objects.select_related("schedule"), pk=pk)
    rows = apportion.by_heading(year)
    fmt = request.GET.get("format")
    if fmt in ("xlsx", "csv"):
        data = ([h.name, b, a, a - b] for h, b, a in rows)
        title = f"Service charge {year}"
        return xlsx_response(title, BUDGET_COLUMNS, data, totals=True) if fmt == "xlsx" else \
            csv_response(title, BUDGET_COLUMNS, data)
    share_list, _area, void = apportion.shares(year.schedule)
    demanded = dict(Charge.objects.filter(service_year=year, period_start__isnull=False).values("lease")
                    .annotate(t=Sum("net")).values_list("lease", "t"))
    members = [(s, apportion.on_account_annual(year, s), demanded.get(s.member.lease_id, Decimal("0")))
               for s in share_list]
    return render(request, "servicecharges/year_detail.html", {
        "year": year, "rows": rows, "summary": _year_summary(year), "members": members, "void": void,
        "expenditure": year.expenditure.select_related("heading").order_by("-spent_on", "-pk")[:100],
        "expenditure_count": year.expenditure.count(), "can_manage": is_administrator(request.user),
        "today": date.today(),
    })


@administrators_only
@service_view
@require_POST
def year_approve(request, pk):
    year = get_object_or_404(ScheduleYear, pk=pk, status=ScheduleYear.Status.DRAFT)
    if not year.budget_lines.exists():
        messages.error(request, _("Add the budget before approving it."))
    else:
        year.status, year.budget_approved_on = ScheduleYear.Status.APPROVED, date.today()
        year.save(update_fields=["status", "budget_approved_on", "updated_at"])
        messages.success(request, _("Budget approved. On-account service charges will be included in demand runs."))
    return redirect(year)


@administrators_only
@service_view
def reconcile(request, pk):
    year = get_object_or_404(ScheduleYear.objects.select_related("schedule"), pk=pk)
    if request.method == "POST":
        if year.status != ScheduleYear.Status.APPROVED:
            messages.error(request, _("Only a year with an approved budget can be reconciled."))
        elif year.end >= date.today() and "confirm_early" not in request.POST:
            messages.error(request, _("The year has not ended yet."))
        else:
            made = apportion.finalise(year)
            messages.success(request, _("Year reconciled: %(n)s balancing charges and credits raised.")
                             % {"n": len(made)})
        return redirect(year)
    return render(request, "servicecharges/reconcile.html", {
        "year": year, "recon": apportion.reconcile(year), "ended": year.end < date.today()})


@service_view
def statement(request, pk, member_pk):
    year = get_object_or_404(ScheduleYear.objects.select_related("schedule"), pk=pk)
    member = get_object_or_404(ScheduleMember.objects.select_related("lease", "lease__counterparty"),
                               pk=member_pk, schedule=year.schedule)
    recon = apportion.reconcile(year)
    line = next(line for line in recon.lines if line.share.member.pk == member.pk)
    return render(request, "servicecharges/statement.html", {
        "year": year, "member": member, "line": line, "recon": recon, "today": date.today(),
        "percent": (line.share.share * 100).quantize(Decimal("0.01")),
        "balancing": Charge.objects.filter(service_year=year, lease=member.lease, period_start__isnull=True),
    })
