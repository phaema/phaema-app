# SPDX-License-Identifier: AGPL-3.0-or-later
"""Import receipts from the finance system and match each one to a lease."""
import re

from apps.imports.engine import Column, Sheet, Workbook
from apps.leases.models import Lease, Party

from .models import Charge, Receipt

PHC = re.compile(r"^PHC0*(\d+)$", re.I)


def charge_for(reference):
    """The charge a quoted reference points to: a PHAEMA invoice number or a PHC reference."""
    reference = reference.strip()
    if not reference:
        return None
    found = PHC.match(reference)
    if found:
        return Charge.objects.filter(pk=int(found.group(1))).select_related("lease").first()
    return Charge.objects.filter(invoice_number__iexact=reference).select_related("lease").first()


class ReceiptSheet(Sheet):
    name, label, model, reference_field = "Receipts", "Receipts", Receipt, "payment_reference"
    deferred_kinds = ("lease", "customer")
    columns = [
        Column("Payment reference", "payment_reference", required=True, example="RCPT-000123",
               guidance="The finance system's unique reference for the payment. A payment already in PHAEMA "
                        "is not imported twice."),
        Column("Date received", "received_on", "date", required=True, example="25/03/2026"),
        Column("Amount", "amount", "decimal", required=True, example="3000.00",
               guidance="In pounds, including VAT. A negative amount records a refund or a returned payment."),
        Column("Lease reference", "lease", "lease", example="EX-L-001",
               guidance="The agreement the payment is for. If blank, PHAEMA uses the invoice reference or the "
                        "customer reference to find it."),
        Column("Invoice reference", "quoted_reference", example="PH000123",
               guidance="The invoice number or PHAEMA charge reference (PHC…) the payer quoted."),
        Column("Customer reference", "customer", "customer",
               guidance="The party's finance customer reference. Used only if the lease cannot be found another way, "
                        "and only when the customer has a single agreement."),
        Column("Notes", "notes"),
    ]

    def find(self, values):
        ref = values.get("payment_reference", ("", ""))[0]
        return Receipt.objects.filter(payment_reference=ref).first() if ref else None

    def convert(self, column, text, raw):
        if column.kind == "lease":
            lease = Lease.objects.filter(reference=text).first()
            if lease is None:
                raise ValueError(f"no agreement with reference {text}.")
            return lease
        if column.kind == "customer":
            party = Party.objects.filter(finance_customer_ref__iexact=text).first()
            if party is None:
                raise ValueError(f"no party with finance customer reference {text}.")
            return party
        return super().convert(column, text, raw)

    def check(self, obj, values, deferred, result):
        if obj.amount is not None and obj.amount == 0:
            result.errors.append("Amount: a payment cannot be £0.")
        lease = deferred.pop("lease", None)
        if lease is None and obj.quoted_reference:
            charge = charge_for(obj.quoted_reference)
            lease = charge.lease if charge else None
        party = deferred.pop("customer", None)
        if lease is None and party is not None:
            leases = list(Lease.objects.filter(counterparty=party, direction=Lease.Direction.OUT)[:2])
            if len(leases) == 1:
                lease = leases[0]
            elif leases:
                result.errors.append(f"{party.name} has more than one agreement. Add the lease reference or "
                                     "invoice reference.")
                return
        if lease is None:
            if not any("Lease reference" in e or "Customer reference" in e for e in result.errors):
                result.errors.append("Cannot tell which agreement this payment is for. Add the lease reference, "
                                     "invoice reference or customer reference.")
            return
        if obj.pk and obj.lease_id != lease.pk:
            result.changed.append("Lease reference")
        obj.lease = lease
        result.reference = f"{obj.payment_reference} → {lease.reference}"

    def clean_exclude(self, obj):
        return [] if obj.lease_id else ["lease"]


class ReceiptWorkbook(Workbook):
    key, title = "receipts", "Rent receipts"
    description = ("Payments from the finance system, matched to agreements by lease reference, invoice reference "
                   "or customer reference. Needs the rent ledger to be switched on.")
    sheets = [ReceiptSheet]
    notes = Workbook.notes + [
        "Payments are set against the oldest debt on the agreement first.",
        "Import the same file again safely: payments already in PHAEMA (same payment reference) are left alone.",
    ]
