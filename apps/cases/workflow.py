# SPDX-License-Identifier: AGPL-3.0-or-later
"""Opening, moving and closing cases; who may do what."""
from datetime import date, timedelta

from django.db import transaction

from apps.core.roles import CONTRIBUTORS, is_administrator, role_of, SURVEYORS
from apps.leases.models import LeaseEvent

from .models import STAGE_ORDER, Case, CaseTask, CaseType

OPEN_EVENT = (LeaseEvent.Status.OPEN, LeaseEvent.Status.IN_PROGRESS)


# ------------------------------------------------------------------ permissions

def can_work(user, case):
    """Change the case: stages, tasks, decisions, details."""
    role = role_of(user)
    if role is None:
        return False
    if is_administrator(user):
        return True
    if role != SURVEYORS:
        return False
    if case.owner_id == user.pk or case.owner_id is None:
        return True
    prop = case.main_property
    return prop is not None and prop.managing_surveyor_id == user.pk


def can_contribute(user, case):
    """Add notes, documents and correspondence."""
    if can_work(user, case):
        return True
    return role_of(user) == CONTRIBUTORS and case.contributors.filter(pk=user.pk).exists()


def sees_confidential(user, case):
    return is_administrator(user) or case.owner_id == user.pk


# ------------------------------------------------------------------ opening

@transaction.atomic
def open_case(case_type, **fields):
    """Create a case with its type's tasks and target dates."""
    case = Case(case_type=case_type, **fields)
    if case.lease_id and not case.party_id:
        case.party = case.lease.counterparty
    if case.lease_id and not case.property_id:
        case.property = case.lease.properties.first()
    if not case.owner_id and case.property_id and case.property.managing_surveyor_id:
        case.owner = case.property.managing_surveyor
    case.refresh_target()
    case.save()
    ack_due = case.acknowledge_due
    CaseTask.objects.bulk_create([
        CaseTask(case=case, stage=t.stage, description=t.description, order=t.order, owner=case.owner,
                 due_date=ack_due if t.description.startswith("Acknowledge") else None)
        for t in case_type.task_templates.all()])
    return case


def case_for_event(event, user=None):
    """Open (or return the open) case for a lease event."""
    existing = event.cases.exclude(status=Case.Status.CLOSED).first()
    if existing:
        return existing, False
    case_type = (CaseType.objects.filter(event_type=event.event_type, active=True).first()
                 or CaseType.objects.filter(code="other_event").first())
    if event.event_type == LeaseEvent.EventType.BREAK and event.source.startswith("break:"):
        # A break date's case is the one opened at its notice deadline, if there is one.
        notice = event.lease.events.filter(source=event.source.replace("break:", "notice:")).first()
        if notice and notice.cases.exclude(status=Case.Status.CLOSED).exists():
            return notice.cases.exclude(status=Case.Status.CLOSED).first(), False
    title = f"{event.display_title}: {event.lease.counterparty.name} ({event.lease.reference})"
    case = open_case(case_type, title=title[:200], lease=event.lease, event=event, owner=event.assigned_to or user,
                     how_received=Case.Received.EVENT, received_on=date.today())
    if not case.target_date:
        case.target_date = event.due_date
        case.save(update_fields=["target_date"])
    return case, True


def auto_open(today=None):
    """Open cases for lease events coming up, as each case type says. Returns the number opened."""
    today = today or date.today()
    opened = 0
    for case_type in CaseType.objects.filter(active=True, open_days_before__isnull=False).exclude(event_type=""):
        horizon = today + timedelta(days=case_type.open_days_before)
        events = (LeaseEvent.objects.filter(event_type=case_type.event_type, status__in=OPEN_EVENT,
                                            due_date__lte=horizon, lease__status__in=("current", "holding_over"))
                  .exclude(cases__isnull=False).select_related("lease", "lease__counterparty", "assigned_to"))
        for event in events:
            _case, created = case_for_event(event)
            opened += created
    return opened


# ------------------------------------------------------------------ moving and closing

def next_stage(case):
    i = STAGE_ORDER.index(case.stage)
    if i + 1 < len(STAGE_ORDER):
        case.stage = STAGE_ORDER[i + 1]
        case.save(update_fields=["stage", "updated_at"])
        return True
    return False


def close(case, outcome="", today=None):
    case.status, case.closed_on = Case.Status.CLOSED, today or date.today()
    if outcome:
        case.outcome = (case.outcome + "\n" if case.outcome else "") + outcome
    case.save(update_fields=["status", "closed_on", "outcome", "updated_at"])


def close_for_event(event):
    """When a lease event's outcome is recorded (or it lapses), close its open cases."""
    if event.status in OPEN_EVENT or not event.pk:
        return
    for case in Case.objects.filter(event=event).exclude(status=Case.Status.CLOSED):
        if not case.decision:
            case.decision = Case.Decision.NONE
        case.save(update_fields=["decision"])
        close(case, f"Lease event {event.get_status_display().lower()}: {event.outcome}".strip(": "))


@transaction.atomic
def raise_fee(case, issue_date=None):
    """Charge the case type's fixed fee on the tenant's rent account."""
    from apps.ledger.billing import _number, settings_row
    from apps.ledger.models import Charge

    if case.fee_charge_id or not case.case_type.fee or not case.lease_id:
        return None
    issue_date = issue_date or date.today()
    lease = case.lease
    rate = settings_row().vat_rate if lease.vat_chargeable else 0
    net, vat, gross = Charge.amounts(case.case_type.fee, rate)
    charge = Charge(lease=lease, kind=Charge.Kind.OTHER, issue_date=issue_date, due_date=issue_date + timedelta(days=30),
                    net=net, vat_rate=rate, vat=vat, gross=gross,
                    description=f"{case.case_type.name} fee, case {case.reference}"[:200])
    _number([charge])
    charge.save()
    case.fee_charge = charge
    case.save(update_fields=["fee_charge", "updated_at"])
    return charge
