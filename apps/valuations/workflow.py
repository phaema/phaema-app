# SPDX-License-Identifier: AGPL-3.0-or-later
"""Assigning valuations to staff or external valuers, and the audit process."""
from datetime import date

from django.conf import settings
from django.core.mail import send_mail

from apps.core.models import ModuleSettings
from apps.core.roles import is_administrator, manages

from .models import AuditReview, Valuation, Valuer


def staff_valuer(user):
    """The Valuer record for a member of staff, made if needed."""
    valuer = Valuer.objects.filter(user=user).first()
    if valuer is None:
        valuer = Valuer.objects.create(user=user, name=user.get_full_name() or user.username,
                                       firm=ModuleSettings.load().organisation_name, status=Valuer.Status.INTERNAL,
                                       email=user.email)
    return valuer


def can_work(user, valuation):
    return (is_administrator(user) or manages(user, valuation.property)
            or bool(valuation.valuer_id and valuation.valuer.user_id == user.pk))


def assign(valuation, valuer, by=None):
    """Give the valuation to a member of staff or an external valuer. A member of staff also takes over the case."""
    valuation.valuer = valuer
    valuation.save(update_fields=["valuer", "updated_at"])
    case = valuation.case
    if case is not None and case.status != "closed":
        if valuer.user_id:
            case.owner = valuer.user
            case.save(update_fields=["owner", "updated_at"])
        _note(case, f"Valuation assigned to {valuer} ({valuer.get_status_display().lower()})", by)
    if valuer.user_id and valuer.user != by:
        _email(valuer.user, f"Valuation assigned to you: {valuation.property.name}",
               f"You have been assigned the valuation of {valuation.property.reference} {valuation.property.name} "
               f"at {valuation.valuation_date:%d %B %Y}.", valuation)


def _note(case, text, user=None):
    from apps.cases.models import CaseNote

    note = CaseNote(case=case, text=text)
    if user is not None:
        note.created_by = user
    note.save()


def _email(user, subject, text, valuation):
    if not user or not user.email:
        return
    base = getattr(settings, "PHAEMA_BASE_URL", "").rstrip("/")
    link = f"\n\n{base}{valuation.get_absolute_url()}" if base else ""
    send_mail(f"PHAEMA: {subject}", f"Hello {user.get_full_name() or user.username},\n\n{text}{link}\n\nPHAEMA",
              settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=True)


# ------------------------------------------------------------------ audit

def accounts_year(valuation_date):
    """'2026/27' for a valuation at 31 March 2027."""
    end = valuation_date.year if valuation_date.month <= 6 else valuation_date.year + 1
    return f"{end - 1}/{str(end)[2:]}"


def flag(valuation, user, query, reason="sample", auditor="", due_on=None, assigned_to=None):
    assigned_to = assigned_to or (valuation.valuer.user if valuation.valuer_id and valuation.valuer.user_id
                                  else valuation.property.managing_surveyor)
    review = AuditReview.objects.create(valuation=valuation, accounts_year=accounts_year(valuation.valuation_date),
                                        auditor=auditor, reason=reason, query=query.strip(), due_on=due_on,
                                        assigned_to=assigned_to)
    if valuation.case_id:
        _note(valuation.case, f"Flagged for audit ({review.get_reason_display().lower()}): {review.query}", user)
    if assigned_to and assigned_to != user:
        due = f" by {due_on:%d %B %Y}" if due_on else ""
        _email(assigned_to, f"Audit query on {valuation.property.name}",
               f"The valuation of {valuation.property.name} at {valuation.valuation_date:%d %B %Y} has been flagged "
               f"for audit. Please prepare the response{due}:\n\n{review.query}", valuation)
    return review


def can_respond(user, review):
    return is_administrator(user) or review.assigned_to_id == user.pk or can_work(user, review.valuation)


def report(review, user, response, evidence=None, on=None):
    review.response = response.strip()
    if evidence:
        review.evidence = evidence
    review.status, review.reported_on, review.reported_by = AuditReview.Status.REPORTED, on or date.today(), user
    review.save()
    if review.valuation.case_id:
        _note(review.valuation.case, f"Response reported to the auditor on {review.reported_on:%d/%m/%Y}.", user)


def close(review, user, outcome, notes=""):
    review.status, review.outcome = AuditReview.Status.CLOSED, outcome
    review.closed_on, review.closed_by, review.close_notes = date.today(), user, notes.strip()
    review.save()
    v = review.valuation
    if outcome == AuditReview.Outcome.AMENDED and v.status == Valuation.Status.ACCEPTED:
        v.status, v.accepted_on, v.accepted_by = Valuation.Status.RECEIVED, None, None
        v.save(update_fields=["status", "accepted_on", "accepted_by", "updated_at"])
    if v.case_id:
        _note(v.case, f"Audit closed: {review.get_outcome_display().lower()}. {review.close_notes}".strip(), user)
