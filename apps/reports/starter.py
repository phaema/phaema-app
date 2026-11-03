# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reports PHAEMA provides out of the box. Administrators can adjust them; anyone can copy them."""

STARTERS = [
    {"starter": "rent_roll", "name": "Rent roll", "dataset": "leases",
     "description": "Live agreements let out by the council, with rent and key dates.",
     "columns": ["reference", "counterparty", "premises", "agreement_type", "term_start", "term_end",
                 "next_review_date", "annual_rent", "rent_frequency", "surveyor"],
     "filters": {"status": {"in": ["current", "holding_over"]}, "direction": {"in": ["out"]}},
     "sort_by": "annual_rent", "sort_descending": True},
    {"starter": "expiries_12m", "name": "Lease expiries in the next 12 months", "dataset": "leases",
     "description": "Live agreements whose contractual term ends within a year.",
     "columns": ["reference", "counterparty", "premises", "term_end", "security_of_tenure", "annual_rent", "surveyor"],
     "filters": {"status": {"in": ["current", "holding_over"]}, "term_end": {"next_days": 365}},
     "sort_by": "term_end"},
    {"starter": "vacant", "name": "Vacant properties", "dataset": "properties",
     "description": "Everything recorded as vacant, with floor areas.",
     "columns": ["reference", "name", "property_type", "address_line_1", "postcode", "use_description",
                 "nia_sqm", "gia_sqm", "managing_surveyor"],
     "filters": {"occupation": {"in": ["vacant"]}}, "sort_by": "reference"},
    {"starter": "overdue_events", "name": "Overdue lease events", "dataset": "events",
     "description": "Events past their due date with no outcome recorded.",
     "columns": ["due_date", "event_type", "title", "lease", "tenant", "premises", "assigned_to"],
     "filters": {"status": {"in": ["open", "in_progress"]}, "due_date": {"before_today": True}},
     "sort_by": "due_date"},
    {"starter": "terrier", "name": "Property terrier", "dataset": "properties",
     "description": "The full property register with identifiers and classification.",
     "columns": ["reference", "name", "property_type", "parent", "uprn", "address_line_1", "town", "postcode",
                 "holding_purpose", "tenure", "occupation", "gia_sqm", "nia_sqm", "site_area_ha", "titles",
                 "managing_surveyor"],
     "filters": {}, "sort_by": "reference"},
    {"starter": "tenant_contacts", "name": "Tenant contacts", "dataset": "parties",
     "description": "Contact details for everyone with a current agreement.",
     "columns": ["name", "party_type", "contact_name", "email", "phone", "address", "finance_customer_ref",
                 "n_current", "current_rent"],
     "filters": {"n_current": {"min": 1}}, "sort_by": "name"},
]


def ensure_starter_reports():
    from .models import Report

    for spec in STARTERS:
        Report.objects.get_or_create(starter=spec["starter"], defaults={**spec, "shared": True})
