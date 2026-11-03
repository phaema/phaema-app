# SPDX-License-Identifier: AGPL-3.0-or-later
"""Import contractors and the component register from a spreadsheet."""
from apps.imports.engine import Column, Sheet, Workbook
from apps.properties.models import Property

from .models import Category, Component, Contractor


class ContractorSheet(Sheet):
    name, label, model, reference_field = "Contractors", "Contractors", Contractor, "name"
    columns = [
        Column("Name", "name", required=True, example="Example Roofing Ltd",
               guidance="A contractor with the same name already in PHAEMA is updated."),
        Column("Trades", "trades", example="Roofing, guttering"),
        Column("Company number", "company_number", example="01234567"),
        Column("Contact name", "contact_name"),
        Column("Email", "email", example="orders@example.org", guidance="Works orders are emailed here."),
        Column("Phone", "phone"),
        Column("Out of hours phone", "emergency_phone"),
        Column("Address", "address"),
        Column("Approved", "approved", "bool", example="Yes", guidance="Yes if on the approved list (the default)."),
        Column("Insurer", "insurer"),
        Column("Public liability cover", "public_liability", "decimal", example="5000000"),
        Column("Insurance expires", "insurance_expires", "date", example="31/03/2027"),
        Column("Accreditations", "accreditations", example="CHAS; Gas Safe 123456"),
        Column("Finance supplier reference", "finance_supplier_ref"),
    ]

    def find(self, values):
        name = values.get("name", ("", ""))[0].strip()
        return Contractor.objects.filter(name__iexact=name).first() if name else None


class ComponentSheet(Sheet):
    name, label, model, reference_field = "Components", "Components", Component, "name"
    columns = [
        Column("Property reference", "property", "property", required=True, example="DM-S07",
               guidance="The property's asset reference, exactly as in PHAEMA."),
        Column("Component", "name", required=True, example="Gas boiler 1",
               guidance="A component with the same name on the same property is updated."),
        Column("Category", "category", "choice", required=True, example="Heating, ventilation and plumbing"),
        Column("Location", "location", example="Plant room"),
        Column("Uniclass 2015", "uniclass", example="Ss_60_40_36"),
        Column("NRM3 element", "nrm3", example="5.4"),
        Column("Quantity", "quantity", "decimal", example="2"),
        Column("Unit", "unit", example="nr"),
        Column("Installed (year)", "installed_year", "int", example="2009"),
        Column("Expected life (years)", "life_years", "int", example="20"),
        Column("Condition", "condition", "choice", example="B: satisfactory, minor deterioration",
               guidance="A good, B satisfactory, C poor, D bad."),
        Column("Condition assessed", "condition_on", "date", example="01/09/2026"),
        Column("Replacement cost", "replacement_cost", "decimal", example="38000"),
        Column("Capital", "capital", "bool", example="Yes",
               guidance="Yes if replacing it is capital spending (the default), No for revenue."),
        Column("Notes", "notes"),
    ]

    def duplicate_key(self, values):
        return (values.get("property", ("", ""))[0].strip().lower(), values.get("name", ("", ""))[0].strip().lower())

    def find(self, values):
        ref, name = values.get("property", ("", ""))[0].strip(), values.get("name", ("", ""))[0].strip()
        if not ref or not name:
            return None
        return Component.objects.filter(property__reference__iexact=ref, name__iexact=name).first()

    def convert(self, column, text, raw):
        if column.kind == "property":
            prop = Property.objects.filter(reference__iexact=text.strip()).first()
            if prop is None:
                raise ValueError(f"no property with the reference {text}.")
            return prop
        if column.kind == "choice" and column.field == "condition":
            letter = text.strip()[:1].upper()
            if letter not in "ABCD":
                raise ValueError("use A, B, C or D.")
            return letter
        if column.kind == "choice" and column.field == "category":
            match = next((v for v, label in Category.choices
                          if text.strip().lower() in (v, str(label).lower())), None)
            if match is None:
                raise ValueError("use one of: " + ", ".join(str(label) for _v, label in Category.choices) + ".")
            return match
        return super().convert(column, text, raw)


class MaintenanceWorkbook(Workbook):
    key, title = "maintenance", "Contractors and components"
    description = ("Your contractors, and the component register: the roofs, boilers, lifts and other parts of each "
                   "building, with condition, life and replacement cost. Needs the maintenance module.")
    sheets = [ContractorSheet, ComponentSheet]
    optional = ("Contractors", "Components")
    notes = Workbook.notes + [
        "Either sheet can be left out. Rows are matched to existing contractors by name, and to existing components "
        "by property and name, so you can re-import a corrected file.",
    ]
