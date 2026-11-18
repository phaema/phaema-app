# SPDX-License-Identifier: AGPL-3.0-or-later
"""A demonstration estate strategy for the fictional council: four objectives with an action plan that links the
demonstration projects and the Asset Challenge, so the board report has something to show."""
from datetime import date, timedelta

from django.contrib.auth import get_user_model

from .models import Action, EstateStrategy, Objective

TITLE = "Asset Management Strategy 2026 to 2031 (demonstration)"

PRINCIPLES = """Keep property only where a service needs it and it is fit for purpose.
Hold property for income only where it also supports the local economy or another council aim.
Share buildings with public sector partners wherever it serves residents better.
Bring every building up to EPC C by 2030 and cut the estate's carbon emissions.
Dispose of surplus property for the best consideration, or for social value where Cabinet decides."""


def load(today=None):
    from apps.cases.models import Case
    from apps.projects.demo import NAMES
    from apps.projects.models import Project

    today = today or date.today()
    users = {u.username: u for u in get_user_model().objects.filter(username__startswith="demo.")}
    existing = EstateStrategy.objects.filter(title=TITLE).first()
    if existing:  # loaded before: add anything added to the demonstration since
        first = existing.objectives.order_by("order").first()
        if first:
            _health_checks(users, today, first)
        return
    projects = {p.name: p for p in Project.objects.filter(name__in=NAMES)}
    start = date(today.year, 4, 1) if today.month >= 4 else date(today.year - 1, 4, 1)
    strategy = EstateStrategy.objects.create(
        title=TITLE, starts_on=start, ends_on=start.replace(year=start.year + 5) - timedelta(days=1), status="adopted",
        approved_by="Cabinet", approved_on=start - timedelta(days=30), minute_reference="CAB/2026/14",
        principles=PRINCIPLES)

    def objective(n, title, owner, years, **text):
        return Objective.objects.create(strategy=strategy, number=str(n), title=title, owner=users.get(owner),
                                        target_date=start.replace(year=start.year + years) - timedelta(days=1),
                                        order=n * 10, **text)

    one = objective(1, "Rationalise the operational estate", "demo.head", 3,
                    corporate_aim="A council that is efficient and well run.",
                    outcomes="Fewer, better used buildings; services sharing with partners.",
                    measures="Floor area per member of staff; buildings shared with partners; running cost saved.",
                    financial_effect="£250,000 a year less running cost by 2029.",
                    risks="Services reluctant to share; partners' timetables.",
                    reported_status="amber", progress_note="Civic centre now shared with the NHS. The depot's Asset "
                    "Challenge is under way; fleet services need only part of the yard.",
                    status_on=today - timedelta(days=20), status_by=users.get("demo.head"))
    challenge = Case.objects.filter(crm_reference="DEMO-AC-1").first()
    if challenge:
        Action.objects.create(objective=one, case=challenge, target_date=today + timedelta(days=60))
    Action.objects.create(objective=one, title="Agree a One Public Estate partnership with Exampleton Community "
                          "Health", owner=users.get("demo.head"), target_date=today - timedelta(days=200),
                          status="done")
    Action.objects.create(objective=one, title="Asset Challenge for every operational building over 1,000 m²",
                          owner=users.get("demo.ojones"), target_date=today + timedelta(days=500),
                          status="in_progress")

    two = objective(2, "Grow income from the investment estate", "demo.lchen", 5,
                    corporate_aim="A thriving local economy.",
                    outcomes="More small business units; fewer voids; rents at market levels.",
                    measures="Rent roll; void rate; rent forgone on lettings below market rent.",
                    financial_effect="£180,000 a year more rent by 2031.")
    if NAMES[0] in projects:
        Action.objects.create(objective=two, project=projects[NAMES[0]])
    Action.objects.create(objective=two, title="Review every letting below estimated rental value",
                          owner=users.get("demo.lchen"), target_date=today - timedelta(days=15),
                          status="in_progress")

    three = objective(3, "Release surplus land for housing", "demo.amorgan", 4,
                      corporate_aim="Homes people can afford.",
                      outcomes="Surplus sites sold or transferred for housing.",
                      measures="Capital receipts; homes enabled on former council land.",
                      financial_effect="£2.5 million capital receipts by 2030.",
                      reported_status="green", progress_note="Oak Street and Lower Farm are on the market.",
                      status_on=today - timedelta(days=40), status_by=users.get("demo.amorgan"))
    if NAMES[2] in projects:
        Action.objects.create(objective=three, project=projects[NAMES[2]])
    Action.objects.create(objective=three, title="Decide the future of the former bus depot",
                          owner=users.get("demo.amorgan"), target_date=today + timedelta(days=20))

    four = objective(4, "Bring council buildings up to EPC C", "demo.ojones", 4,
                     corporate_aim="Net zero by 2040.",
                     measures="Buildings at EPC C or better; energy use per m².",
                     financial_effect="£1.2 million capital, about £90,000 a year saved on energy.")
    Action.objects.create(objective=four, title="Commission energy surveys of all operational buildings",
                          owner=users.get("demo.ojones"), target_date=today + timedelta(days=120),
                          status="in_progress")
    Action.objects.create(objective=four, title="Bid to the Public Sector Decarbonisation Scheme",
                          owner=users.get("demo.ojones"), target_date=today + timedelta(days=200))
    _health_checks(users, today, one)


