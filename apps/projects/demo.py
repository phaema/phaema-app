# SPDX-License-Identifier: AGPL-3.0-or-later
"""Three fictional demonstration projects: a development, a confidential acquisition and a disposal in two lots."""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model

from . import workflow
from .models import (BudgetLine, BudgetYear, Milestone, Project, ProjectMember, ProjectParty, ProjectProperty,
                     ProjectType, Risk, financial_year_of)

NAMES = ("Northfield Business Park phase 2", "Depot site acquisition, Mill Lane",
         "Disposal of surplus land at Oak Street and Lower Farm")


def _users():
    User = get_user_model()
    return {u.username: u for u in User.objects.filter(username__startswith="demo.")}


def _gate(project, number, days_ago, today, maker="officer", reference=""):
    workflow.record_gateway(project, number, decision_maker=maker, decided_on=today - timedelta(days=days_ago),
                            outcome="approved", reference=reference)
    project.refresh_from_db()


def _budget(project, rows):
    for order, (category, description, funding, years) in enumerate(rows):
        line = BudgetLine.objects.create(project=project, category=category, description=description,
                                         funding=funding, order=order)
        for year, approved, forecast, actual in years:
            BudgetYear.objects.create(line=line, year=year, approved=Decimal(approved), forecast=Decimal(forecast),
                                      actual=Decimal(actual))


def load(today):
    from apps.leases.models import Party
    from apps.properties.models import Property

    Project.objects.filter(name__in=NAMES).delete()
    people = _users()
    fy = financial_year_of(today)
    types = {t.code: t for t in ProjectType.objects.all()}

    # 1. A development on Northfield Business Park, in its business case phase.
    lena, rob = people.get("demo.lchen"), people.get("demo.rbaker")
    dev = workflow.start(Project(
        name=NAMES[0], project_type=types["development"], lead=lena, sponsor="Director of Place",
        start_date=today - timedelta(days=120), target_date=today.replace(year=today.year + 2),
        description="Replace the Hangar block with twelve light industrial units for small businesses."), lena)
    ProjectProperty.objects.create(project=dev, property=Property.objects.get(reference="DM-N01-B01"),
                                   part=ProjectProperty.Part.DEVELOP)
    for user, role in ((rob, "surveyor"), (people.get("demo.finance"), "finance")):
        if user:
            ProjectMember.objects.create(project=dev, user=user, role=role)
    _gate(dev, 1, 90, today, reference="DD/2026/88")
    dev.tasks.filter(phase="idea").update(done_on=today - timedelta(days=95), done_by=lena)
    Milestone.objects.create(project=dev, name="Outline business case to Cabinet", order=0,
                             target_date=today + timedelta(days=35), forecast_date=today + timedelta(days=50))
    Milestone.objects.create(project=dev, name="Planning application submitted", order=1,
                             target_date=today + timedelta(days=150))
    Milestone.objects.create(project=dev, name="Start on site", order=2, target_date=today + timedelta(days=330))
    _budget(dev, [
        ("fees", "Design team fees", "capital", [(fy, 120000, 135000, 48000), (fy + 1, 60000, 60000, 0)]),
        ("works", "Construction works", "capital", [(fy + 1, 1800000, 1850000, 0), (fy + 2, 900000, 900000, 0)]),
        ("contingency", "Contingency", "capital", [(fy + 1, 150000, 150000, 0)]),
    ])
    Risk.objects.create(project=dev, description="Planning refused or delayed", likelihood=3, impact=5, owner=lena,
                        mitigation="Pre-application advice booked with the planning service.")
    Risk.objects.create(project=dev, description="Construction prices rise faster than forecast", likelihood=4,
                        impact=3, owner=people.get("demo.finance"),
                        mitigation="Contingency held; prices fixed at tender where possible.")

    # 2. A confidential acquisition: no property yet, just a proposed site.
    vendor, _created = Party.objects.get_or_create(name="Mill Lane Holdings Ltd (fictional)",
                                                   defaults={"party_type": "company"})
    acq = workflow.start(Project(
        name=NAMES[1], project_type=types["acquisition"], lead=rob, sponsor="Director of Environment",
        start_date=today - timedelta(days=200), target_date=today + timedelta(days=120), confidential=True,
        description="Buy 2.1 hectares to replace the depot at Riverside, which is at the end of its life.",
        site_address="Land north of Mill Lane\nNorthfield ZZ98 4ML", site_title_number="ZZ980777", vendor=vendor), rob)
    if people.get("demo.legal"):
        ProjectMember.objects.create(project=acq, user=people["demo.legal"], role="legal")
    if people.get("demo.head"):
        ProjectMember.objects.create(project=acq, user=people["demo.head"], role="member")
    ProjectParty.objects.create(project=acq, party=vendor, role="Vendor")
    _gate(acq, 1, 170, today)
    _gate(acq, 2, 60, today, maker="cabinet", reference="CAB/2026/31")
    acq.tasks.exclude(phase__in=("delivery", "completion", "close")).update(done_on=today - timedelta(days=65),
                                                                           done_by=rob)
    Milestone.objects.create(project=acq, name="Heads of terms agreed", order=0, target_date=today - timedelta(days=30),
                             actual_date=today - timedelta(days=34))
    Milestone.objects.create(project=acq, name="Exchange of contracts", order=1, target_date=today + timedelta(days=45))
    Milestone.objects.create(project=acq, name="Completion", order=2, target_date=today + timedelta(days=90))
    _budget(acq, [
        ("land", "Purchase price", "capital", [(fy, 650000, 640000, 0)]),
        ("fees", "Valuation, legal and survey fees", "capital", [(fy, 30000, 30000, 12500)]),
    ])

    # 3. A disposal of surplus land in two lots, being marketed.
    alex = people.get("demo.amorgan") or rob
    disp = workflow.start(Project(
        name=NAMES[2], project_type=types["disposal"], lead=alex, sponsor="Assets Board",
        start_date=today - timedelta(days=300), target_date=today + timedelta(days=200),
        description="Sell two surplus sites, each as its own lot, for best consideration."), alex)
    for ref in ("DM-S06", "DM-S10"):
        ProjectProperty.objects.create(project=disp, property=Property.objects.get(reference=ref),
                                       part=ProjectProperty.Part.DISPOSE)
    _gate(disp, 1, 260, today)
    _gate(disp, 2, 120, today, maker="board", reference="Assets Board minute 2026/07")
    Milestone.objects.create(project=disp, name="Marketing closes", order=0, target_date=today + timedelta(days=20))
    Milestone.objects.create(project=disp, name="Report on offers", order=1, target_date=today + timedelta(days=50))
    _budget(disp, [
        ("fees", "Agents' and legal fees", "revenue", [(fy, 25000, 25000, 9000)]),
        ("income", "Capital receipts", "capital", [(fy + 1, 0, 1150000, 0)]),
    ])
    Risk.objects.create(project=disp, description="Offers below the Red Book valuation", likelihood=2, impact=4,
                        owner=alex, mitigation="Reserve price set from the valuation; best consideration report.")
    return Project.objects.filter(name__in=NAMES).count()
