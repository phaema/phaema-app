# SPDX-License-Identifier: AGPL-3.0-or-later
"""Import the valuer's returned figures."""
from apps.imports.engine import Column, Sheet, Workbook, to_date

from .models import Valuation, Valuer


class ValuationSheet(Sheet):
    name, label, model, reference_field = "Valuations", "Valuations", Valuation, "property"
    deferred_kinds = ("property_ref", "valuer_name")
    columns = [
        Column("Asset reference", "property", "property_ref", required=True, example="DM-S02",
               guidance="The property's asset reference. The row updates the valuation instructed for this "
                        "property at the valuation date."),
        Column("Valuation date", "valuation_date", "date", required=True, example="31/03/2027"),
        Column("Value", "value", "decimal", required=True, example="4250000"),
        Column("Land", "land_value", "decimal", example="850000"),
        Column("Buildings", "building_value", "decimal", example="3400000"),
        Column("Remaining life (years)", "remaining_life", "int", example="35"),
        Column("Method", "method", "choice", example="Depreciated replacement cost"),
        Column("Inspected", "inspection_date", "date", example="12/01/2027"),
        Column("Extent of inspection", "inspection", "choice", example="Full internal and external"),
        Column("Report date", "report_date", "date", example="20/02/2027"),
        Column("Valuer", "valuer", "valuer_name", example="A Valuer",
               guidance="The lead valuer's name, as recorded in PHAEMA."),
        Column("Material uncertainty", "material_uncertainty", "bool", example="No"),
        Column("Uncertainty statement", "uncertainty_statement"),
        Column("Special assumptions", "special_assumptions"),
    ]

    def duplicate_key(self, values):
        return (values.get("property", ("", ""))[0].strip().lower(), values.get("valuation_date", ("", ""))[0])

    def find(self, values):
        ref = values.get("property", ("", ""))[0].strip()
        text, raw = values.get("valuation_date", ("", None))
        if not ref or not text:
            return None
        try:
            when = to_date(raw, text)
        except ValueError:
            return None
        found = Valuation.objects.filter(property__reference__iexact=ref, valuation_date=when).first()
        if found is None:
            raise ValueError(f"no valuation of {ref} at {when:%d/%m/%Y} has been instructed in PHAEMA.")
        if found.status == Valuation.Status.ACCEPTED:
            raise ValueError(f"the valuation of {ref} at {when:%d/%m/%Y} is already accepted for the accounts.")
        return found

    def convert(self, column, text, raw):
        if column.kind == "property_ref":
            return text.strip()
        if column.kind == "valuer_name":
            valuer = Valuer.objects.filter(name__iexact=text.strip()).first()
            if valuer is None:
                raise ValueError(f"no valuer called {text} in PHAEMA.")
            return valuer
        return super().convert(column, text, raw)

    def check(self, obj, values, deferred, result):
        deferred.pop("property", None)
        valuer = deferred.pop("valuer", None)
        if valuer is not None:
            obj.valuer = valuer
        if obj.value is not None and obj.land_value is not None and obj.building_value is not None \
                and obj.land_value + obj.building_value != obj.value:
            result.errors.append("Land and buildings must add up to the value.")
        if obj.material_uncertainty and not obj.uncertainty_statement.strip():
            result.errors.append("Uncertainty statement: needed when there is material uncertainty.")
        if obj.status in (Valuation.Status.INSTRUCTED, Valuation.Status.REJECTED):
            obj.status = Valuation.Status.RECEIVED
        result.reference = f"{values.get('property', ('', ''))[0]} £{obj.value or ''}"

    def save(self, prepared):
        prepared.obj.save()


class ValuationWorkbook(Workbook):
    key, title = "valuations", "Valuer's returned figures"
    description = ("Values from the external valuer for the assets instructed in this year's programme. Needs the "
                   "asset valuation module.")
    sheets = [ValuationSheet]
    notes = Workbook.notes + [
        "Each row updates a valuation already instructed in PHAEMA (Asset valuation, Start the programme). "
        "Accepted valuations cannot be changed by import.",
    ]
