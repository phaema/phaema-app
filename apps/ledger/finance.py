# SPDX-License-Identifier: AGPL-3.0-or-later
"""The finance export: a documented, system-neutral file of charges for the council's finance system.

One row per charge or credit note. Columns are fixed (see the manual) so a finance team can map
them once into Unit4, Oracle, SAP, Civica or any other system's invoice or journal import.
"""
from collections import namedtuple

from django.db import transaction

from apps.reports.export import csv_response, xlsx_response

from .models import Charge, ExportBatch

Col = namedtuple("Col", "label type")

COLUMNS = [
    Col("Record type", "text"), Col("PHAEMA reference", "text"), Col("Invoice number", "text"),
    Col("Credit for", "text"), Col("Customer reference", "text"), Col("Customer name", "text"),
    Col("Customer address", "text"), Col("Lease reference", "text"), Col("Premises", "text"),
    Col("UPRN", "text"), Col("Description", "text"), Col("Period from", "date"), Col("Period to", "date"),
    Col("Issue date", "date"), Col("Due date", "date"), Col("Net", "money"), Col("VAT code", "text"),
    Col("VAT rate", "number"), Col("VAT", "money"), Col("Gross", "money"), Col("Income code", "text"),
]


def unexported():
    return Charge.objects.filter(export__isnull=True).select_related("lease", "lease__counterparty", "credit_for")


@transaction.atomic
def create_batch():
    """Put every charge not yet exported into a new batch. Returns the batch, or None if there is nothing new."""
    ids = list(unexported().select_for_update().values_list("pk", flat=True))
    if not ids:
        return None
    batch = ExportBatch.objects.create()
    Charge.objects.filter(pk__in=ids).update(export=batch)
    return batch


def _rows(charges, settings):
    for c in charges:
        lease, party = c.lease, c.lease.counterparty
        props = list(lease.properties.all())
        yield [
            "Credit note" if c.gross < 0 else "Invoice", f"PHC{c.pk:06d}", c.invoice_number,
            c.credit_for.reference if c.credit_for_id else "", party.finance_customer_ref, party.name,
            party.address.replace("\n", ", "), lease.reference, "; ".join(p.name for p in props),
            "; ".join(p.uprn for p in props if p.uprn), c.description, c.period_start, c.period_end,
            c.issue_date, c.due_date, c.net, settings.vat_code_standard if c.vat_rate else settings.vat_code_exempt,
            c.vat_rate, c.vat, c.gross, _income_code(c, settings),
        ]


def _income_code(charge, settings):
    source = charge.credit_for or charge
    if source.kind == Charge.Kind.SERVICE and settings.service_charge_income_code:
        return settings.service_charge_income_code
    return settings.rent_income_code


def download(batch, fmt, settings):
    charges = batch.charges.select_related("lease", "lease__counterparty", "credit_for") \
        .prefetch_related("lease__properties").order_by("pk")
    title = f"PHAEMA finance export {batch.pk}"
    if fmt == "csv":
        return csv_response(title, COLUMNS, _rows(charges, settings))
    return xlsx_response(title, COLUMNS, _rows(charges, settings), totals=True)
