# SPDX-License-Identifier: AGPL-3.0-or-later
"""Import actual project spending from the finance system, by project, budget line and financial year."""
from apps.imports.engine import Column, Sheet, Workbook

from .models import BudgetYear, Project, financial_year_label


def _project(text):
    ref = text.strip().upper().replace("PRJ-", "")
    parts = ref.split("-")
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        return None
    return Project.objects.filter(year=int(parts[0]), number=int(parts[1])).first()


def _year(text):
    """'2026/27', '2026-27' or '2026' -> 2026."""
    head = text.strip().replace("-", "/").split("/")[0]
    return int(head) if head.isdigit() and len(head) == 4 else None


class SpendSheet(Sheet):
    name, label, model, reference_field = "Spending", "Project spending", BudgetYear, "line_ref"
    deferred_kinds = ("project_ref", "line_ref", "year_ref")
    columns = [
        Column("Project", "project_ref", "project_ref", required=True, example="PRJ-2026-001",
               guidance="The project reference, as shown in PHAEMA."),
        Column("Budget line", "line_ref", "line_ref", required=True, example="Construction works",
               guidance="The budget line's description, exactly as on the project page."),
        Column("Financial year", "year_ref", "year_ref", required=True, example="2026/27",
               guidance="April to March, for example 2026/27."),
        Column("Actual", "actual", "decimal", required=True, example="182500.00",
               guidance="Total spent (or, for an income line, received) in that year, in pounds. It replaces the "
                        "figure already in PHAEMA."),
    ]

    def _line(self, values):
        project = _project(values.get("project_ref", ("", ""))[0])
        if project is None:
            return None, None
        name = values.get("line_ref", ("", ""))[0].strip()
        return project, project.budget_lines.filter(description__iexact=name).first()

    def duplicate_key(self, values):
        return tuple(values.get(k, ("", ""))[0].strip().lower() for k in ("project_ref", "line_ref", "year_ref"))

    def find(self, values):
        _project_obj, line = self._line(values)
        year = _year(values.get("year_ref", ("", ""))[0])
        if line and year:
            return BudgetYear.objects.filter(line=line, year=year).first()
        return None

    def convert(self, column, text, raw):
        if column.kind == "project_ref":
            if _project(text) is None:
                raise ValueError(f"no project {text}.")
            return text
        if column.kind == "line_ref":
            return text
        if column.kind == "year_ref":
            if _year(text) is None:
                raise ValueError(f"'{text}' is not a financial year; use the form 2026/27.")
            return _year(text)
        return super().convert(column, text, raw)

    def check(self, obj, values, deferred, result):
        project, line = self._line(values)
        year = deferred.pop("year_ref", None)
        deferred.pop("project_ref", None)
        deferred.pop("line_ref", None)
        if project is not None and line is None:
            names = ", ".join(project.budget_lines.values_list("description", flat=True)) or "none yet"
            result.errors.append(f"Budget line: {project.display_reference} has no line called "
                                 f"'{values.get('line_ref', ('', ''))[0]}'. Its lines are: {names}.")
        if line is not None:
            obj.line = line
        if year is not None:
            obj.year = year
        if obj.actual is not None and obj.actual < 0:
            result.errors.append("Actual: enter a positive amount.")
        if line is not None and year is not None:
            result.reference = f"{line.project.display_reference} {line.description} {financial_year_label(year)}"

    def clean_exclude(self, obj):
        return ["line"] if obj.line_id is None else []


class SpendWorkbook(Workbook):
    key, title = "project_spending", "Project spending"
    description = ("Actual spending and income on project budget lines, by financial year, from the finance system. "
                   "Add the budget lines on the project page first.")
    sheets = [SpendSheet]
