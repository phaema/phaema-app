# SPDX-License-Identifier: AGPL-3.0-or-later
"""The case types PHAEMA ships with. Administrators can change them and add their own."""
from decimal import Decimal

R, I, A, D, C = "received", "information", "assessing", "decision", "completing"
ACK = (R, "Acknowledge the request")

# code, name, group, target days, 1988 Act, fee, event type, open days before, tasks
TYPES = [
    ("assignment", "Consent to assign", "consent", 28, True, "", "", None, [
        ACK, (R, "Check the lease's alienation clause"),
        (I, "Assignee's details, company number and accounts or references"), (I, "Undertaking for the council's costs"),
        (A, "Covenant strength check"), (A, "Check rent arrears on the rent account"),
        (A, "Conditions needed: guarantee agreement, rent deposit"),
        (D, "Decision letter with reasons for any conditions or refusal"),
        (C, "Instruct legal: licence to assign"), (C, "Record the new tenant on the agreement")]),
    ("underletting", "Consent to underlet", "consent", 28, True, "", "", None, [
        ACK, (R, "Check the lease's alienation clause"), (I, "Undertenant's details and references"),
        (I, "Draft underlease terms: rent, term, 1954 Act status, part of premises"), (A, "Check rent and terms against the lease"),
        (D, "Decision letter with reasons for any conditions or refusal"), (C, "Instruct legal: licence to underlet"),
        (C, "Record the undertenant on the agreement")]),
    ("alterations", "Licence for alterations", "consent", 28, False, "", "", None, [
        ACK, (I, "Drawings, specification and method statement"), (I, "Contractor's insurance"),
        (A, "Surveyor's inspection"), (A, "Planning and building control check"), (A, "Reinstatement at lease end?"),
        (D, "Decision letter with conditions"), (C, "Instruct legal: licence for alterations"),
        (C, "Inspect the finished works"), (C, "Add a reinstatement event at lease expiry if required")]),
    ("change_of_use", "Change of use", "consent", 28, False, "", "", None, [
        ACK, (A, "Check the lease's user clause and the planning use class"), (A, "Consult planning"),
        (D, "Decision letter"), (C, "Update the agreement's permitted use")]),
    ("charging", "Consent to charge or mortgage", "consent", 28, True, "", "", None, [
        ACK, (I, "Lender's details and draft charge"), (D, "Decision letter"), (C, "Instruct legal")]),
    ("sharing", "Consent to share occupation", "consent", 28, True, "", "", None, [
        ACK, (I, "Details of the company sharing"), (D, "Decision letter"), (C, "Instruct legal")]),
    ("signage", "Consent for signage", "consent", 28, False, "", "", None, [
        ACK, (I, "Sign drawings and position"), (A, "Planning (advertisement consent) check"), (D, "Decision letter")]),
    ("planning_consent", "Landlord's consent to a planning application", "consent", 28, False, "", "", None, [
        ACK, (I, "Copy of the proposed application"), (A, "Consult planning and other services"), (D, "Decision letter")]),
    ("rent_review", "Rent review", "event", None, False, None, "review", 270, [
        (R, "Check the review clause, basis and timetable"), (I, "Gather rental evidence"),
        (A, "Negotiate, or refer to an independent expert or arbitrator"), (D, "Agree the new rent"),
        (C, "Record the outcome on the lease event"), (C, "Rent review memorandum signed")]),
    ("break", "Break", "event", None, False, None, "notice", 270, [
        (R, "Check break conditions and notice requirements"), (A, "Decide whether the council will serve notice, "
                                                                 "or check any notice received"),
        (D, "Record whether notice was served"), (C, "Check conditions met and vacant possession at the break date")]),
    ("expiry", "Lease expiry", "event", None, False, None, "expiry", 365, [
        (R, "Decide: renew, regain possession or allow holding over"), (A, "1954 Act position and any notices"),
        (D, "Record the decision"), (C, "Record the outcome on the lease event")]),
    ("other_event", "Other lease event", "event", None, False, None, "other", None, [(C, "Record the outcome")]),
    ("renewal", "Lease renewal (1954 Act)", "management", None, False, None, "", None, [
        (R, "Check 1954 Act status"), (A, "Section 25 or 26 notice: record the dates on the case"),
        (A, "Heads of terms covering every item the RICS Code for leasing business premises requires"), (C, "Instruct legal: new lease"), (C, "Set up the new agreement in PHAEMA")]),
    ("surrender", "Surrender", "management", None, False, None, "", None, [
        (A, "Agree terms"), (A, "Inspect the premises"), (C, "Deed of surrender"), (C, "End the agreement in PHAEMA")]),
    ("variation", "Deed of variation", "management", None, False, None, "", None, [
        (A, "Agree terms"), (C, "Instruct legal"), (C, "Update the agreement in PHAEMA")]),
    ("deposit_return", "Rent deposit return", "management", None, False, None, "", None, [
        (A, "Check rent arrears and dilapidations"), (C, "Pay out the deposit and interest")]),
    ("dilapidations", "Dilapidations", "management", None, False, None, "", None, [
        (I, "Schedule of dilapidations"), (A, "Tenant's response and negotiation"), (C, "Record the settlement")]),
    ("breach", "Breach of covenant", "management", None, False, None, "", None, [
        (R, "Inspect and record the breach"), (A, "Notify the tenant with a time to remedy"),
        (D, "Remedied, or pass to legal"), (C, "Record the outcome")]),
    ("arrears", "Rent arrears recovery", "income", None, False, None, "", None, [
        (R, "Reminder letter"), (A, "Final notice"), (D, "Payment plan, or legal action"), (C, "Record the outcome")]),
    ("sc_dispute", "Service charge query or dispute", "income", 28, False, None, "", None, [
        ACK, (A, "Review the costs and apportionment questioned"),
        (D, "Reply with the outcome; offer mediation or expert determination if unresolved"), (C, "Record the outcome")]),
    ("valuation_programme", "Annual valuation programme", "valuation", None, False, None, "", None, [
        (R, "Finance confirms the year's criteria and timetable"), (I, "Agree the list of assets to value"),
        (A, "Instruct valuers with data packs"), (D, "Valuations returned, reviewed and signed off by finance"),
        (C, "Year-end schedule sent to finance")]),
    ("asset_valuation", "Asset valuation", "valuation", None, False, None, "", None, [
        (I, "Send the data pack to the valuer"), (A, "Valuation and report received"), (D, "Reviewed and accepted"),
        (C, "Record the valuation against the asset")]),
    ("impairment", "Impairment or material change review", "valuation", None, False, None, "", None, [
        (A, "Assess the trigger"), (D, "No change, or a new valuation")]),
    ("disposal_valuation", "Disposal valuation", "valuation", None, False, None, "", None, [
        (A, "Instruct the valuation"), (D, "Valuation received"), (C, "Recorded for the disposal decision")]),
    ("new_letting", "New letting or licence application", "enquiry", None, False, None, "", None, [
        ACK, (A, "Check availability and terms"),
        (A, "Heads of terms covering every item the RICS Code for leasing business premises requires"),
        (A, "If the tenant is unrepresented, give them the Code and its supplemental guide"),
        (D, "Approval"), (C, "Instruct legal"), (C, "Set up the new agreement in PHAEMA")]),
    ("wayleave", "Wayleave or easement request", "enquiry", 56, False, "", "", None, [
        ACK, (I, "Plans and route"), (A, "Terms and consideration"), (D, "Decision"), (C, "Instruct legal")]),
    ("land_purchase", "Request to buy or lease council land", "enquiry", None, False, None, "", None, [
        ACK, (A, "Check title, use and any restrictions"), (A, "Valuation"), (D, "Disposal decision"),
        (C, "Instruct legal")]),
    ("encroachment", "Encroachment or trespass", "enquiry", None, False, None, "", None, [
        (R, "Inspect and photograph"), (A, "Title check"), (D, "Letter to the occupier"), (C, "Record the outcome")]),
    ("boundary", "Boundary query", "enquiry", 28, False, None, "", None, [ACK, (A, "Title and plan check"),
                                                                           (D, "Reply")]),
    ("enquiry", "General enquiry", "enquiry", 20, False, None, "", None, [ACK, (D, "Reply")]),
    ("other_activity", "Other activity (hoardings, filming, events and so on)", "other", 28, False, None, "", None, [
        ACK, (I, "Details, dates and insurance"), (A, "Consult other services"), (D, "Decision"),
        (C, "Licence or permission issued")]),
]


