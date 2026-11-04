# SPDX-License-Identifier: AGPL-3.0-or-later
"""Hand over one person's work to others, for leavers, role changes and new starters.

Each kind of work is an Item: what to look for, which field names the person, and who may receive it.
Records are saved one by one (not with queryset.update) so every change is written to the audit trail.
"""
from dataclasses import dataclass, field
from typing import Callable

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from . import places
from .roles import ADMINISTRATORS, CONTRIBUTORS, SURVEYORS

STAFF = (ADMINISTRATORS, SURVEYORS)


@dataclass
class Item:
    key: str
    label: str
    hint: str
    query: Callable  # user -> queryset of records this person holds
    paths: tuple = ()  # routes from the record to a Property, for the building limit
    roles: tuple = STAFF  # who may receive it
    move: Callable = None  # (record, old, new) -> None; default sets `field`
    module: str = ""  # an optional module the receiver must be able to open (their access areas)
    field_name: str = ""
    extra: dict = field(default_factory=dict)

    def records(self, user, building=None):
        qs = self.query(user)
        if building:
            if not self.paths:
                return qs.none()
            ids = places.subtree(building)
            cond = Q()
            for path in self.paths:
                cond |= Q(**{f"{path}__in": ids})
            qs = qs.filter(cond).distinct()
        return qs

    def apply(self, record, old, new):
        if self.move:
            self.move(record, old, new)
        else:
            setattr(record, self.field_name, new)
            record.save()


def _swap_contributor(case, old, new):
    case.contributors.remove(old)
    case.contributors.add(new)


def _case_approval(approval, old, new):
    from apps.cases import workflow

    workflow.reassign_approval(approval, new)


def _supervisee(profile, old, new):
    profile.supervisor = new
    profile.save()


def items():
    from apps.cases.models import Approval, Case, CaseTask
    from apps.leases.models import LeaseEvent
    from apps.maintenance.models import Job
    from apps.properties.models import Property
    from apps.valuations.models import AuditReview

    from .models import StaffProfile

    open_case = ~Q(status=Case.Status.CLOSED)
    return [
        Item("properties", _("Properties they manage"), _("They become the managing surveyor."),
             lambda u: Property.objects.filter(managing_surveyor=u), ("pk",), field_name="managing_surveyor"),
        Item("cases", _("Open cases they own"), _("Open and on-hold cases. Closed cases keep their history."),
             lambda u: Case.objects.filter(open_case, owner=u), ("property", "lease__properties"),
             field_name="owner"),
        Item("case_tasks", _("Case tasks not yet done"), _("Tasks on any case, including other people's."),
             lambda u: CaseTask.objects.filter(owner=u, done_on__isnull=True).filter(
                 ~Q(case__status=Case.Status.CLOSED)),
             ("case__property", "case__lease__properties"), field_name="owner"),
        Item("case_approvals", _("Case approvals waiting for them"),
             _("The new approver is emailed, as when one approval is passed on."),
             lambda u: Approval.objects.filter(approver=u, status=Approval.Status.PENDING),
             ("case__property", "case__lease__properties"), move=_case_approval),
        Item("contributor", _("Open cases they contribute to"),
             _("The new person is added as a contributor in their place."),
             lambda u: Case.objects.filter(open_case, contributors=u), ("property", "lease__properties"),
             roles=STAFF + (CONTRIBUTORS,), move=_swap_contributor),
        Item("lease_events", _("Lease events assigned to them"), _("Events still to do or in progress."),
             lambda u: LeaseEvent.objects.filter(
                 assigned_to=u, status__in=(LeaseEvent.Status.OPEN, LeaseEvent.Status.IN_PROGRESS)),
             ("lease__properties",), field_name="assigned_to"),
        Item("jobs", _("Maintenance jobs they own"), _("Jobs not yet closed or cancelled."),
             lambda u: Job.objects.filter(owner=u).exclude(status__in=(Job.Status.CLOSED, Job.Status.CANCELLED)),
             ("property",), field_name="owner", module="maintenance"),
        Item("job_approvals", _("Works orders waiting for their approval"), "",
             lambda u: Job.objects.filter(approver=u, approval_status="pending"), ("property",),
             field_name="approver", module="maintenance"),
        Item("audit_reviews", _("Audit queries they are answering"), _("Valuation audit queries still open."),
             lambda u: AuditReview.objects.filter(assigned_to=u, status=AuditReview.Status.OPEN),
             ("valuation__property",), field_name="assigned_to", module="valuations"),
        Item("supervisees", _("Staff they supervise and approve for"),
             _("Not limited by building: moves everyone they supervise."),
             lambda u: StaffProfile.objects.filter(supervisor=u), (), move=_supervisee),
    ]


def candidates(roles, exclude=None):
    qs = (get_user_model().objects.filter(is_active=True)
          .filter(Q(groups__name__in=roles) | Q(is_superuser=True)).distinct()
          .order_by("first_name", "last_name", "username"))
    return qs.exclude(pk=exclude.pk) if exclude else qs


def receivers(item, exclude=None):
    """Who may receive this kind of work: the right role and, for module work, an access area that opens it."""
    from .access import can_use

    people = list(candidates(item.roles, exclude=exclude))
    return [u for u in people if can_use(u, item.module)] if item.module else people


def summary(user, building=None):
    """[(item, count, allowed receivers)] for everything this person holds."""
    return [(item, item.records(user, building).count(), receivers(item, exclude=user)) for item in items()]


@transaction.atomic
def hand_over(old, choices, building=None):
    """Move work. choices maps item key -> receiving User (missing or None = leave it).
    Returns {item key: number moved}."""
    moved = {}
    for item in items():
        new = choices.get(item.key)
        if new is None or new == old:
            continue
        if not any(u.pk == new.pk for u in receivers(item)):
            raise ValueError(f"{new} cannot receive {item.label}")
        records = list(item.records(old, building))
        for record in records:
            item.apply(record, old, new)
        if records:
            moved[item.key] = len(records)
    return moved
