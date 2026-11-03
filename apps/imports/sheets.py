# SPDX-License-Identifier: AGPL-3.0-or-later
"""What can be imported: parties, leases and licences, and break options."""
from apps.leases.models import BreakOption, Lease, Party
from apps.properties.models import Property

from .engine import Column, Sheet, Workbook, to_date

FILE = "file"  # marks a link to a record that is created earlier in the same file


def _file_values(context, sheet_name, field_name):
    return {values.get(field_name, ("", ""))[0].strip().lower() for _n, values in context.get(sheet_name, [])} - {""}


class PartySheet(Sheet):
    name, label, model, reference_field = "Parties", "Parties", Party, "name"
    columns = [
        Column("Name", "name", required=True, example="Example Trading Ltd",
               guidance="The party's full name. An existing party with the same name (or finance customer "
                        "reference) is updated."),
        Column("Type", "party_type", "choice", example="Company",
               guidance="Company, Limited liability partnership, Charity or community group, Public body, "
                        "Sole trader or individual, Partnership or Other. Needed for new parties."),
        Column("Company number", "company_number", example="ZZ999999"),
        Column("Charity number", "charity_number"),
        Column("Contact name", "contact_name", example="A Person"),
        Column("Email", "email", example="accounts@example.org"),
        Column("Phone", "phone", example="01632 960000"),
        Column("Address", "address", example="1 Example Street, Exampleton, ZZ99 9ZZ"),
        Column("Finance customer reference", "finance_customer_ref",
               guidance="The customer account number in the council's finance system. Used to match parties "
                        "when names differ."),
        Column("Notes", "notes"),
    ]

    def find(self, values):
        ref = values.get("finance_customer_ref", ("", ""))[0]
        if ref:
            match = Party.objects.filter(finance_customer_ref__iexact=ref).first()
            if match:
                return match
        name = values.get("name", ("", ""))[0]
        matches = list(Party.objects.filter(name__iexact=name)[:2]) if name else []
        if len(matches) > 1:
            raise ValueError(f"More than one party is called {name}. Add their finance customer reference "
                             "to say which one.")
        return matches[0] if matches else None

    def check(self, obj, values, deferred, result):
        if not obj.pk and not obj.party_type:
            result.errors.append("Type is missing (needed for a new party).")


def find_party(text, context):
    """A party already in PHAEMA, by finance customer reference or name, or one in this file's Parties sheet."""
    match = Party.objects.filter(finance_customer_ref__iexact=text).first()
    if match is None:
        matches = list(Party.objects.filter(name__iexact=text)[:2])
        if len(matches) > 1:
            raise ValueError(f"more than one party is called {text}. Use their finance customer reference.")
        match = matches[0] if matches else None
    if match:
        return match
    if text.strip().lower() in _file_values(context, "Parties", "name"):
        return (FILE, text.strip())
    raise ValueError(f"no party called {text} in PHAEMA or on the Parties sheet.")


