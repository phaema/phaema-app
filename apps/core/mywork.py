# SPDX-License-Identifier: AGPL-3.0-or-later
"""A surveyor's own dashboard: what needs doing now, what is coming up, and the properties they manage."""
from dataclasses import dataclass
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils.translation import gettext as _

from apps.properties.models import Property

from .models import ModuleSettings, StaffProfile
from .roles import is_administrator

AHEAD = 90  # days counted as "coming up"


@dataclass
class Item:
    when: object
    kind: str
    area: str
    title: str
    url: str
    note: str = ""


def viewable(viewer):
    """People whose dashboard this user may see: themselves, the people they supervise, and anyone for
    administrators."""
    User = get_user_model()
    if is_administrator(viewer):
        return list(User.objects.filter(is_active=True, groups__name__in=["Surveyors", "Administrators"])
                    .distinct().order_by("first_name", "last_name", "username"))
    team = [p.user for p in StaffProfile.objects.filter(supervisor=viewer, user__is_active=True)
            .select_related("user").order_by("user__first_name", "user__username")]
    return [viewer, *[u for u in team if u.pk != viewer.pk]]


def property_ids(user):
    """Properties the surveyor manages, and every part of them (a surveyor who manages an estate manages its
    units)."""
    ids = set()
    for prop in Property.objects.filter(managing_surveyor=user):
        ids.add(prop.pk)
        ids.update(prop._descendant_ids())
    return ids


