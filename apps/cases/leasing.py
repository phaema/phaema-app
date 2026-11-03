# SPDX-License-Identifier: AGPL-3.0-or-later
"""New lettings and renewals: heads of terms under the RICS Code for leasing business premises, and the
Landlord and Tenant Act 1954 notice dates."""
from dataclasses import dataclass, field
from datetime import date, timedelta

from django.utils.translation import gettext_lazy as _

from apps.core.dates import add_months

# The items the Code's mandatory part requires heads of terms to cover (RICS Code for leasing business
# premises, England and Wales, 1st edition, 2020).
ITEMS = [
    ("premises", _("Premises and extent"), _("With a plan that meets Land Registry requirements if the lease "
                                             "will be registrable.")),
    ("rights", _("Special rights"), _("Parking, rights of way, telecoms access and so on. Write \"None\" if none.")),
    ("term", _("Term and security of tenure"), _("Length of term, and whether the 1954 Act protection is "
                                                 "excluded.")),
    ("renewal_break", _("Rights to renew or break"), ""),
    ("security", _("Guarantor and rent deposit"), ""),
    ("rent", _("Rent and how it is paid"), _("Amount, frequency, and whether it excludes business rates.")),
    ("vat", _("VAT on the rent"), ""),
    ("incentives", _("Rent-free period or other incentive"), ""),
    ("review", _("Rent review: frequency and basis"), ""),
    ("service_insurance", _("Service charge and insurance"), ""),
    ("alienation", _("Assigning, subletting, charging and sharing"), ""),
    ("repairs", _("Repairing obligations"), ""),
    ("use", _("Permitted use and changes of use"), ""),
    ("alterations", _("Alterations and reinstatement"), ""),
    ("fit_out", _("Initial fit-out"), ""),
    ("conditions", _("Conditions"), _("Surveys, approvals, planning or anything else needed before "
                                      "completion.")),
]
KEYS = [k for k, _l, _h in ITEMS]


def from_lease(lease):
    """What the current agreement says, as a starting point for a renewal."""
    if lease is None:
        return {}
    money = "£{:,.2f}".format
    rent = f"{money(lease.annual_rent)} a year, {lease.get_rent_frequency_display().lower()}" \
        if lease.annual_rent is not None else ""
    if rent and not lease.rates_excluded:
        rent += ", including business rates"
    security = []
    if lease.guarantor_id:
        security.append(f"Guarantor: {lease.guarantor}")
    if lease.deposit:
        security.append(f"Deposit {money(lease.deposit)}")
    review = lease.get_review_basis_display() if lease.review_basis else ""
    if review and lease.review_interval_years:
        review += f", every {lease.review_interval_years} years"
    service = []
    if lease.service_charge_payable:
        service.append("Service charge payable")
    if lease.insurance:
        service.append(lease.get_insurance_display())
    return {
        "premises": lease.premises_description, "rights": lease.special_rights,
        "term": lease.get_security_of_tenure_display() if lease.security_of_tenure else "",
        "security": "; ".join(security), "rent": rent,
        "vat": "VAT charged" if lease.vat_chargeable else "No VAT", "incentives": lease.incentives,
        "review": review, "service_insurance": "; ".join(service), "alienation": lease.alienation,
        "repairs": lease.get_repairing_display() if lease.repairing else "", "use": lease.permitted_use,
        "alterations": lease.alterations,
    }


def answered(case):
    terms = case.heads_of_terms or {}
    return [k for k in KEYS if str(terms.get(k, "")).strip()]


def problems(case):
    """What stops a letting or renewal case moving to its decision."""
    if not case.case_type.heads_of_terms:
        return []
    out = []
    missing = [str(label) for k, label, _h in ITEMS if k not in answered(case)]
    if missing:
        out.append(_("Heads of terms not yet covered: %(items)s.") % {"items": ", ".join(missing)})
    if case.tenant_represented == "":
        out.append(_("Say whether the tenant has a professional adviser."))
    elif case.tenant_represented == "no" and not case.code_given_on:
        out.append(_("The tenant is unrepresented: record the date they were given the RICS Code and its "
                     "supplemental guide."))
    return out


@dataclass
class NoticeDates:
    counter_notice_due: date | None = None
    court_deadline: date | None = None
    warnings: list = field(default_factory=list)


def notice_dates(case):
    """Deadlines that follow from a section 25 notice or section 26 request (1954 Act, as amended in 2004)."""
    result = NoticeDates()
    if not (case.notice_kind and case.notice_served_on and case.notice_date):
        return result
    served, specified = case.notice_served_on, case.notice_date
    if not (add_months(served, 6) <= specified <= add_months(served, 12)):
        what = _("termination date") if case.notice_kind == "s25" else _("new tenancy start date")
        result.warnings.append(_("The %(what)s should be between 6 and 12 months after the notice is given.")
                               % {"what": what})
    if case.lease_id and case.lease.term_end and specified < case.lease.term_end:
        result.warnings.append(_("The date given is before the lease's contractual expiry."))
    if case.notice_kind == "s25":
        result.court_deadline = specified
    else:
        result.counter_notice_due = add_months(served, 2)
        result.court_deadline = specified - timedelta(days=1)
    return result
