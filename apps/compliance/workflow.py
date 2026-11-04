# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import date

from django.db.models import Prefetch

from . import rules
from .models import Action, Certificate, Requirement


def add_requirements(prop, kinds):
    made = []
    who, why = rules.responsible(prop)
    for kind in kinds:
        req, created = Requirement.objects.get_or_create(property=prop, kind=kind, defaults={
            "responsible": who, "responsible_reason": why})
        if not created and not req.active:
            req.active = True
            req.save(update_fields=["active", "updated_at"])
        made.append(req)
    return made


def requirements(**filters):
    return (Requirement.objects.filter(active=True, **filters).select_related("property", "kind")
            .prefetch_related(Prefetch("certificates", queryset=Certificate.objects.order_by("-issued_on", "-pk")
                                       .prefetch_related("actions"))))


def _latest(req):
    certs = list(req.certificates.all())
    req._latest = certs[0] if certs else None
    return req


def statuses(qs, today=None):
    """[(requirement, (colour, label, order))], worst first."""
    today = today or date.today()
    rows = [(r, _status(_latest(r), today)) for r in qs]
    return sorted(rows, key=lambda row: (row[1][2], row[0].property.reference))


def _status(req, today):
    cert = req.latest
    if cert is None:
        return ("red", "Missing", 0)
    if cert.expires_on < today:
        return ("red", "Expired", 1)
    if cert.result == Certificate.Result.UNSATISFACTORY:
        return ("red", "Unsatisfactory", 2)
    if (cert.expires_on - today).days <= 60:
        return ("orange", "Expires soon", 3)
    if any(a.done_on is None for a in cert.actions.all()):
        return ("orange", "Actions open", 4)
    return ("green", "Valid", 5)


def summary(today=None, qs=None):
    today = today or date.today()
    rows = statuses(requirements() if qs is None else qs, today)
    count = lambda *labels: sum(1 for _r, s in rows if s[1] in labels)  # noqa: E731
    return {
        "total": len(rows), "valid": count("Valid"), "missing": count("Missing"), "expired": count("Expired"),
        "failed": count("Unsatisfactory"), "soon": count("Expires soon"),
        "compliant_pct": round(100 * count("Valid", "Expires soon", "Actions open") / len(rows)) if rows else None,
        "actions_overdue": Action.objects.filter(certificate__requirement__in=[r for r, _s in rows],
                                                 done_on__isnull=True, due_on__lt=today).count(),
        "actions_open": Action.objects.filter(certificate__requirement__in=[r for r, _s in rows],
                                              done_on__isnull=True).count(),
    }


def record(req, issued_on, expires_on=None, upload=None, **fields):
    cert = Certificate(requirement=req, issued_on=issued_on, expires_on=expires_on, **fields)
    if upload:
        cert.file, cert.original_filename = upload, upload.name[:255]
    cert.save()
    return cert


def raise_job(action, user=None):
    from apps.maintenance.workflow import open_job

    req = action.certificate.requirement
    priority = {"high": "urgent", "medium": "routine", "low": "routine"}[action.priority]
    job = open_job(req.property, action.description[:200], user=user, priority=priority, how_reported="inspection",
                   description=f"Remedial action from the {req.kind.name.lower()} of "
                               f"{action.certificate.issued_on:%d %B %Y}.", category=_category(req.kind))
    action.job = job
    action.save(update_fields=["job", "updated_at"])
    return job


def _category(kind):
    from apps.maintenance.library import BY_CODE

    task = BY_CODE.get(kind.planned_task)
    return task[2] if task else "other"