def build(user, today=None, viewer=None):
    """`user` is whose work it is; `viewer` (default the same person) decides which modules appear, through their
    access areas."""
    from apps.cases.models import Case, CaseTask
    from apps.leases.models import Lease, LeaseEvent

    today = today or date.today()
    horizon = today + timedelta(days=AHEAD)
    from .access import ModulesForUser

    modules = ModulesForUser(ModuleSettings.load(), viewer or user)
    props = property_ids(user)
    now, ahead = [], []

    # Lease events assigned to them, or on their properties and assigned to nobody.
    events = (LeaseEvent.objects.filter(status__in=("open", "in_progress"), due_date__lte=horizon)
              .filter(Q(assigned_to=user) | Q(assigned_to__isnull=True, lease__properties__in=props))
              .exclude(due_date__lt=today, event_type__in=("break", "notice"))
              .select_related("lease").distinct())
    for e in events:
        title = e.display_title
        if e.time_of_essence:
            title = _("%(title)s (time is of the essence)") % {"title": title}
        item = Item(e.due_date, _("Lease event"), "leases", title, e.get_absolute_url(), e.lease.reference)
        (now if e.due_date < today else ahead).append(item)

    cases = list(Case.objects.filter(owner=user).exclude(status=Case.Status.CLOSED)
                 .select_related("case_type", "property", "lease").order_by("target_date", "pk"))
    for c in cases:
        if c.target_date and c.is_open and not c.decision_on:
            item = Item(c.target_date, _("Case target"), "cases", f"{c.display_reference} {c.title}",
                        c.get_absolute_url())
            if c.target_date < today:
                now.append(item)
            elif c.target_date <= horizon:
                ahead.append(item)
    for t in CaseTask.objects.filter(owner=user, done_on__isnull=True, due_date__isnull=False,
                                     due_date__lte=horizon, case__status__in=("open", "on_hold")).select_related("case"):
        item = Item(t.due_date, _("Case task"), "cases", t.description, t.case.get_absolute_url(),
                    t.case.display_reference)
        (now if t.due_date < today else ahead).append(item)

    # Projects: tasks they own, and the projects they lead or are on (only those the viewer may see).
    from apps.projects import rules as project_rules
    from apps.projects.models import ProjectTask

    seen = project_rules.visible(viewer or user)
    for t in ProjectTask.objects.filter(owner=user, done_on__isnull=True, due_date__isnull=False, due_date__lte=horizon,
                                        project__status__in=("active", "paused"), project__in=seen
                                        ).select_related("project"):
        item = Item(t.due_date, _("Project task"), "cases", t.description, t.project.get_absolute_url(),
                    t.project.display_reference)
        (now if t.due_date < today else ahead).append(item)
    data_projects = list(seen.filter(Q(lead=user) | Q(members__user=user), status__in=("active", "paused"))
                         .distinct().select_related("project_type").prefetch_related("milestones"))
    for p in data_projects:
        for m in p.milestones.all():
            if m.actual_date is None and m.target_date and m.target_date <= horizon:
                item = Item(m.target_date, _("Milestone"), "cases", f"{p.display_reference} {m.name}",
                            p.get_absolute_url())
                (now if m.target_date < today else ahead).append(item)

    approvals = list(Case.objects.filter(approvals__status="pending", approvals__approver=user).distinct())
    for c in approvals:
        now.append(Item(None, _("Approve"), "cases", f"{c.display_reference} {c.title}", c.get_absolute_url(),
                        _("Waiting for your approval")))

    data = {"today": today, "horizon": horizon, "cases": cases, "approvals": approvals,
            "property_count": len(props), "jobs": None, "compliance": None, "arrears": None}

    if modules.maintenance_enabled:
        from apps.maintenance.models import Job, PlannedTask

        jobs = list(Job.objects.filter(status__in=Job.OPEN).filter(Q(owner=user) | Q(property__in=props))
                    .select_related("property").distinct().order_by("target_date", "pk"))
        for j in jobs:
            if j.target_date and j.target_date < today:
                now.append(Item(j.target_date, _("Repair past target"), "buildings", j.title, j.get_absolute_url(),
                                j.property.reference))
        to_approve = list(Job.objects.filter(approval_status="pending", approver=user).select_related("property"))
        data["jobs_to_approve"] = len(to_approve)
        for job in to_approve:
            now.append(Item(None, _("Approve"), "buildings", job.title, job.get_absolute_url(),
                            _("Works order waiting for your approval")))
        for t in PlannedTask.objects.filter(active=True, property__in=props, next_due__lte=horizon) \
                .select_related("property"):
            item = Item(t.next_due, _("Statutory task") if t.statutory else _("Planned task"), "buildings", t.title,
                        t.get_absolute_url(), t.property.reference)
            (now if t.next_due < today else ahead).append(item)
        data["jobs"] = jobs

    if modules.compliance_enabled:
        from apps.compliance import workflow as compliance

        rows = compliance.statuses(compliance.requirements(property__in=props), today)
        problems = [(r, s) for r, s in rows if s[1] in ("Missing", "Expired", "Unsatisfactory", "Expires soon")]
        for r, s in problems:
            item = Item(r.latest.expires_on if r.latest else None, _("Certificate"), "buildings",
                        f"{r.kind.name}: {s[1].lower()}", r.get_absolute_url(), r.property.reference)
            (ahead if s[1] == "Expires soon" else now).append(item)
        data["compliance"] = {"total": len(rows), "problems": len(problems),
                              "valid": sum(1 for _r, s in rows if s[1] in ("Valid", "Actions open"))}

    if modules.valuation_enabled:
        from apps.valuations.models import AuditReview, Valuation

        assigned = list(Valuation.objects.filter(valuer__user=user).exclude(status="accepted").select_related("property"))
        audits = list(AuditReview.objects.filter(assigned_to=user, status="open").select_related("valuation__property"))
        data["valuations"] = {"mine": len(assigned), "audits": len(audits)}
        for v in assigned:
            ahead.append(Item(v.valuation_date, _("Valuation"), "estate", f"{v.property.reference} {v.property.name}",
                              v.get_absolute_url(), v.get_status_display()))
        for a in audits:
            now.append(Item(None, _("Audit query"), "estate", a.valuation.property.name,
                            a.valuation.get_absolute_url(), _("To answer")))

    if modules.rent_ledger_enabled:
        from apps.ledger import billing

        leases = Lease.objects.filter(properties__in=props).distinct()
        accounts = [a for a in billing.accounts(today, leases=leases) if a.overdue > 0]
        data["arrears"] = sorted(accounts, key=lambda a: -a.overdue)[:10]
        data["arrears_total"] = sum((a.overdue for a in accounts), 0)

    key = lambda i: (i.when is not None, i.when or today)  # noqa: E731 - undated items (approvals) first
    data["now"], data["ahead"] = sorted(now, key=key), sorted(ahead, key=key)
    data["properties"] = _properties(user)
    data["projects"] = data_projects
    return data


def _properties(user):
    """The properties they manage directly, with what is let and the rent."""
    from apps.leases.events import live
    from apps.leases.models import Lease

    rows = []
    for p in Property.objects.filter(managing_surveyor=user).order_by("reference")[:60]:
        ids = [p.pk, *p._descendant_ids()]
        let = live().filter(properties__in=ids, direction=Lease.Direction.OUT).distinct()
        rows.append({"property": p, "parts": len(ids) - 1, "leases": let.count(),
                     "rent": sum((lease.annual_rent or 0 for lease in let), 0)})
    return rows
