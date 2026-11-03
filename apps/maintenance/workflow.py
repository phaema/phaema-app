# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reactive and planned jobs: opening, works orders, approval, completion and who pays."""
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from apps.core.models import ModuleSettings, supervisor_of
from apps.core.roles import is_administrator, manages

from . import responsibility
from .models import Job, PlannedTask, Responsibility


def can_work(user, job):
    return is_administrator(user) or manages(user, job.property) or (job.owner_id and job.owner_id == user.pk)


def open_job(prop, title, user=None, **fields):
    job = Job(property=prop, title=title, **fields)
    who, why, lease = responsibility.decide(prop, job.category)
    if "responsibility" not in fields:
        job.responsibility, job.responsibility_reason = who, why
    job.lease = job.lease or lease
    job.owner = job.owner or prop.managing_surveyor or user
    if not job.target_date:
        job.set_target()
    job.save()
    return job


# ------------------------------------------------------------------ works orders and approval

def approval_limit():
    return ModuleSettings.load().order_approval_limit


def needs_order_approval(job):
    return bool(job.estimate and job.estimate > approval_limit() and job.approval_status != "approved")


def request_order_approval(job, user):
    approver = supervisor_of(user)
    if approver is None:
        raise ValueError("You have no supervisor in PHAEMA to approve this order. Ask an administrator to set one.")
    if approver.pk == user.pk:
        raise ValueError("You cannot approve your own order.")
    job.approval_status, job.approver, job.approval_comments = "pending", approver, ""
    job.save(update_fields=["approval_status", "approver", "approval_comments", "updated_at"])
    _email(approver, f"Works order to approve: {job.reference}", "maintenance/email/approve_order.txt", job)


def can_approve(user, job):
    if job.approval_status != "pending":
        return False
    requester = job.owner_id
    return (user.pk == job.approver_id or is_administrator(user)) and user.pk != requester


def decide_order(job, user, approve, comments=""):
    job.approval_status = "approved" if approve else "returned"
    job.approved_by, job.approved_at, job.approval_comments = user, timezone.now(), comments.strip()
    job.save(update_fields=["approval_status", "approved_by", "approved_at", "approval_comments", "updated_at"])
    if job.owner:
        _email(job.owner, f"Works order {'approved' if approve else 'returned'}: {job.reference}",
               "maintenance/email/order_decided.txt", job)


def issue_order(job, email_contractor=True, on=None):
    if job.contractor is None:
        raise ValueError("Choose the contractor first.")
    if needs_order_approval(job):
        raise ValueError(f"Orders over £{approval_limit():,.0f} need your supervisor's approval first.")
    job.status, job.ordered_on = Job.Status.ORDERED, on or date.today()
    job.save(update_fields=["status", "ordered_on", "updated_at"])
    if email_contractor and job.contractor.email:
        body = render_to_string("maintenance/email/works_order.txt", {"job": job, "settings": ModuleSettings.load()})
        send_mail(f"Works order {job.reference}: {job.title}", body, settings.DEFAULT_FROM_EMAIL,
                  [job.contractor.email], fail_silently=True)
        return True
    return False


def complete(job, on, cost=None, notes="", invoice=""):
    job.status, job.completed_on = Job.Status.COMPLETED, on
    if cost is not None:
        job.actual_cost = cost
    job.completion_notes, job.invoice_reference = notes.strip() or job.completion_notes, invoice.strip()
    job.save()
    if job.planned_task_id:
        task = job.planned_task
        if not task.last_done or on > task.last_done:
            task.record_done(on)


# ------------------------------------------------------------------ who pays