# Last year's finished check (answer, note) by question number, and this year's answers so far.
LAST_YEAR = {1: ("yes", ""), 2: ("partly", "Purposes recorded; asset strategies only for the investment estate."),
             3: ("no", "No rolling programme yet."), 4: ("partly", ""), 5: ("no", ""), 6: ("partly", ""),
             7: ("partly", ""), 8: ("yes", ""), 9: ("no", ""), 10: ("partly", ""), 11: ("partly", ""),
             12: ("partly", "Surveys for about half the buildings are over five years old."), 13: ("yes", ""),
             14: ("yes", ""), 15: ("no", ""), 16: ("yes", ""), 17: ("yes", ""), 18: ("partly", ""), 19: ("partly", ""),
             20: ("yes", ""), 21: ("partly", ""), 22: ("no", ""), 23: ("partly", ""), 24: ("partly", ""),
             25: ("partly", ""), 26: ("partly", ""), 27: ("na", "First year of the check.")}
THIS_YEAR = {1: ("yes", "Adopted by Cabinet, minute CAB/2026/14."), 2: ("yes", ""),
             3: ("partly", "Asset Challenge started; reviews dated for every property."), 4: ("yes", ""),
             5: ("partly", ""), 6: ("partly", "Running costs held for most buildings; capital charges not yet."),
             7: ("yes", "Property events pipeline taken to the capital board."), 8: ("yes", ""), 9: ("partly", ""),
             10: ("partly", ""), 11: ("yes", ""), 12: ("partly", ""), 13: ("yes", ""), 14: ("yes", ""),
             15: ("partly", "Property board set up; terms of reference still in draft.")}


def _health_checks(users, today, objective):
    from apps.projects.models import financial_year_of

    from . import health
    from .models import Action, HealthCheck

    head = users.get("demo.head")
    if head is None:
        return
    year = financial_year_of(today)
    if HealthCheck.objects.filter(year__in=(year - 1, year)).exists():
        return
    last = health.start(head, year - 1)
    for n, a in enumerate(last.answers.order_by("order"), start=1):
        a.answer, a.notes = LAST_YEAR.get(n, ("partly", ""))
        a.answered_by, a.answered_on = head, today - timedelta(days=330)
        a.save()
    last.status, last.finished_on = "finished", today - timedelta(days=320)
    last.summary = ("A first look at how the council manages its estate. Strong on lease management and "
                    "compliance; the gaps are a rolling review of every property, a property board and the "
                    "register's completeness.")
    last.save()
    now = health.start(head, year)
    for n, a in enumerate(now.answers.order_by("order"), start=1):
        if n in THIS_YEAR:
            a.answer, a.notes = THIS_YEAR[n]
            a.answered_by, a.answered_on = head, today - timedelta(days=5)
            if n == 15:
                a.action = Action.objects.create(objective=objective, title="Agree the property board's terms of "
                                                 "reference", owner=head, target_date=today + timedelta(days=60),
                                                 notes="From the health check")
            a.save()


def remove():
    from apps.projects.models import financial_year_of

    from .models import HealthCheck

    year = financial_year_of(date.today())
    HealthCheck.objects.filter(year__in=(year - 1, year), lead__username="demo.head").delete()
    EstateStrategy.objects.filter(title=TITLE).delete()
