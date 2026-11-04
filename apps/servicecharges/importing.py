# SPDX-License-Identifier: AGPL-3.0-or-later
"""Import service charge spending from the finance system."""
from apps.imports.engine import Column, Sheet, Workbook, to_date

from .models import CostHeading, Expenditure, Schedule, ScheduleYear


class ExpenditureSheet(Sheet):
    name, label, model, reference_field = "Expenditure", "Service charge spending", Expenditure, "description"
    deferred_kinds = ("schedule", "heading_ref")
    columns = [
        Column("Schedule", "schedule", "schedule", required=True, example="Riverside Industrial Estate services",
               guidance="The service charge schedule's name, exactly as in PHAEMA."),
        Column("Date", "spent_on", "date", required=True, example="15/05/2026",
               guidance="The date of the cost. It decides which service charge year the cost falls in."),
        Column("Heading", "heading_ref", "heading_ref", required=True, example="Landscaping and grounds",
               guidance="A cost heading's name or code, for example Cleaning or CLN."),
        Column("Supplier", "supplier", example="Example Grounds Ltd"),
        Column("Description", "description", required=True, example="Grass cutting, May"),
        Column("Invoice reference", "invoice_reference", example="INV-4471",
               guidance="The supplier's invoice or the finance system's reference. A row with a reference already in "
                        "the same year is updated, not added twice."),
        Column("Amount", "amount", "decimal", required=True, example="420.00",
               guidance="In pounds, net of any VAT the council recovers. Always positive, for income too."),
        Column("Type", "kind", "choice", example="Cost",
               guidance="Cost (the default), or Income for interest, rebates and commissions credited to the "
                        "service charge."),
        Column("Recoverable", "recoverable", "bool", example="Yes",
               guidance="No for costs the council bears itself, such as improvements. Defaults to Yes."),
        Column("Category", "category", "choice", example="Service cost",
               guidance="Service cost (the default); Building Safety Act defect (never recoverable); or Improvement "
                        "or enhancement (recoverable only if tenants agreed)."),
        Column("Tenants agreed improvement", "improvement_agreed", "bool", example="No"),
    ]

    def duplicate_key(self, values):
        ref = values.get("invoice_reference", ("", ""))[0].strip().lower()
        if not ref:
            return None
        return (values.get("schedule", ("", ""))[0].strip().lower(), ref)

    def _year(self, values):
        name = values.get("schedule", ("", ""))[0].strip()
        text, raw = values.get("spent_on", ("", None))
        schedule = Schedule.objects.filter(name__iexact=name).first()
        if not schedule or not text:
            return schedule, None
        try:
            when = to_date(raw, text)
        except ValueError:
            return schedule, None
        return schedule, schedule.years.filter(start__lte=when, end__gte=when).first()

    def find(self, values):
        _schedule, year = self._year(values)
        ref = values.get("invoice_reference", ("", ""))[0].strip()
        if year and ref:
            return Expenditure.objects.filter(year=year, invoice_reference=ref).first()
        return None

    def convert(self, column, text, raw):
        if column.kind == "schedule":
            schedule = Schedule.objects.filter(name__iexact=text.strip()).first()
            if schedule is None:
                raise ValueError(f"no service charge schedule called {text}.")
            return schedule
        if column.kind == "heading_ref":
            heading = (CostHeading.objects.filter(code__iexact=text.strip()).first()
                       or CostHeading.objects.filter(name__iexact=text.strip()).first())
            if heading is None:
                names = ", ".join(CostHeading.objects.values_list("name", flat=True))
                raise ValueError(f"'{text}' is not a cost heading. Use one of: {names}.")
            return heading
        return super().convert(column, text, raw)

    def check(self, obj, values, deferred, result):
        schedule, year = self._year(values)
        heading = deferred.pop("heading_ref", None)
        deferred.pop("schedule", None)
        if heading is not None:
            if obj.pk and obj.heading_id != heading.pk:
                result.changed.append("Heading")
            obj.heading = heading
        if obj.amount is not None and obj.amount < 0:
            result.errors.append("Amount: enter a positive amount; use Type = Income for credits.")
        if schedule and obj.spent_on and year is None:
            result.errors.append(f"Date: {schedule.name} has no service charge year covering "
                                 f"{obj.spent_on:%d/%m/%Y}. Add the year first.")
        elif year is not None:
            if year.status == ScheduleYear.Status.RECONCILED:
                result.errors.append(f"Date: the {year.label} year has been reconciled, so it cannot change.")
            obj.year = year
        result.reference = f"{obj.description[:40]} £{obj.amount}" if obj.amount is not None else obj.description

    def clean_exclude(self, obj):
        return [f for f in ("year", "heading") if getattr(obj, f"{f}_id") is None]


class ExpenditureWorkbook(Workbook):
    key, title = "expenditure", "Service charge spending"
    description = ("Costs paid by the council that are recovered through service charges, from the finance system. "
                   "Needs the service charge module to be switched on.")
    sheets = [ExpenditureSheet]