# Where a supervisor's approval is needed by default: before the decision on anything that commits the
# council (consents, settlements, disposals, lettings). Administrators change this per case type.
APPROVAL_GROUPS = {"consent", "event", "management", "valuation"}
APPROVAL_CODES = {"new_letting", "wayleave", "land_purchase", "other_activity"}
NO_APPROVAL = {"other_event", "deposit_return"}


HEADS_OF_TERMS = {"new_letting", "renewal"}


def default_approval(code, group):
    if code in NO_APPROVAL:
        return []
    return ["decision"] if group in APPROVAL_GROUPS or code in APPROVAL_CODES else []


def ensure_case_types():
    from .models import CaseType, CaseTypeTask

    for i, (code, name, group, target, statutory, fee, event_type, before, tasks) in enumerate(TYPES):
        case_type, created = CaseType.objects.get_or_create(code=code, defaults={
            "name": name, "group": group, "target_days": target, "statutory_1988": statutory,
            "fee": Decimal(fee) if fee else None,  # shipped blank: councils set their own fees
            "event_type": event_type, "open_days_before": before,
            "approval_stages": default_approval(code, group),
            "heads_of_terms": code in HEADS_OF_TERMS,
            "order": i * 10})
        if created:
            CaseTypeTask.objects.bulk_create([CaseTypeTask(case_type=case_type, stage=stage, description=text,
                                                           order=n * 10) for n, (stage, text) in enumerate(tasks)])
