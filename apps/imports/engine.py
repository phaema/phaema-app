# SPDX-License-Identifier: AGPL-3.0-or-later
"""A small engine for importing records from Excel or CSV.

A workbook import is made of sheets. Each sheet lists its columns and how a row finds an
existing record. Every row on every sheet is checked first and nothing is saved unless the
whole file is clean; then the sheets are saved in order inside one transaction, so a later
sheet (e.g. Breaks) can refer to records created by an earlier one (e.g. Leases).
"""
import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

YES = ("yes", "y", "true", "1")
NO = ("no", "n", "false", "0")


@dataclass
class Column:
    heading: str
    field: str
    kind: str = "text"  # text, choice, decimal, int, date, bool, user, or a sheet-specific kind
    required: bool = False
    guidance: str = ""
    example: str = ""


@dataclass
class RowResult:
    sheet: str
    number: int
    reference: str
    action: str = "create"  # create, update, unchanged
    changed: list = field(default_factory=list)
    errors: list = field(default_factory=list)


@dataclass
class Prepared:
    obj: object
    deferred: dict  # values that need other records saved first (e.g. links to other rows)
    result: RowResult


class ImportResult:
    def __init__(self, sheets):
        self.sheets = sheets  # [(Sheet, [RowResult])]

    @property
    def rows(self):
        return [r for _s, rows in self.sheets for r in rows]

    @property
    def ok(self):
        return bool(self.rows) and not any(r.errors for r in self.rows)

    @property
    def error_count(self):
        return sum(1 for r in self.rows if r.errors)

    def summary(self):
        """[(sheet label, created, updated, unchanged)]"""
        out = []
        for sheet, rows in self.sheets:
            good = [r for r in rows if not r.errors]
            out.append((sheet.label, sum(r.action == "create" for r in good), sum(r.action == "update" for r in good),
                        sum(r.action == "unchanged" for r in good)))
        return out


class Sheet:
    """One kind of record. Subclasses set the attributes and override the hooks they need."""
    name = ""          # worksheet name
    label = ""         # plural, for messages
    model = None
    columns = []
    reference_field = ""  # which value identifies the row in messages

    def __init__(self, context):
        self.context = context  # shared between sheets in one workbook (e.g. references in the file)

    # ---- hooks
    def find(self, values):
        """Return the existing record this row updates, or None."""
        raise NotImplementedError

    def new(self, values):
        return self.model()

    def convert(self, column, text, raw):
        """Turn a cell into a value. Raise ValueError with a plain-English message if it is wrong."""
        kind = column.kind
        if kind == "text":
            return text
        if kind == "choice":
            return choice(self.model, column.field, text)
        if kind == "decimal":
            return to_decimal(text)
        if kind == "int":
            cleaned = text.replace(",", "")
            if not cleaned.isdigit():
                raise ValueError(f"{text} is not a whole number.")
            return int(cleaned)
        if kind == "date":
            return to_date(raw, text)
        if kind == "bool":
            return to_bool(text)
        if kind == "user":
            return find_user(text)
        raise ValueError(f"unknown column type {kind}")

    def check(self, obj, values, deferred, result):
        """Extra checks across columns. Add messages to result.errors."""

    def clean_exclude(self, obj):
        return []

    def save(self, prepared):
        prepared.obj.save()

    # ---- engine
    def column(self, field_name):
        return next(c for c in self.columns if c.field == field_name)

    def validate(self, rows):
        results, prepared, seen = [], [], {}
        for number, values in rows:
            ref = values.get(self.reference_field, ("", ""))[0]
            result = RowResult(self.label, number, ref)
            key = self.duplicate_key(values)
            if key and key in seen:
                result.errors.append(f"This row repeats row {seen[key]}.")
            elif key:
                seen[key] = number
            for c in self.columns:
                if c.required and not values.get(c.field, ("", ""))[0]:
                    result.errors.append(f"{c.heading} is missing.")
            obj = None
            try:
                obj = self.find(values)
            except ValueError as exc:
                result.errors.append(str(exc))
            if obj is None:
                obj = self.new(values)
            else:
                result.action = "update"
            deferred = {}
            for c in self.columns:
                text, raw = values.get(c.field, ("", None))
                if text == "":
                    continue
                try:
                    value = self.convert(c, text, raw)
                except ValueError as exc:
                    result.errors.append(f"{c.heading}: {exc}")
                    continue
                if c.kind in self.deferred_kinds:
                    deferred[c.field] = value
                    continue
                current = getattr(obj, c.field, None)
                if obj.pk and not same(current, value):
                    result.changed.append(c.heading)
                setattr(obj, c.field, value)
            self.check(obj, values, deferred, result)
            if not result.errors:
                try:
                    obj.full_clean(exclude=self.clean_exclude(obj), validate_unique=not obj.pk)
                except ValidationError as exc:
                    for f, msgs in exc.message_dict.items():
                        heading = next((c.heading for c in self.columns if c.field == f), "Row")
                        result.errors.extend(f"{heading}: {m}" for m in msgs)
            if obj.pk and not result.changed and not result.errors:
                result.action = "unchanged"
            results.append(result)
            prepared.append(Prepared(obj, deferred, result))
        return results, prepared

    deferred_kinds = ()

    def duplicate_key(self, values):
        return values.get(self.reference_field, ("", ""))[0].lower()


