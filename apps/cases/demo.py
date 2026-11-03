# SPDX-License-Identifier: AGPL-3.0-or-later
"""Demonstration cases on the fictional Exampleton estate."""
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db.models import Q

from apps.core.models import StaffProfile
from apps.core.roles import CONTRIBUTORS, SURVEYORS
from apps.leases.models import Lease, Party
from apps.properties.models import Property

from . import workflow
from .models import Approval, Case, CaseNote, CaseType, Correspondence

MARK = "DEMO"


def _legal_user():
    user, created = get_user_model().objects.get_or_create(
        username="demo.legal", defaults={"first_name": "Jo", "last_name": "Patel", "email": "demo.legal@example.org"})
    if created:
        user.set_unusable_password()
        user.save()
    user.groups.add(Group.objects.get(name=CONTRIBUTORS))
    return user


def _supervisor():
    """A head of estates who approves the demo surveyors' work."""
    head, created = get_user_model().objects.get_or_create(
        username="demo.head", defaults={"first_name": "Sam", "last_name": "Hughes", "email": "demo.head@example.org"})
    if created:
        head.set_unusable_password()
        head.save()
    head.groups.add(Group.objects.get(name=SURVEYORS))
    StaffProfile.objects.update_or_create(user=head, defaults={"job_title": "Head of Estates"})
    for user in get_user_model().objects.filter(username__in=("demo.amorgan", "demo.pshah", "demo.ojones")):
        StaffProfile.objects.update_or_create(user=user, defaults={"supervisor": head, "job_title": "Estates Surveyor"})
    return head


def _approval(case, head, status, recommendation, comments="", when=None):
    if case.owner_id is None or case.owner_id == head.pk:
        return
    Approval.objects.create(case=case, stage="decision", requested_by=case.owner, approver=head, status=status,
                            recommendation=recommendation, comments=comments,
                            decided_by=head if status != "pending" else None, decided_at=when)


def load(today=None):
    today = today or date.today()
    if Case.objects.filter(crm_reference__startswith=MARK).exists():
        return Case.objects.count()
    t = {c.code: c for c in CaseType.objects.all()}
    lease = {lease.reference: lease for lease in Lease.objects.filter(reference__startswith="DL-")}
    legal = _legal_user()
    head = _supervisor()

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
        _approval(c, head, "pending", "Grant consent to assign, subject to an authorised guarantee agreement from "
                                      "the outgoing tenant and a rent deposit of six months' rent from the assignee.")
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
        from django.utils import timezone

        _approval(c, head, "approved", "Approve with conditions: building regulations, contractor's insurance and "
                                       "reinstatement on request.", "Agreed. Add a condition on working hours.",
                  timezone.now() - timedelta(days=26))
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
    # 6. A new letting of a vacant unit, heads of terms part agreed with an unrepresented tenant.
    vacant = Property.objects.filter(reference="DM-E01-U08").first()
    if vacant:
        c = workflow.open_case(t["new_letting"], title="New lease of Unit 8 to a local bakery", property=vacant,
                               received_on=today - timedelta(days=35), how_received=Case.Received.EMAIL,
                               crm_reference=f"{MARK}-6")
        c.acknowledged_on, c.stage = today - timedelta(days=33), "assessing"
        c.tenant_represented, c.code_given_on = "no", today - timedelta(days=30)
        c.heads_of_terms = {
            "premises": "Unit 8, Exampleton Business Park, as edged red on the attached plan",
            "rights": "Two parking spaces in the shared car park", "term": "6 years, contracted out of the 1954 Act",
            "renewal_break": "Tenant break at year 3 on six months' notice", "security": "Three months' rent deposit",
            "rent": "£14,500 a year, quarterly in advance, excluding business rates", "vat": "VAT charged",
            "incentives": "Three months rent free from completion", "review": "Open market, upwards only, at year 3",
            "service_insurance": "Estate service charge; council insures and recharges",
            "repairs": "Internal repairing, with a schedule of condition",
        }
        c.save()
    # 7. A renewal: the tenant has served a section 26 request.
    if "DL-0004" in lease:
        served = today - timedelta(days=40)
        c = workflow.open_case(t["renewal"], title="Renewal request from Brookside Joinery", lease=lease["DL-0004"],
                               received_on=served, how_received=Case.Received.LETTER, crm_reference=f"{MARK}-7")
        c.stage, c.notice_kind, c.notice_served_on = "assessing", "s26", served
        c.acknowledged_on = served + timedelta(days=3)
        c.notice_date = served + timedelta(days=280)
        c.tenant_represented = "yes"
        from .leasing import notice_dates

        c.target_date = notice_dates(c).court_deadline
        c.save()
    # Cases for the rent reviews, breaks and expiries coming up.
    workflow.auto_open(today)
    return Case.objects.count()


def remove():
    Case.objects.filter(Q(crm_reference__startswith=MARK) | Q(lease__reference__startswith="DL-")).delete()
    get_user_model().objects.filter(username__in=("demo.legal", "demo.head"), auditentry__isnull=True).delete()
