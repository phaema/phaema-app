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
    ("insurance_certificate", "Tenant's insurance certificate", "management", 28, False, None, "", None, [
        (R, "Check the lease's insurance clause: what the tenant must insure and show"),
        (I, "Ask the tenant for a copy of the current insurance certificate or schedule"),
        (A, "Check the cover: risks, sum insured, the council's interest noted and the expiry date"),
        (C, "Add the certificate to the agreement's documents, with its expiry as the date for review")]),
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
NO_APPROVAL = {"other_event", "deposit_return", "insurance_certificate"}


HEADS_OF_TERMS = {"new_letting", "renewal"}


def default_approval(code, group):
    if code in NO_APPROVAL:
        return []
    return ["decision"] if group in APPROVAL_GROUPS or code in APPROVAL_CODES else []


# ------------------------------------------------------------------ site visit sheets
# What is printed about the property, and what to check on site. Administrators change both per case type.

EVERYTHING = ["facts", "location", "description", "services", "parking", "areas", "plans", "titles", "agreements",
              "agreement_terms", "cases"]
LEASE_VISIT = ["facts", "description", "services", "areas", "plans", "agreements", "agreement_terms", "cases"]
CONSENT_VISIT = ["facts", "description", "services", "plans", "agreements", "agreement_terms", "cases"]
LAND_VISIT = ["facts", "location", "description", "plans", "titles", "agreements", "cases"]
BRIEF_VISIT = ["facts", "description", "agreements"]

VISIT_PARTS_BY_GROUP = {"valuation": EVERYTHING, "event": LEASE_VISIT, "management": LEASE_VISIT,
                        "consent": CONSENT_VISIT, "enquiry": LAND_VISIT, "income": BRIEF_VISIT, "other": LAND_VISIT}
VISIT_PARTS_BY_CODE = {"signage": BRIEF_VISIT, "charging": BRIEF_VISIT, "insurance_certificate": BRIEF_VISIT,
                       "deposit_return": BRIEF_VISIT, "new_letting": EVERYTHING, "land_purchase": EVERYTHING}

T, YN, TX, NUM = "tick", "yes_no", "text", "number"
CONDITION = "Good, Fair, Poor, Bad"

# heading, item, guidance, answer, checks (a detail of the property record), choices
_ARRIVAL = [
    ("Arrival", "Signed in and made yourself known to the occupier", "", T, "", ""),
    ("Arrival", "Site hazards as recorded", "Note any new hazard and add it to the property record.", YN,
     "site_hazards", ""),
]
_BUILDING = [
    ("Outside", "Construction as recorded", "", YN, "construction_type", ""),
    ("Outside", "Storeys as recorded", "", YN, "storeys", ""),
    ("Outside", "Roof type and covering as recorded", "View from the ground or a safe vantage point only.", YN,
     "roof", ""),
    ("Outside", "Windows as recorded", "", YN, "window_type", ""),
    ("Outside", "Condition of roof, walls and windows", "", "choice", "", CONDITION),
    ("Outside", "Parking, yard and access as recorded", "", YN, "parking", ""),
    ("Inside", "Layout and accommodation as described", "", YN, "building_description", ""),
    ("Inside", "Services as recorded", "Gas, electricity and phase, water, drainage, heating.", YN, "services", ""),
    ("Inside", "Condition of floors, walls, ceilings and fittings", "", "choice", "", CONDITION),
]
_OCCUPATION = [
    ("Occupation", "Occupied as recorded", "Who is in occupation, and of which parts.", YN, "occupation", ""),
    ("Occupation", "Use as recorded and permitted", "", YN, "use_description", ""),
    ("Occupation", "Anyone else in occupation, or parts shared or sublet", "", YN, "", ""),
]
_PHOTOS = [("Record", "Photographs taken", "Each elevation, the roof where visible, inside, and any defects.", T,
            "", "")]

VALUATION_CHECKLIST = _ARRIVAL + _BUILDING + _OCCUPATION + [
    ("Valuation", "Floor areas check-measured", "Note the areas measured and the basis used.", TX, "floor_areas", ""),
    ("Valuation", "Alterations or extensions since the last inspection", "", YN, "", ""),
    ("Valuation", "Surroundings and neighbouring uses", "Anything that affects value: new development, vacant "
     "neighbours, access.", TX, "", ""),
    ("Valuation", "Solar panels as recorded", "", YN, "solar_pv", ""),
    ("Valuation", "Site area and boundaries as recorded", "", YN, "site_area_ha", ""),
] + _PHOTOS

LEASE_CHECKLIST = _ARRIVAL + _OCCUPATION + [
    ("Premises", "Premises as described in the agreement", "", YN, "building_description", ""),
    ("Premises", "Tenant's alterations or improvements", "Note what, and whether consent is on file.", TX, "", ""),
    ("Premises", "State of repair against the repairing obligation", "", "choice", "", CONDITION),
    ("Premises", "Breaches of covenant seen", "Use, signs, alterations, repair, nuisance.", TX, "", ""),
    ("Premises", "Floor areas check-measured", "Where the areas matter to the rent.", TX, "floor_areas", ""),
    ("Evidence", "Comparable properties nearby", "To let boards, recent lettings, vacant units.", TX, "", ""),
] + _PHOTOS

