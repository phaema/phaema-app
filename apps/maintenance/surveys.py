# SPDX-License-Identifier: AGPL-3.0-or-later
"""Condition surveys: finishing a survey, raising jobs from its items, the backlog and the survey programme."""
from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Max, Q

from . import workflow
from .models import ConditionSurvey, Job, SurveyItem

SURVEYED_TYPES = ("building", "site", "estate")  # what the survey programme lists, with anything already surveyed
GRADE_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3}


@transaction.atomic
def finish(survey, update_components=True):
    """Close the survey: the property takes its overall grade and date, and, if asked, each component named on an
    item takes the worst grade found for it."""
    survey.status, survey.finished_on = ConditionSurvey.Status.FINISHED, date.today()
    survey.save(update_fields=["status", "finished_on", "updated_at"])
    prop = survey.property
    latest = prop.condition_surveys.filter(status=ConditionSurvey.Status.FINISHED).order_by("-surveyed_on").first()
    if survey.overall_grade and latest == survey:
        prop.condition_grade, prop.condition_surveyed_on = survey.overall_grade, survey.surveyed_on
        prop.save()
    changed = 0
    if update_components:
        worst = {}
        for item in survey.items.exclude(component=None).select_related("component"):
            current = worst.get(item.component_id)
            if current is None or GRADE_ORDER[item.grade] > GRADE_ORDER[current[1]]:
                worst[item.component_id] = (item.component, item.grade)
        for component, grade in worst.values():
            if component.condition_on and component.condition_on > survey.surveyed_on:
                continue  # graded more recently than this survey
            component.condition, component.condition_on = grade, survey.surveyed_on
            component.save()
            changed += 1
    return changed


def raise_job(item, user):
    """A job for one survey item, linked to it so the item shows as done when the job is completed."""
    if item.job_id and item.job.status != Job.Status.CANCELLED:
        raise ValueError("A job has already been raised for this item.")
    survey = item.survey
    detail = [item.description]
    if item.location:
        detail.append(f"Location: {item.location}.")
    detail.append(f"From the {survey.get_kind_display().lower()} on {survey.surveyed_on:%d %B %Y} by "
                  f"{survey.surveyor}: condition {item.grade}, priority {item.priority}.")
    job = workflow.open_job(
        survey.property, f"{item.get_element_display()}: {item.description}"[:200], user=user,
        category=item.element, priority=item.job_priority(), how_reported=Job.Reported.INSPECTION,
        estimate=item.estimated_cost, component=item.component, description="\n".join(detail))
    item.job = job
    item.save(update_fields=["job", "updated_at"])
    return job


def open_items(qs=None):
    """Items still to do: open, and not covered by a completed job."""
    qs = SurveyItem.objects.all() if qs is None else qs
    done = Q(job__status__in=[Job.Status.COMPLETED, Job.Status.CLOSED])
    return qs.filter(state=SurveyItem.State.OPEN).exclude(done)


def backlog(items):
    """Totals for a set of open items: by priority, by element and by year due. Backlog maintenance is the work of
    priorities 1 to 3; priority 4 is shown beside it."""
    by_priority = {p: {"count": 0, "cost": Decimal("0")} for p, _l in SurveyItem.Priority.choices}
    by_element = defaultdict(lambda: Decimal("0"))
    by_year = defaultdict(lambda: Decimal("0"))
    this_year = date.today().year
    for item in items:
        cost = item.estimated_cost or Decimal("0")
        by_priority[item.priority]["count"] += 1
        by_priority[item.priority]["cost"] += cost
        if item.priority in SurveyItem.BACKLOG:
            by_element[item.get_element_display()] += cost
        by_year[max(item.due_year or this_year, this_year)] += cost
    total = sum((by_priority[p]["cost"] for p in SurveyItem.BACKLOG), Decimal("0"))
    return {"by_priority": [(p, label, by_priority[p]["count"], by_priority[p]["cost"])
                            for p, label in SurveyItem.Priority.choices],
            "by_element": sorted(by_element.items(), key=lambda kv: -kv[1]),
            "by_year": by_year, "total": total}


def programme(properties):
    """Each property's last finished survey, when the next is due, and whether it is overdue or never surveyed."""
    today = date.today()
    props = (properties.filter(Q(property_type__in=SURVEYED_TYPES, parent=None) | Q(property_type="building")
                               | Q(condition_surveys__isnull=False))
             .distinct().annotate(last=Max("condition_surveys__surveyed_on",
                                           filter=Q(condition_surveys__status="finished")))
             .order_by("reference"))
    latest = {}
    for s in ConditionSurvey.objects.filter(property__in=props, status=ConditionSurvey.Status.FINISHED) \
            .order_by("property_id", "-surveyed_on"):
        latest.setdefault(s.property_id, s)
    rows = []
    for p in props:
        survey = latest.get(p.pk)
        due = survey.next_due if survey else None
        if survey is None:
            state = "never"
        elif due and due < today:
            state = "overdue"
        elif due and (due - today).days <= 365:
            state = "due"
        else:
            state = "ok"
        rows.append({"property": p, "survey": survey, "due": due, "state": state})
    return rows


def property_summary(prop):
    """For the property's maintenance page: its surveys and its own open items."""
    items = list(open_items(SurveyItem.objects.filter(survey__property=prop)).select_related("survey", "job"))
    return {"surveys": list(prop.condition_surveys.all()[:10]),
            "open_items": items,
            "backlog": sum((i.estimated_cost or 0 for i in items if i.priority in SurveyItem.BACKLOG), 0)}

