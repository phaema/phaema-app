# SPDX-License-Identifier: AGPL-3.0-or-later
"""The merge fields: plain text worked out from PHAEMA's records. Templates see only these strings."""
from collections import OrderedDict
from datetime import date

from apps.core.models import ModuleSettings

# key: (group, label). The order here is the order shown when a document is created.
FIELDS = OrderedDict([
    ("today", ("Letter", "Today's date")),
    ("our_ref", ("Letter", "Our reference")),
    ("your_ref", ("Letter", "Your reference")),
    ("author_name", ("Letter", "Signed by")),
    ("author_title", ("Letter", "Job title")),
    ("author_email", ("Letter", "Email")),
    ("council_name", ("Council", "Council")),
    ("department", ("Council", "Department")),
    ("council_address", ("Council", "Council's address for service")),
    ("council_phone", ("Council", "Phone")),
    ("council_email", ("Council", "Email")),
    ("addressee", ("Addressee", "Addressed to")),
    ("addressee_address", ("Addressee", "Their address")),
    ("dear", ("Addressee", "Dear")),
    ("tenant_name", ("Tenant", "Tenant")),
    ("tenant_address", ("Tenant", "Tenant's address")),
    ("tenant_company_number", ("Tenant", "Company number")),
    ("guarantor_name", ("Tenant", "Guarantor")),
    ("guarantor_address", ("Tenant", "Guarantor's address")),
    ("premises", ("Premises", "Premises")),
    ("property_name", ("Premises", "Property")),
    ("property_address", ("Premises", "Property address")),
    ("property_reference", ("Premises", "Asset reference")),
    ("uprn", ("Premises", "UPRN")),
    ("lease_reference", ("Agreement", "Agreement reference")),
    ("agreement_type", ("Agreement", "Type of agreement")),
    ("lease_date", ("Agreement", "Date of the agreement")),
    ("parties_to_lease", ("Agreement", "Original parties")),
    ("term", ("Agreement", "Term")),
    ("term_start", ("Agreement", "Term start")),
    ("term_end", ("Agreement", "Contractual expiry")),
    ("security_of_tenure", ("Agreement", "1954 Act status")),
    ("annual_rent", ("Agreement", "Current rent a year")),
    ("rent_frequency", ("Agreement", "Rent payable")),
    ("next_review_date", ("Agreement", "Next rent review")),
    ("review_basis", ("Agreement", "Review basis")),
    ("permitted_use", ("Agreement", "Permitted use")),
    ("repairing", ("Agreement", "Repairing obligation")),
    ("deposit", ("Agreement", "Rent deposit")),
    ("alienation", ("Agreement", "Assignment and subletting clause")),
    ("case_reference", ("Case", "Case reference")),
    ("case_title", ("Case", "Case")),
    ("case_type", ("Case", "Type of case")),
    ("request", ("Case", "What was asked for")),
    ("received_on", ("Case", "Application received")),
    ("application_complete_on", ("Case", "Application complete")),
    ("decision", ("Case", "Decision")),
    ("decision_on", ("Case", "Decision date")),
    ("reasons", ("Case", "Reasons and conditions")),
    ("fee", ("Case", "Council's fee")),
    ("notice_served_on", ("1954 Act", "Notice or request given")),
    ("notice_date", ("1954 Act", "Date in the notice")),
    ("counter_notice_due", ("1954 Act", "Counter-notice due")),
    ("court_deadline", ("1954 Act", "Last day to apply to court")),
    ("opposition_grounds", ("1954 Act", "Grounds of opposition")),
    ("arrears_total", ("Rent account", "Balance owed")),
    ("arrears_overdue", ("Rent account", "Overdue")),
    ("valuation_date", ("Valuation", "Valuation date")),
    ("asset_class", ("Valuation", "Asset class")),
    ("valuation_basis", ("Valuation", "Basis of value")),
    ("valuation_purpose", ("Valuation", "Purpose")),
    ("valuer_name", ("Valuation", "Valuer")),
    ("valuer_firm", ("Valuation", "Valuer's firm")),
    ("valuer_status", ("Valuation", "Valuer's status")),
    ("valuation_report_due", ("Valuation", "Report required by")),
])

# Left blank (not highlighted) when unknown, so templates can test them with {% if %}.
OPTIONAL = {"your_ref", "tenant_company_number", "guarantor_name", "guarantor_address", "uprn", "fee", "deposit",
            "reasons", "statutory_1988"}

HOT = ["premises", "rights", "term", "renewal_break", "security", "rent", "vat", "incentives", "review",
       "service_insurance", "alienation", "repairs", "use", "alterations", "fit_out", "conditions"]


def long_date(d):
    return f"{d.day} {d:%B %Y}" if d else ""


def money(amount):
    return f"£{amount:,.2f}" if amount is not None else ""


def _address(party):
    return (party.address or "").strip() if party else ""


def _user(user):
    if not user:
        return {}
    profile = getattr(user, "staff_profile", None)
    return {"author_name": user.get_full_name() or user.username, "author_email": user.email,
            "author_title": profile.job_title if profile else ""}


