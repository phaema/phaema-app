# SPDX-License-Identifier: AGPL-3.0-or-later
"""Project rules: starting a project, recording gateway decisions, pausing and stopping."""
from datetime import date

from django.db import transaction
from django.utils.translation import gettext as _

from .models import GATEWAYS, GatewayDecision, Phase, Project, ProjectNote, ProjectTask, ProjectType

# Standard project types, created on install. Councils can rename them or add their own.
TYPES = [
    ("development", "Development", ProjectType.Kind.DEVELOPMENT, False,
     "Building, redeveloping or refurbishing property, often over several sites or phases."),
    ("acquisition", "Acquisition", ProjectType.Kind.ACQUISITION, True,
     "Buying land or property. The site is drawn on the map before the council owns it."),
    ("disposal", "Disposal", ProjectType.Kind.DISPOSAL, False,
     "Selling or granting a long lease of surplus property, in one or several lots."),
    ("programme", "Programme", ProjectType.Kind.PROGRAMME, False,
     "Work across many properties, such as decarbonisation or energy efficiency upgrades."),
    ("review", "Strategic review", ProjectType.Kind.REVIEW, False,
     "An options appraisal or asset review, ending in a decision."),
]

# Starter tasks for each kind of project: (phase, task).
STARTER_TASKS = {
    ProjectType.Kind.DEVELOPMENT: [
        (Phase.IDEA, "Agree the project brief and sponsor"),
        (Phase.BUSINESS_CASE, "Options appraisal and outline costs"),
        (Phase.BUSINESS_CASE, "Pre-application planning advice"),
        (Phase.BUSINESS_CASE, "Report for approval to proceed"),
        (Phase.DELIVERY, "Appoint the design team and contractor"),
        (Phase.DELIVERY, "Planning permission"),
        (Phase.DELIVERY, "Building Safety Regulator approval, if a higher-risk building"),
        (Phase.COMPLETION, "Practical completion and handover"),
        (Phase.COMPLETION, "Add the new units to the property register"),
        (Phase.CLOSE, "Final account and lessons learned"),
    ],
    ProjectType.Kind.ACQUISITION: [
        (Phase.IDEA, "Record why the council needs the site"),
        (Phase.BUSINESS_CASE, "Red Book valuation"),
        (Phase.BUSINESS_CASE, "Title and searches review"),
        (Phase.BUSINESS_CASE, "Report for approval to proceed"),
        (Phase.DELIVERY, "Agree heads of terms"),
        (Phase.DELIVERY, "Instruct legal: due diligence and contract"),
        (Phase.DELIVERY, "Exchange contracts"),
        (Phase.COMPLETION, "Complete and pay"),
        (Phase.COMPLETION, "Add the property and title to the register"),
        (Phase.CLOSE, "Classify and value the new asset for the accounts"),
    ],
    ProjectType.Kind.DISPOSAL: [
        (Phase.IDEA, "Confirm the property is surplus to requirements"),
        (Phase.BUSINESS_CASE, "Red Book valuation and best consideration (s123 Local Government Act 1972)"),
        (Phase.BUSINESS_CASE, "Report for approval to dispose"),
        (Phase.DELIVERY, "Market the property"),
        (Phase.DELIVERY, "Report on offers and select a buyer"),
        (Phase.DELIVERY, "Instruct legal and exchange contracts"),
        (Phase.COMPLETION, "Complete the sale"),
        (Phase.COMPLETION, "Mark the property as disposed of and tell finance"),
        (Phase.CLOSE, "Lessons learned"),
    ],
    ProjectType.Kind.PROGRAMME: [
        (Phase.IDEA, "Agree the programme's aims and the properties in scope"),
        (Phase.BUSINESS_CASE, "Surveys and costed plan for each property"),
        (Phase.BUSINESS_CASE, "Report for approval to proceed"),
        (Phase.DELIVERY, "Deliver the works, property by property"),
        (Phase.COMPLETION, "Confirm the work is complete at every property"),
        (Phase.CLOSE, "Final costs and benefits achieved"),
    ],
    ProjectType.Kind.REVIEW: [
        (Phase.IDEA, "Agree the scope of the review"),
        (Phase.BUSINESS_CASE, "Gather data and appraise the options"),
        (Phase.DELIVERY, "Report with recommendations"),
        (Phase.COMPLETION, "Record the decision and set up any projects that follow"),
        (Phase.CLOSE, "Close the review"),
    ],
}


def ensure_types():
    for order, (code, name, kind, confidential, description) in enumerate(TYPES):
        ProjectType.objects.get_or_create(code=code, defaults={
            "name": name, "kind": kind, "confidential_by_default": confidential, "description": description,
            "order": order})


def start(project, user):
    """Save a new project with its starter tasks. Confidentiality follows the project type unless chosen."""
    with transaction.atomic():
        project.save()
        for phase, text in STARTER_TASKS.get(project.project_type.kind, []):
            ProjectTask.objects.create(project=project, phase=phase, description=text, owner=project.lead)
    return project


def record_gateway(project, number, *, decision_maker, decided_on, outcome, reference="", notes="", report=None,
                   user=None):
    """Record a gateway decision. Approval moves the project to the next phase (gateway 4 closes it); rejection
    stops it; deferral leaves it where it is."""
    if not project.is_open:
        raise ValueError(_("The project is not open."))
    expected = project.next_gateway()
    if number != expected:
        raise ValueError(_("The next decision for this project is gateway %(n)s.") % {"n": expected})
    if outcome not in GatewayDecision.Outcome.values:
        raise ValueError(_("Choose the outcome."))
    if decided_on is None or decided_on > date.today():
        raise ValueError(_("Enter the date of the decision; it cannot be in the future."))
    with transaction.atomic():
        decision = GatewayDecision(project=project, number=number, decision_maker=decision_maker,
                                   decided_on=decided_on, outcome=outcome, reference=reference, notes=notes)
        if report:
            decision.report = report
        decision.full_clean(exclude=["project"])
        decision.save()
        _ended, opens, label, _maker = GATEWAYS[number]
        if outcome == GatewayDecision.Outcome.APPROVED:
            project.phase = opens
            if number == 4:
                project.status = Project.Status.CLOSED
        elif outcome == GatewayDecision.Outcome.REJECTED:
            project.status, project.status_reason = Project.Status.STOPPED, (notes or str(label))[:300]
        project.save()
        ProjectNote.objects.create(project=project, text=_("Gateway %(n)s (%(label)s): %(outcome)s.") % {
            "n": number, "label": label, "outcome": decision.get_outcome_display()})
    return decision


def set_status(project, status, reason=""):
    if status not in (Project.Status.ACTIVE, Project.Status.PAUSED, Project.Status.STOPPED):
        raise ValueError("Unknown status")
    if status != Project.Status.ACTIVE and not reason.strip():
        raise ValueError(_("Give a reason."))
    project.status, project.status_reason = status, reason.strip()[:300] if status != Project.Status.ACTIVE else ""
    project.save()
