# SPDX-License-Identifier: AGPL-3.0-or-later
"""Import contractors and the component register from a spreadsheet."""
from apps.imports.engine import Column, Sheet, Workbook
from apps.properties.models import Property

from .models import Category, Component, ConditionSurvey, Contractor, SurveyItem


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


class SurveyItemSheet(Sheet):
    """Work found by condition surveys, as survey firms usually deliver it: one row per item. Rows with the same
    property and survey date make up one survey, which is added as being entered for checking and finishing."""

    name, label, model, reference_field = "Survey items", "Condition survey items", SurveyItem, "property"
    deferred_kinds = ("property", "surveydate", "surveyor", "surveykind", "component")
    columns = [
        Column("Property reference", "property", "property", required=True, example="EX-001",
               guidance="The building or site surveyed."),
        Column("Survey date", "survey_date", "surveydate", required=True, example="12/05/2026",
               guidance="Rows with the same property and date are one survey."),
        Column("Surveyor", "surveyor", "surveyor", example="A Surveyor MRICS, Example Surveyors LLP",
               guidance="Needed for a new survey."),
        Column("Kind of survey", "kind", "surveykind", example="Full condition survey",
               guidance="Full condition survey (the default), Visual inspection, Desktop review or Specialist survey."),
        Column("Element", "element", "choice", required=True, example="Roof",
               guidance="The same categories as components: Roof, Structure, External walls and so on."),
        Column("Location", "location", example="Main hall"),
        Column("Work needed", "description", required=True, example="Replace failed felt covering and insulation"),
        Column("Condition", "grade", "choice", required=True, example="C", guidance="A good, B satisfactory, C poor, "
               "D bad."),
        Column("Priority", "priority", "int", required=True, example="2",
               guidance="1 urgent (within a year), 2 essential (within two years), 3 desirable (within five years), "
                        "4 long term."),
        Column("Estimated cost", "estimated_cost", "decimal", example="48000"),
        Column("Capital", "capital", "bool", example="Yes"),
        Column("Year due", "due_year", "int", example="2027", guidance="Left blank, set from the priority."),
        Column("Component", "component", "component", example="Main hall roof",
               guidance="The name of a component on the property, if the item is about one."),
    ]

    def _key(self, values):
        return (values.get("property", ("", ""))[0].strip().lower(), values.get("survey_date", ("", ""))[0],
                values.get("element", ("", ""))[0].strip().lower(),
                values.get("description", ("", ""))[0].strip().lower(), values.get("location", ("", ""))[0].lower())

    def duplicate_key(self, values):
        return self._key(values)

    def find(self, values):
        from apps.imports.engine import to_date

        ref, (text, raw) = values.get("property", ("", ""))[0].strip(), values.get("survey_date", ("", None))
        description = values.get("description", ("", ""))[0].strip()
        if not ref or not text or not description:
            return None
        try:
            when = to_date(raw, text)
        except ValueError:
            return None
        return SurveyItem.objects.filter(survey__property__reference__iexact=ref, survey__surveyed_on=when,
                                         description__iexact=description,
                                         location__iexact=values.get("location", ("", ""))[0].strip()).first()

    def convert(self, column, text, raw):
        from apps.imports.engine import choice, to_date

        if column.kind == "property":
            prop = Property.objects.filter(reference__iexact=text.strip()).first()
            if prop is None:
                raise ValueError(f"no property with the reference {text}.")
            return prop
        if column.kind == "surveydate":
            return to_date(raw, text)
        if column.kind == "surveyor":
            return text.strip()[:150]
        if column.kind == "surveykind":
            return choice(ConditionSurvey, "kind", text)
        if column.kind == "component":
            return text.strip()
        if column.field == "grade":
            letter = text.strip()[:1].upper()
            if letter not in "ABCD":
                raise ValueError("use A, B, C or D.")
            return letter
        if column.field == "element":
            match = next((v for v, label in Category.choices
                          if text.strip().lower() in (v, str(label).lower())), None)
            if match is None:
                raise ValueError("use one of: " + ", ".join(str(label) for _v, label in Category.choices) + ".")
            return match
        return super().convert(column, text, raw)

    def check(self, obj, values, deferred, result):
        if obj.priority is not None and obj.priority not in (1, 2, 3, 4):
            result.errors.append("Priority: use 1, 2, 3 or 4.")
        prop, when = deferred.get("property"), deferred.get("survey_date")
        if prop and when:
            survey = ConditionSurvey.objects.filter(property=prop, surveyed_on=when).first()
            if survey is None and not deferred.get("surveyor") and not self._surveyor_in_file(values):
                result.errors.append("Surveyor is missing (needed for a new survey).")
            if survey is not None:
                obj.survey = survey
        name = deferred.get("component")
        if name and prop:
            ids = {prop.pk} | prop._descendant_ids()
            component = Component.objects.filter(property_id__in=ids, name__iexact=name).first()
            if component is None:
                result.errors.append(f"Component: no component called {name} on {prop.reference}.")
            else:
                obj.component = component

    def _surveyor_in_file(self, values):
        """True if another row of this file for the same property and date names the surveyor."""
        key = (values.get("property", ("", ""))[0].strip().lower(), values.get("survey_date", ("", ""))[0])
        return any((v.get("property", ("", ""))[0].strip().lower(), v.get("survey_date", ("", ""))[0]) == key
                   and v.get("surveyor", ("", ""))[0].strip() for _n, v in self.context.get(self.name, []))

    def _file_surveyor(self, d):
        from apps.imports.engine import to_date

        for _n, v in self.context.get(self.name, []):
            if v.get("property", ("", ""))[0].strip().lower() != d["property"].reference.lower():
                continue
            try:
                when = to_date(v.get("survey_date", ("", None))[1], v.get("survey_date", ("", ""))[0])
            except ValueError:
                continue
            if when == d["survey_date"] and v.get("surveyor", ("", ""))[0].strip():
                return v["surveyor"][0].strip()[:150]
        return ""

    def clean_exclude(self, obj):
        return ["survey"] if obj.survey_id is None else []

    def save(self, prepared):
        obj, d = prepared.obj, prepared.deferred
        if obj.survey_id is None:
            obj.survey, _created = ConditionSurvey.objects.get_or_create(
                property=d["property"], surveyed_on=d["survey_date"],
                defaults={"surveyor": d.get("surveyor") or self._file_surveyor(d), "kind": d.get("kind")
                          or ConditionSurvey.Kind.FULL})
        obj.save()


class SurveyWorkbook(Workbook):
    key, title = "condition_surveys", "Condition surveys"
    description = ("Work found by condition surveys, one row per item, as survey firms usually supply it. Each "
                   "property and survey date becomes a survey, ready to check and finish. Needs the maintenance "
                   "module.")
    sheets = [SurveyItemSheet]
    notes = Workbook.notes + [
        "Rows are matched to existing items by property, survey date, location and work needed, so you can "
        "re-import a corrected file.",
    ]