def _lease(lease):
    if lease is None:
        return {}
    tenant = lease.counterparty
    return {
        "lease_reference": lease.reference, "agreement_type": lease.get_agreement_type_display().lower(),
        "lease_date": long_date(lease.lease_date), "term": str(getattr(lease, "term_description", "") or ""),
        "term_start": long_date(lease.term_start), "term_end": long_date(lease.term_end),
        "security_of_tenure": lease.get_security_of_tenure_display() if lease.security_of_tenure else "",
        "annual_rent": money(lease.annual_rent), "rent_frequency": lease.get_rent_frequency_display().lower()
        if lease.rent_frequency else "", "next_review_date": long_date(lease.next_review_date),
        "review_basis": lease.get_review_basis_display() if lease.review_basis else "",
        "permitted_use": lease.permitted_use, "alienation": lease.alienation,
        "repairing": lease.get_repairing_display() if lease.repairing else "", "deposit": money(lease.deposit),
        "tenant_name": tenant.name if tenant else "", "tenant_address": _address(tenant),
        "tenant_company_number": tenant.company_number if tenant else "",
        "guarantor_name": lease.guarantor.name if lease.guarantor_id else "",
        "guarantor_address": _address(lease.guarantor) if lease.guarantor_id else "",
        "premises": lease.premises_description or "; ".join(_premises(p) for p in lease.properties.all()),
    }


def _premises(prop):
    address = prop.address
    return address if address.lower().startswith(prop.name.lower()) else f"{prop.name}, {address}".strip(", ")


def _property(prop):
    if prop is None:
        return {}
    return {"property_name": prop.name, "property_address": prop.address, "property_reference": prop.reference,
            "uprn": prop.uprn}


def _arrears(lease):
    settings = ModuleSettings.load()
    if lease is None or not settings.rent_ledger_enabled:
        return {}
    try:
        from apps.ledger.billing import account

        acc = account(lease)
        return {"arrears_total": money(acc.balance), "arrears_overdue": money(acc.overdue)}
    except Exception:  # the ledger is optional; never stop a letter for it
        return {}


def _case(case):
    from apps.cases import leasing

    data = {
        "case_reference": case.display_reference, "our_ref": case.display_reference, "case_title": case.title,
        "case_type": case.case_type.name, "request": case.case_type.name.lower(),
        "received_on": long_date(case.received_on), "application_complete_on": long_date(case.application_complete_on),
        "decision": case.get_decision_display() if case.decision else "", "decision_on": long_date(case.decision_on),
        "reasons": case.reasons, "your_ref": case.applicant_reference,
        "fee": money(case.case_type.fee) if case.case_type.fee else "",
        "statutory_1988": "yes" if case.case_type.statutory_1988 else "",
        "notice_served_on": long_date(case.notice_served_on), "notice_date": long_date(case.notice_date),
        "opposition_grounds": case.opposition_grounds,
    }
    dates = leasing.notice_dates(case)
    data["counter_notice_due"] = long_date(dates.counter_notice_due)
    data["court_deadline"] = long_date(dates.court_deadline)
    for key in HOT:
        data[f"hot_{key}"] = (case.heads_of_terms or {}).get(key, "")
    if case.party_id and not case.lease_id:
        data.update(tenant_name=case.party.name, tenant_address=_address(case.party))
    return data


def _valuation(v):
    from apps.valuations.models import ValuationSettings

    return {
        "valuation_date": long_date(v.valuation_date), "asset_class": v.asset_class.name,
        "valuation_basis": v.get_basis_display(), "valuation_purpose": v.purpose,
        "valuer_name": v.valuer.name if v.valuer else "", "valuer_firm": v.valuer.firm if v.valuer else "",
        "valuer_status": v.valuer.get_status_display().lower() if v.valuer else "",
        "addressee": v.valuer.name if v.valuer else "", "valuation_report_due": long_date(
            date(v.valuation_date.year, 4, 30)) if v.valuation_date else "",
        "council_finance_contact": ValuationSettings.load().finance_contact,
    }


def context(user=None, case=None, lease=None, prop=None, valuation=None):
    """Every merge field as a string ('' when PHAEMA does not know it)."""
    settings = ModuleSettings.load()
    if case is not None:
        lease = lease or case.lease
        prop = prop or case.main_property
    if valuation is not None:
        prop = prop or valuation.property
        case = case or valuation.case
    if lease is not None and prop is None:
        prop = lease.properties.first()
    data = {key: "" for key in FIELDS}
    data.update(today=long_date(date.today()), council_name=settings.organisation_name or "the Council",
                department=settings.department, council_address=settings.postal_address,
                council_phone=settings.letter_phone, council_email=settings.letter_email)
    data.update(_user(user))
    data.update(_property(prop))
    data.update(_lease(lease))
    data.update(_arrears(lease))
    if case is not None:
        data.update(_case(case))
    if valuation is not None:
        data.update(_valuation(valuation))
    if not data["premises"] and prop is not None:
        data["premises"] = _premises(prop)
    data["addressee"] = data["addressee"] or data["tenant_name"]
    data["addressee_address"] = data["addressee_address"] or data["tenant_address"]
    data["dear"] = "Sir or Madam"
    if lease is not None and lease.counterparty and lease.counterparty.contact_name:
        data["dear"] = lease.counterparty.contact_name
    return data