class LeaseSheet(Sheet):
    name, label, model, reference_field = "Leases", "Leases and licences", Lease, "reference"
    deferred_kinds = ("party", "premises")
    columns = [
        Column("Reference", "reference", required=True, example="EX-L-001",
               guidance="The council's unique reference for the agreement. Existing references are updated."),
        Column("Tenant or landlord", "counterparty", "party", required=True, example="Example Trading Ltd",
               guidance="The other party: a name or finance customer reference already in PHAEMA, or a name on "
                        "this file's Parties sheet."),
        Column("Guarantor", "guarantor", "party"),
        Column("Premises", "properties", "premises", example="EX-001",
               guidance="Property references in PHAEMA, separated by semicolons. Needed for new agreements; "
                        "if filled in for an existing one, replaces its premises."),
        Column("Agreement type", "agreement_type", "choice", example="Lease",
               guidance="Lease, Licence, Tenancy at will, Agreement for lease, Farm business tenancy, Wayleave, "
                        "Easement or Concession. Needed for new agreements."),
        Column("Direction", "direction", "choice", example="Let out by the council (council is landlord)",
               guidance="Let out by the council, or Held by the council. Defaults to let out."),
        Column("Status", "status", "choice", example="Current", guidance="Proposed, Current, Holding over or Ended."),
        Column("Premises description", "premises_description", example="Ground floor shop"),
        Column("Lease date", "lease_date", "date"),
        Column("Term start", "term_start", "date", example="25/03/2024", guidance="Needed for new agreements."),
        Column("Term end", "term_end", "date", example="24/03/2034", guidance="Leave blank for periodic agreements."),
        Column("Actual end", "actual_end", "date", guidance="The date an agreement actually ended."),
        Column("Security of tenure", "security_of_tenure", "choice", example="Contracted out of the 1954 Act"),
        Column("Annual rent", "annual_rent", "decimal", example="12500",
               guidance="Rent per year in pounds. For an existing agreement with a rent schedule, change the rent "
                        "on its rent schedule instead."),
        Column("Rent frequency", "rent_frequency", "choice", example="Quarterly in advance (usual quarter days)"),
        Column("VAT chargeable", "vat_chargeable", "bool", example="Yes"),
        Column("Deposit", "deposit", "decimal"),
        Column("Review basis", "review_basis", "choice", example="Open market, upwards only"),
        Column("Review interval (years)", "review_interval_years", "int", example="5"),
        Column("Next review date", "next_review_date", "date", example="25/03/2029"),
        Column("Repairing", "repairing", "choice", example="Full repairing and insuring"),
        Column("Insurance", "insurance", "choice", example="Landlord insures and recharges"),
        Column("Service charge payable", "service_charge_payable", "bool"),
        Column("Permitted use", "permitted_use", example="Retail (Class E(a))"),
        Column("Notes", "notes"),
        Column("Rates excluded", "rates_excluded", "bool", example="Yes",
               guidance="Yes if the rent excludes business rates (the usual case)."),
        Column("Incentives", "incentives", example="Six months rent free"),
        Column("Alterations", "alterations", example="Internal non-structural alterations without consent"),
        Column("Special rights", "special_rights", example="Two parking spaces"),
        Column("Deposit held", "deposit_held"),
        Column("Deposit interest", "deposit_interest"),
    ]

    def find(self, values):
        ref = values.get("reference", ("", ""))[0]
        return Lease.objects.filter(reference=ref).first() if ref else None

    def convert(self, column, text, raw):
        if column.kind == "party":
            return find_party(text, self.context)
        if column.kind == "premises":
            refs = [r.strip() for r in text.replace(",", ";").split(";") if r.strip()]
            found = {p.reference: p for p in Property.objects.filter(reference__in=refs)}
            missing = [r for r in refs if r not in found]
            if missing:
                raise ValueError(f"no property with reference {', '.join(missing)} in PHAEMA. "
                                 "Import the properties first.")
            return [found[r] for r in refs]
        return super().convert(column, text, raw)

    def check(self, obj, values, deferred, result):
        new = obj.pk is None
        for f, heading in (("agreement_type", "Agreement type"), ("term_start", "Term start")):
            if new and not getattr(obj, f):
                result.errors.append(f"{heading} is missing (needed for a new agreement).")
        if new and "properties" not in deferred and not values.get("properties", ("", ""))[0]:
            result.errors.append("Premises is missing (needed for a new agreement).")
        tenant, guarantor = deferred.get("counterparty"), deferred.get("guarantor")
        if tenant is not None and guarantor is not None and _party_key(tenant) == _party_key(guarantor):
            result.errors.append("Guarantor: the guarantor cannot be the same party as the tenant.")
        # Links to records already in PHAEMA can be set now, so validation and change detection work.
        for f, heading in (("counterparty", "Tenant or landlord"), ("guarantor", "Guarantor")):
            value = deferred.get(f)
            if isinstance(value, Party):
                if not new and getattr(obj, f"{f}_id") == value.pk:
                    deferred.pop(f)
                    continue
                if not new:
                    result.changed.append(heading)
                setattr(obj, f, value)
                deferred.pop(f)
            elif value is not None and not new:
                result.changed.append(heading)
        if "properties" in deferred and not new:
            if {p.pk for p in deferred["properties"]} == set(obj.properties.values_list("pk", flat=True)):
                deferred.pop("properties")
            else:
                result.changed.append("Premises")
        if not new and "Annual rent" in result.changed and obj.rent_schedule.exists():
            result.errors.append("Annual rent: this agreement has a rent schedule. Change the rent there "
                                 "(add a rent step or record the review) rather than by import.")

    def clean_exclude(self, obj):
        return ["counterparty"] if obj.counterparty_id is None else []

    def save(self, prepared):
        obj, deferred = prepared.obj, prepared.deferred
        for f in ("counterparty", "guarantor"):
            value = deferred.get(f)
            if isinstance(value, tuple):
                setattr(obj, f, Party.objects.filter(name__iexact=value[1]).first())
        obj.save()
        if "properties" in deferred:
            obj.properties.set(deferred["properties"])