class Workbook:
    """A set of sheets imported together."""
    title = ""
    sheets = []  # Sheet classes, in save order
    optional = ()  # names of sheets that may be left out

    def __init__(self):
        self.context = {}
        self.instances = [cls(self.context) for cls in self.sheets]

    def read(self, uploaded):
        """Return {sheet name: [(row number, {field: (text, raw)})]}."""
        name = uploaded.name.lower()
        if name.endswith(".csv"):
            # A CSV holds one sheet: whichever sheet's headings it matches best.
            text = uploaded.read().decode("utf-8-sig", errors="replace")
            table = list(csv.reader(io.StringIO(text)))
            if not table:
                raise ValidationError("The file is empty.")
            sheet = self._sheet_for_headings(table[0])
            return {sheet.name: self._rows(sheet, table)}
        if not name.endswith(".xlsx"):
            raise ValidationError("Upload an Excel (.xlsx) or CSV (.csv) file.")
        from openpyxl import load_workbook

        try:
            wb = load_workbook(uploaded, read_only=True, data_only=True)
        except Exception:
            raise ValidationError("This file could not be opened as an Excel workbook.")
        found = {}
        for sheet in self.instances:
            if sheet.name in wb.sheetnames:
                table = [list(r) for r in wb[sheet.name].iter_rows(values_only=True)]
                if table:
                    found[sheet.name] = self._rows(sheet, table)
        if not found:
            if len(self.instances) == 1:
                table = [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
                if table:
                    found[self.instances[0].name] = self._rows(self.instances[0], table)
            if not found:
                names = ", ".join(f"“{s.name}”" for s in self.instances)
                raise ValidationError(f"No sheet called {names} was found. Use the PHAEMA template.")
        return found

    def _sheet_for_headings(self, headings):
        labels = {str(h or "").strip().lower().rstrip("*").strip() for h in headings}
        best = max(self.instances, key=lambda s: len(labels & {c.heading.lower() for c in s.columns}))
        return best

    def _rows(self, sheet, table):
        by_heading = {c.heading.lower(): c.field for c in sheet.columns}
        by_heading.update({c.field: c.field for c in sheet.columns})
        headers = [by_heading.get(str(h or "").strip().lower().rstrip("*").strip()) for h in table[0]]
        missing = [c.heading for c in sheet.columns if c.required and c.field not in headers]
        if missing:
            raise ValidationError(f"{sheet.name} sheet: missing column(s) {', '.join(missing)}. Use the PHAEMA template.")
        rows = []
        for number, raw_row in enumerate(table[1:], start=2):
            values = {}
            for f, cell in zip(headers, raw_row):
                if f is None:
                    continue
                values[f] = (cell_text(cell), cell)
            if any(t for t, _r in values.values()):
                rows.append((number, values))
        return rows

    def validate(self, uploaded):
        data = self.read(uploaded)
        for sheet in self.instances:  # let sheets see what the file contains before checking
            sheet.context[sheet.name] = data.get(sheet.name, [])
        sheets, prepared = [], []
        for sheet in self.instances:
            if sheet.name not in data:
                continue
            results, items = sheet.validate(data[sheet.name])
            sheets.append((sheet, results))
            prepared.append((sheet, items))
        return ImportResult(sheets), prepared

    @transaction.atomic
    def apply(self, prepared):
        saved = 0
        for sheet, items in prepared:
            for item in items:
                if item.result.action == "unchanged" and not item.deferred:
                    continue
                sheet.save(item)
                saved += 1
        return saved

    def template(self):
        """An Excel template: one sheet per record type with an example row, drop-downs and guidance."""
        from openpyxl import Workbook as XLWorkbook
        from openpyxl.styles import Font, PatternFill
        from openpyxl.worksheet.datavalidation import DataValidation

        wb = XLWorkbook()
        wb.remove(wb.active)
        lists = wb.create_sheet("Lists")
        list_col = 0
        for sheet in self.instances:
            ws = wb.create_sheet(sheet.name, index=len(wb.sheetnames) - 1)
            ws.append([f"{c.heading}*" if c.required else c.heading for c in sheet.columns])
            for cell in ws[1]:
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill("solid", fgColor="1D3557")
            ws.append([c.example for c in sheet.columns])
            ws.freeze_panes = "A2"
            for i, c in enumerate(sheet.columns, start=1):
                letter = ws.cell(1, i).column_letter
                ws.column_dimensions[letter].width = max(12, len(c.heading) + 4)
                options = None
                if c.kind == "choice":
                    options = [str(label) for _v, label in sheet.model._meta.get_field(c.field).choices]
                elif c.kind == "bool":
                    options = ["Yes", "No"]
                if options:
                    list_col += 1
                    for r, label in enumerate(options, start=1):
                        lists.cell(r, list_col, label)
                    ll = lists.cell(1, list_col).column_letter
                    dv = DataValidation(type="list", formula1=f"=Lists!${ll}$1:${ll}${len(options)}", allow_blank=True)
                    ws.add_data_validation(dv)
                    dv.add(f"{letter}2:{letter}5000")
        lists.sheet_state = "hidden"
        guide = wb.create_sheet("Guidance")
        guide.append(["Sheet", "Column", "Required", "Guidance"])
        for cell in guide[1]:
            cell.font = Font(bold=True)
        for sheet in self.instances:
            for c in sheet.columns:
                guide.append([sheet.name, c.heading, "Yes" if c.required else "", c.guidance])
        guide.append([])
        for line in self.notes:
            guide.append(["Notes", "", "", line])
        guide.column_dimensions["A"].width = 14
        guide.column_dimensions["B"].width = 26
        guide.column_dimensions["D"].width = 100
        out = io.BytesIO()
        wb.save(out)
        return out.getvalue()

    notes = ["Delete the example rows before importing. Empty cells leave existing values unchanged.",
             "Dates can be typed as dd/mm/yyyy or entered as Excel dates."]


# ---- cell helpers

def cell_text(cell):
    if cell is None:
        return ""
    if isinstance(cell, datetime):
        return cell.date().isoformat()
    if isinstance(cell, date):
        return cell.isoformat()
    if isinstance(cell, float) and cell.is_integer():
        return str(int(cell))  # Excel stores 445000 as 445000.0
    return str(cell).strip()


def same(current, value):
    if isinstance(current, Decimal) and isinstance(value, Decimal):
        return current == value
    if hasattr(current, "pk") and hasattr(value, "pk"):
        return current.pk == value.pk
    return current == value


def choice(model, field_name, text):
    model_field = model._meta.get_field(field_name)
    t = text.strip().lower()
    for value, label in model_field.choices:
        if t in (str(value).lower(), str(label).lower()):
            return value
    # Accept the start of a long label, e.g. "Inside the 1954 Act".
    starts = [value for value, label in model_field.choices if str(label).lower().startswith(t) and len(t) >= 4]
    if len(starts) == 1:
        return starts[0]
    raise ValueError(f"'{text}' is not a valid {model_field.verbose_name}. "
                     f"Use one of: {', '.join(str(label) for _v, label in model_field.choices)}.")


def to_decimal(text):
    try:
        return Decimal(text.replace(",", "").replace("£", "").strip())
    except InvalidOperation:
        raise ValueError(f"{text} is not a number.")


def to_date(raw, text):
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"'{text}' is not a date. Use dd/mm/yyyy, e.g. 25/03/2026.")


def to_bool(text):
    t = text.strip().lower()
    if t in YES:
        return True
    if t in NO:
        return False
    raise ValueError(f"'{text}' should be Yes or No.")


def find_user(text):
    user = get_user_model().objects.filter(Q(username__iexact=text) | Q(email__iexact=text)).first()
    if user is None:
        raise ValueError(f"no PHAEMA user with username or email '{text}'.")
    return user