CONSENT_CHECKLIST = _ARRIVAL + _OCCUPATION + [
    ("Proposal", "What is there now", "The parts affected, as they are today.", TX, "building_description", ""),
    ("Proposal", "What is proposed matches the application", "", YN, "", ""),
    ("Proposal", "Work already started or done", "", YN, "", ""),
    ("Proposal", "Effect on structure, roof or services", "", TX, "services", ""),
    ("Proposal", "Effect on neighbours, common parts or other tenants", "", TX, "", ""),
    ("Proposal", "Other consents likely to be needed", "Planning, building regulations, superior landlord.", TX,
     "", ""),
] + _PHOTOS

CONDITION_CHECKLIST = _ARRIVAL + [
    ("Condition", "Roof and rainwater goods", "", "choice", "roof", CONDITION),
    ("Condition", "External walls, windows and doors", "", "choice", "window_type", CONDITION),
    ("Condition", "Floors, internal walls and ceilings", "", "choice", "", CONDITION),
    ("Condition", "Services and fittings", "", "choice", "services", CONDITION),
    ("Condition", "Decoration", "", "choice", "", CONDITION),
    ("Condition", "Yard, parking, fences and boundaries", "", "choice", "parking", CONDITION),
    ("Obligations", "Tenant's alterations to reinstate", "", TX, "", ""),
    ("Obligations", "Breaches seen and items for the schedule", "", TX, "", ""),
    ("Obligations", "Premises vacated and keys returned", "", YN, "occupation", ""),
] + _PHOTOS

LAND_CHECKLIST = _ARRIVAL + [
    ("On the ground", "Land or premises as recorded", "", YN, "building_description", ""),
    ("On the ground", "Boundaries on the ground match the title plan", "Note fences, walls, hedges and who appears "
     "to maintain them.", YN, "site_area_ha", ""),
    ("On the ground", "Occupation or use by anyone else", "Encroachment, storage, parking, gardens, fly-tipping.",
     TX, "occupation", ""),
    ("On the ground", "Access to the land and rights of way in use", "", TX, "", ""),
    ("On the ground", "Services, cables or pipes crossing the land", "", TX, "", ""),
    ("On the ground", "Condition and anything needing action", "", TX, "", ""),
] + _PHOTOS

CHECKLIST_BY_CODE = {
    **{c: VALUATION_CHECKLIST for c in ("asset_valuation", "impairment", "disposal_valuation")},
    **{c: LEASE_CHECKLIST for c in ("rent_review", "break", "expiry", "other_event", "renewal", "variation")},
    **{c: CONSENT_CHECKLIST for c in ("assignment", "underletting", "alterations", "change_of_use", "sharing",
                                      "signage", "planning_consent")},
    **{c: CONDITION_CHECKLIST for c in ("dilapidations", "breach", "surrender")},
    **{c: LAND_CHECKLIST for c in ("new_letting", "wayleave", "land_purchase", "encroachment", "boundary",
                                   "other_activity")},
}


# Items under these headings are repeated for each building on a site with several.
BUILDING_HEADINGS = {"Outside", "Inside", "Condition", "Premises"}


def visit_parts_for(code, group):
    return list(VISIT_PARTS_BY_CODE.get(code) or VISIT_PARTS_BY_GROUP.get(group) or LAND_VISIT)


def add_checklist(case_type, item_model):
    """Give a shipped case type its starting checklist."""
    item_model.objects.bulk_create([
        item_model(case_type=case_type, heading=heading, label=label, guidance=guidance, kind=kind, checks=checks,
                   choices=choices, each_building=heading in BUILDING_HEADINGS, order=n * 10)
        for n, (heading, label, guidance, kind, checks, choices) in enumerate(CHECKLIST_BY_CODE.get(case_type.code, []))])


def ensure_case_types():
    from .models import CaseType, CaseTypeChecklistItem, CaseTypeTask

    for i, (code, name, group, target, statutory, fee, event_type, before, tasks) in enumerate(TYPES):
        case_type, created = CaseType.objects.get_or_create(code=code, defaults={
            "name": name, "group": group, "target_days": target, "statutory_1988": statutory,
            "fee": Decimal(fee) if fee else None,  # shipped blank: councils set their own fees
            "event_type": event_type, "open_days_before": before,
            "approval_stages": default_approval(code, group),
            "heads_of_terms": code in HEADS_OF_TERMS,
            "visit_parts": visit_parts_for(code, group),
            "order": i * 10})
        if created:
            CaseTypeTask.objects.bulk_create([CaseTypeTask(case_type=case_type, stage=stage, description=text,
                                                           order=n * 10) for n, (stage, text) in enumerate(tasks)])
            add_checklist(case_type, CaseTypeChecklistItem)