def _party_key(value):
    return ("pk", value.pk) if isinstance(value, Party) else ("name", value[1].lower())


class BreakSheet(Sheet):
    name, label, model, reference_field = "Breaks", "Break options", BreakOption, "lease"
    deferred_kinds = ("lease",)
    columns = [
        Column("Lease reference", "lease", "lease", required=True, example="EX-L-001",
               guidance="An agreement reference in PHAEMA or on this file's Leases sheet."),
        Column("Break date", "break_date", "date", required=True, example="25/03/2029",
               guidance="An existing break on the same agreement and date is updated."),
        Column("Exercisable by", "exercisable_by", "choice", example="Tenant only",
               guidance="Tenant only, Landlord only or Either party. Needed for new breaks."),
        Column("Notice (months)", "notice_months", "int", example="6"),
        Column("Conditions", "conditions", example="Rent paid up to date; vacant possession."),
    ]

    def _lease_ref(self, values):
        return values.get("lease", ("", ""))[0].strip()

    def duplicate_key(self, values):
        return (self._lease_ref(values).lower(), values.get("break_date", ("", ""))[0])

    def find(self, values):
        ref, (text, raw) = self._lease_ref(values), values.get("break_date", ("", None))
        if not ref or not text:
            return None
        try:
            when = to_date(raw, text)
        except ValueError:
            return None
        return BreakOption.objects.filter(lease__reference=ref, break_date=when).first()

    def convert(self, column, text, raw):
        if column.kind == "lease":
            lease = Lease.objects.filter(reference=text).first()
            if lease:
                return lease
            if text.lower() in _file_values(self.context, "Leases", "reference"):
                return (FILE, text)
            raise ValueError(f"no agreement with reference {text} in PHAEMA or on the Leases sheet.")
        return super().convert(column, text, raw)

    def check(self, obj, values, deferred, result):
        lease = deferred.get("lease")
        if isinstance(lease, Lease):
            obj.lease = lease
            deferred.pop("lease")
        if obj.pk is None and not obj.exercisable_by:
            result.errors.append("Exercisable by is missing (needed for a new break).")
        if obj.lease_id and obj.break_date and obj.lease.term_end and obj.break_date > obj.lease.term_end:
            result.errors.append("Break date: the break is after the agreement's term end.")

    def clean_exclude(self, obj):
        return ["lease"] if obj.lease_id is None else []

    def save(self, prepared):
        obj, lease = prepared.obj, prepared.deferred.get("lease")
        if isinstance(lease, tuple):
            obj.lease = Lease.objects.get(reference=lease[1])
        obj.save()


class PartyWorkbook(Workbook):
    key, title = "parties", "Parties"
    description = "Tenants, landlords, licensees and guarantors, with contact details."
    sheets = [PartySheet]


class LeaseWorkbook(Workbook):
    key, title = "leases", "Leases and licences"
    description = ("Agreements with their tenants, premises, rent and terms, and their break options. "
                   "New tenants can go on a Parties sheet in the same file.")
    sheets = [PartySheet, LeaseSheet, BreakSheet]
    notes = Workbook.notes + [
        "Sheets are imported in order: Parties, then Leases, then Breaks. You can leave out the Parties and "
        "Breaks sheets.",
        "Rents: a new agreement's annual rent becomes the first entry in its rent schedule. Key dates and "
        "reminders are created automatically from the term, reviews and breaks.",
    ]


def _workbooks():
    from apps.ledger.importing import ReceiptWorkbook
    from apps.maintenance.importing import MaintenanceWorkbook
    from apps.servicecharges.importing import ExpenditureWorkbook

    return {wb.key: wb for wb in (PartyWorkbook, LeaseWorkbook, ReceiptWorkbook, ExpenditureWorkbook,
                                  MaintenanceWorkbook)}  # in the order to import them


class _LazyWorkbooks(dict):
    """Filled on first use, so the ledger app can depend on this module without a circular import."""

    def _fill(self):
        if not self:
            self.update(_workbooks())

    def get(self, key, default=None):
        self._fill()
        return super().get(key, default)

    def values(self):
        self._fill()
        return super().values()


WORKBOOKS = _LazyWorkbooks()
