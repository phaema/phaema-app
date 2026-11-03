# SPDX-License-Identifier: AGPL-3.0-or-later
"""Demonstration cases on the fictional Exampleton estate."""
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db.models import Q

from apps.core.roles import CONTRIBUTORS
from apps.leases.models import Lease, Party
from apps.properties.models import Property

from . import workflow
from .models import Case, CaseNote, CaseType, Correspondence

MARK = "DEMO"


def _legal_user():
    user, created = get_user_model().objects.get_or_create(
        username="demo.legal", defaults={"first_name": "Jo", "last_name": "Patel", "email": "demo.legal@example.org"})
    if created:
        user.set_unusable_password()
        user.save()
    user.groups.add(Group.objects.get(name=CONTRIBUTORS))
    return user


def load(today=None):
    today = today or date.today()
    if Case.objects.filter(crm_reference__startswith=MARK).exists():
        return Case.objects.count()
    t = {c.code: c for c in CaseType.objects.all()}
    lease = {lease.reference: lease for lease in Lease.objects.filter(reference__startswith="DL-")}
    legal = _legal_user()

    def done(case, *starts):
        for task in case.tasks.all():
            if any(task.description.startswith(s) for s in starts):
                task.done_on, task.done_by = case.received_on + timedelta(days=3), case.owner
                task.save(update_fields=["done_on", "done_by"])

    # 1. Consent to assign, being assessed, with the legal team involved.
    if "DL-0005" in lease:
        days_ago = 20
        c = workflow.open_case(t["assignment"], title="Consent to assign to Exampleton Deli Co Ltd",
                               lease=lease["DL-0005"], received_on=today - timedelta(days=days_ago),
                               how_received=Case.Received.EMAIL, applicant_reference="EFF/assign/1",
                               crm_reference=f"{MARK}-1")
        c.acknowledged_on, c.application_complete_on = today - timedelta(days=17), today - timedelta(days=9)
        c.stage = "assessing"
        c.refresh_target()
        c.save()
        c.contributors.add(legal)
        done(c, "Acknowledge", "Check the lease", "Assignee", "Undertaking")
        Correspondence.objects.create(
            case=c, direction="in", method="email", on=c.received_on,
            correspondent="Exampleton Fine Foods Ltd <accounts@example.org>",
            subject="Request for consent to assign the lease of Unit 6",
            summary="We have agreed to sell our business to Exampleton Deli Co Ltd and request the council's consent "
                    "to assign the lease. Their accounts for the last two years are attached.")
        CaseNote.objects.create(case=c, text="Assignee's accounts show two years' trading; covenant looks adequate "
                                             "with a rent deposit of six months' rent.")
        CaseNote.objects.create(case=c, text="Tenant mentioned informally that the sale price depends on consent "
                                             "by the end of the month.", confidential=True)
    # 2. Licence for alterations: approved with conditions, being completed.
    if "DL-0003" in lease:
        c = workflow.open_case(t["alterations"], title="Mezzanine floor and new loading door, Unit 4",
                               lease=lease["DL-0003"], received_on=today - timedelta(days=60),
                               how_received=Case.Received.LETTER, crm_reference=f"{MARK}-2")
        c.acknowledged_on, c.application_complete_on = today - timedelta(days=55), today - timedelta(days=45)
        c.decision, c.decision_on = Case.Decision.CONDITIONS, today - timedelta(days=25)
        c.reasons = ("Approved subject to building regulations approval, works by a contractor with £5m public "
                     "liability insurance, and reinstatement at the end of the lease if the council asks.")
        c.stage = "completing"
        c.refresh_target()
        c.save()
        c.contributors.add(legal)
        done(c, "Acknowledge", "Drawings", "Contractor", "Surveyor", "Planning", "Reinstatement", "Decision")
    # 3. A filming request on the market square: just arrived, not yet acknowledged.
    square = Property.objects.filter(reference="DM-S01").first()
    c = workflow.open_case(t["other_activity"], title="Request to film a television drama in Market Square",
                           property=square, received_on=today - timedelta(days=4), how_received=Case.Received.ONLINE,
                           crm_reference=f"{MARK}-3")
    # 4. Underletting refused last spring, with reasons (shows in the consent decisions report).
    if "DL-0017" in lease:
        c = workflow.open_case(t["underletting"], title="Consent to underlet part of the first floor",
                               lease=lease["DL-0017"], received_on=today - timedelta(days=150),
                               crm_reference=f"{MARK}-4")
        c.acknowledged_on, c.application_complete_on = today - timedelta(days=146), today - timedelta(days=135)
        c.decision, c.decision_on = Case.Decision.REFUSED, today - timedelta(days=118)
        c.reasons = "The proposed underlease rent is below the passing rent, which the lease does not allow."
        c.stage, c.status, c.closed_on, c.outcome = "decision", Case.Status.CLOSED, today - timedelta(days=110), \
            "Tenant told; no further request."
        c.refresh_target()
        c.save()
    # 5. An encroachment onto the estate roads, resolved.
    roads = Property.objects.filter(reference="DM-E01-L01").first()
    party = Party.objects.filter(name="Brookside Joinery").first()
    c = workflow.open_case(t["encroachment"], title="Timber stored on the estate road verge", property=roads,
                           party=party, received_on=today - timedelta(days=95), how_received=Case.Received.PHONE,
                           crm_reference=f"{MARK}-5")
    c.stage, c.decision, c.status, c.closed_on = "completing", Case.Decision.NONE, Case.Status.CLOSED, \
        today - timedelta(days=70)
    c.outcome = "Materials removed after a letter; verge reinstated by the tenant."
    c.save()
    # Cases for the rent reviews, breaks and expiries coming up.
    workflow.auto_open(today)
    return Case.objects.count()


def remove():
    Case.objects.filter(Q(crm_reference__startswith=MARK) | Q(lease__reference__startswith="DL-")).delete()
    get_user_model().objects.filter(username="demo.legal", auditentry__isnull=True).delete()