def raise_recharge(job, issue_date=None):
    """Charge the cost of the repair to the tenant's rent account."""
    from apps.ledger.billing import _number, settings_row
    from apps.ledger.models import Charge

    if job.recharge_id or not job.lease_id or not job.actual_cost:
        return None
    issue_date = issue_date or date.today()
    rate = settings_row().vat_rate if job.lease.vat_chargeable else Decimal("0")
    net, vat, gross = Charge.amounts(job.actual_cost, rate)
    charge = Charge(lease=job.lease, kind=Charge.Kind.OTHER, issue_date=issue_date,
                    due_date=issue_date + timedelta(days=30), net=net, vat_rate=rate, vat=vat, gross=gross,
                    description=f"Repair recharge {job.reference}: {job.title}"[:200])
    _number([charge])
    charge.save()
    job.recharge = charge
    job.save(update_fields=["recharge", "updated_at"])
    return charge


def service_charge_years(job):
    """Approved service charge years covering this property and the date the work was done."""
    from apps.servicecharges.models import ScheduleYear

    when = job.completed_on or date.today()
    ids = [job.property_id] + [a.pk for a in job.property.ancestors()]
    return (ScheduleYear.objects.filter(schedule__properties__in=ids, start__lte=when, end__gte=when)
            .select_related("schedule").distinct())


def add_to_service_charge(job, year, heading):
    from apps.servicecharges.models import Expenditure

    if job.expenditure_id or not job.actual_cost:
        return None
    item = Expenditure.objects.create(
        year=year, heading=heading, spent_on=job.completed_on or date.today(),
        supplier=str(job.contractor or "")[:150], description=f"{job.reference}: {job.title}"[:200],
        invoice_reference=job.invoice_reference, amount=job.actual_cost)
    job.expenditure = item
    job.save(update_fields=["expenditure", "updated_at"])
    return item


# ------------------------------------------------------------------ planned maintenance

@transaction.atomic
def auto_raise(today=None):
    """Raise jobs for planned tasks coming due. Returns how many were raised."""
    today = today or date.today()
    raised = 0
    for task in PlannedTask.objects.filter(active=True, raise_days_before__isnull=False).select_related("property"):
        if task.next_due - timedelta(days=task.raise_days_before) > today:
            continue
        if task.jobs.filter(status__in=Job.OPEN).exists():
            continue
        if task.jobs.filter(completed_on__gte=task.next_due - timedelta(days=task.raise_days_before)).exists():
            continue
        raise_for_task(task)
        raised += 1
    return raised


def raise_for_task(task, user=None):
    return open_job(task.property, task.title, user=user, planned_task=task, component=task.component,
                    category=task.category, priority=Job.Priority.PLANNED, how_reported=Job.Reported.PLANNED,
                    target_date=task.next_due, contractor=task.contractor, estimate=task.estimated_cost,
                    description=task.regulation and f"Law or standard: {task.regulation}" or "")


def summary(user=None, today=None):
    today = today or date.today()
    open_jobs = Job.objects.filter(status__in=Job.OPEN)
    tasks = PlannedTask.objects.filter(active=True)
    return {
        "open": open_jobs.count(),
        "emergency": open_jobs.filter(priority="emergency").count(),
        "past_target": open_jobs.filter(target_date__lt=today).count(),
        "mine": open_jobs.filter(owner=user).count() if user else 0,
        "to_approve": Job.objects.filter(approval_status="pending", approver=user).count() if user else 0,
        "tasks_overdue": tasks.filter(next_due__lt=today).count(),
        "statutory_overdue": tasks.filter(next_due__lt=today, statutory=True).count(),
        "tasks_due_30": tasks.filter(next_due__gte=today, next_due__lte=today + timedelta(days=30)).count(),
        "to_recharge": Job.objects.filter(status="completed", responsibility=Responsibility.RECHARGE,
                                          recharge__isnull=True).count(),
    }


def _email(user, subject, template, job):
    if not user or not user.email:
        return
    body = render_to_string(template, {"job": job, "user": user,
                                       "base_url": getattr(settings, "PHAEMA_BASE_URL", "").rstrip("/")})
    send_mail(f"PHAEMA: {subject}", body, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=True)
