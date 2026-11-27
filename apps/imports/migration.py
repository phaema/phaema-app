# SPDX-License-Identifier: AGPL-3.0-or-later
"""Moving records in from another system: trial runs, control totals, the exception report and sign-off.

Every import (properties, and each workbook in sheets.py) goes through an adapter that checks a file and saves it.
On top of that:

- A **trial run** imports the file inside a transaction that is then rolled back, so the council sees exactly what
  would be added and changed, and the totals PHAEMA would hold, with nothing saved.
- **Control totals** compare three figures: the old system's (typed in by the person importing, from the old
  system's own reports), the file's, and PHAEMA's after the import. Every sheet's row count is one; columns marked
  ``total=True`` (rents, amounts, values) are the others.
- The **exception report** is an Excel file listing every row with what happened to it, its problems and warnings,
  for checking a large file away from the screen.
- Each trial and real run is kept as a ``MigrationRun`` with its report, and an administrator other than the person
  who ran it can **sign it off** as checked.
"""
import hashlib
import io
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .models import MigrationRun


@dataclass
class Row:
    sheet: str
    number: int
    reference: str
    action: str
    changed: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


@dataclass
class Control:
    key: str
    label: str
    in_file: Decimal
    places: int = 0  # decimal places shown: 0 for counts and whole pounds, 2 for money


@dataclass
class Outcome:
    """A checked file: its rows, counts and control totals, and how to save it."""
    result: object  # the importer's own result, for its preview page
    rows: list
    summary: list  # [(label, new, updated, unchanged)]
    controls: list
    saver: object = None  # () -> {control key: total in PHAEMA}

    @property
    def ok(self):
        return bool(self.rows) and not any(r.errors for r in self.rows)

    @property
    def warning_count(self):
        return sum(1 for r in self.rows if r.warnings)

    @property
    def error_count(self):
        return sum(1 for r in self.rows if r.errors)


def _number(text):
    try:
        return Decimal(str(text).replace(",", "").replace("£", "").strip())
    except (InvalidOperation, ValueError):
        return None


class WorkbookAdapter:
    """One of the workbooks in sheets.py (parties, leases, receipts and so on)."""

    supports_trial, supports_mapping, max_bytes = True, True, 10 * 1024 * 1024

    def __init__(self, cls):
        self.cls, self.key, self.title, self.description = cls, cls.key, cls.title, cls.description

    @property
    def template_url(self):
        from django.urls import reverse

        return reverse("imports:template", args=[self.key])

    def sheet_columns(self):
        """[(sheet name, label, [(field, heading, required)])], for matching another system's columns."""
        return [(sh.name, sh.label, [(c.field, c.heading, c.required) for c in sh.columns])
                for sh in self.cls().instances]

    def check(self, uploaded, mapping=None):
        workbook = self.cls(mapping=mapping)
        result, prepared = workbook.validate(uploaded)
        rows = [Row(r.sheet, r.number, r.reference, r.action, r.changed, r.errors, r.warnings) for r in result.rows]
        controls, filled = [], {}
        for sheet, items in prepared:
            controls.append(Control(f"{sheet.name}:rows", f"{sheet.label}: rows", Decimal(len(items))))
            data = dict(sheet.context.get(sheet.name, []))
            for column in sheet.columns:
                if not column.total:
                    continue
                total, rows_with = Decimal("0"), []
                for item in items:
                    text = data.get(item.result.number, {}).get(column.field, ("", None))[0]
                    value = _number(text) if text else None
                    if value is not None:
                        total += value
                        rows_with.append(item)
                key = f"{sheet.name}:{column.field}"
                filled[key] = (sheet, column.field, rows_with)
                controls.append(Control(key, f"{sheet.label}: {column.heading.lower()}", total, 2))

        def save():
            workbook.apply(prepared)
            after = {}
            for sheet, items in prepared:
                after[f"{sheet.name}:rows"] = Decimal(len({i.obj.pk for i in items if i.obj.pk}))
            for key, (sheet, name, rows_with) in filled.items():
                pks = [i.obj.pk for i in rows_with if i.obj.pk]
                total = sheet.model.objects.filter(pk__in=pks).aggregate(t=Sum(name))["t"] if pks else None
                after[key] = Decimal(total or 0)
            return after

        return Outcome(result, rows, result.summary(), controls, save)


class PropertyAdapter:
    """The property register import (apps/properties/importer.py)."""

    key, title = "properties", "Properties"
    description = "Estates, sites, buildings, units and land, with addresses, UPRNs, areas and managing surveyors."
    supports_trial, supports_mapping, max_bytes = True, True, 10 * 1024 * 1024
    TOTALS = [("site_area_ha", "site area (ha)", 4), ("gia_sqm", "GIA (m²)", 2), ("nia_sqm", "NIA (m²)", 2)]

    @property
    def template_url(self):
        from django.urls import reverse

        return reverse("properties:import-template")

    def sheet_columns(self):
        from apps.properties.importer import COLUMNS

        return [("Properties", "Properties", [(f, h, req) for h, f, req, _g in COLUMNS])]

    def check(self, uploaded, mapping=None):
        from apps.properties import importer
        from apps.properties.models import Property

        data = importer.read_rows(uploaded, (mapping or {}).get("Properties"))
        result, prepared = importer.validate(data)
        by_number = dict(data)
        rows = []
        for r in result.rows:
            row = Row("Properties", r.number, r.reference, r.action, r.changed, r.errors)
            values = by_number.get(r.number, {})
            if r.action == "create" and not r.errors and values.get("postcode") and values.get("address_line_1"):
                twin = (Property.objects.filter(postcode__iexact=values["postcode"].strip(),
                                                address_line_1__iexact=values["address_line_1"].strip())
                        .exclude(reference=r.reference).first())
                if twin:
                    row.warnings.append(f"Same address and postcode as {twin.reference} {twin.name}, already in "
                                        "PHAEMA. Check it is not the same property under another reference.")
            rows.append(row)
        controls = [Control("properties:rows", "Properties: rows", Decimal(len(result.rows)))]
        filled = {}
        for name, label, places in self.TOTALS:
            total, refs = Decimal("0"), []
            for _row, values in data:
                value = _number(values.get(name)) if values.get(name) else None
                if value is not None:
                    total += value
                    refs.append(values.get("reference", ""))
            filled[f"properties:{name}"] = (name, refs)
            controls.append(Control(f"properties:{name}", f"Properties: {label}", total, places))
        summary = [("Properties", result.count("create"), result.count("update"), result.count("unchanged"))]

        def save():
            importer.apply([(obj, parent) for (obj, parent), r in zip(prepared, result.rows)
                            if r.action != "unchanged"])
            refs = [r.reference for r in result.rows]
            after = {"properties:rows": Decimal(Property.objects.filter(reference__in=refs).count())}
            for key, (name, with_value) in filled.items():
                total = Property.objects.filter(reference__in=with_value).aggregate(t=Sum(name))["t"]
                after[key] = Decimal(total or 0)
            return after

        return Outcome(result, rows, summary, controls, save)


def adapters_for(user):
    """Every import this person may run, in the order to import them."""
    from apps.core.roles import is_administrator

    from .documents import DocumentsAdapter
    from .views import _available

    found = [PropertyAdapter()] if is_administrator(user) else []
    found += [WorkbookAdapter(cls) for cls in _available(user)]
    return found + ([DocumentsAdapter()] if is_administrator(user) else [])


def fingerprint(uploaded):
    uploaded.seek(0)
    digest = hashlib.sha256(uploaded.read()).hexdigest()
    uploaded.seek(0)
    return digest


def expected_from(post, controls):
    """The old system's figures typed in on the preview page, by control key."""
    out = {}
    for c in controls:
        value = _number(post.get(f"expected:{c.key}", "")) if post.get(f"expected:{c.key}", "").strip() else None
        if value is not None:
            out[c.key] = value
    return out


def run(adapter, uploaded, mode, user, expected=None, mapping=None):
    """Check and import a file for real or as a trial, and keep the run with its report. The file must be clean."""
    expected = expected or {}
    sha = fingerprint(uploaded)
    outcome = adapter.check(uploaded, mapping)
    if not outcome.ok:
        raise ValueError("The file has problems: check it again.")
    with transaction.atomic():
        after = outcome.saver()
        if mode == MigrationRun.Mode.TRIAL:
            transaction.set_rollback(True)
    controls = []
    for c in outcome.controls:
        in_phaema = after.get(c.key)
        want = expected.get(c.key)
        matches = in_phaema == c.in_file and (want is None or want == c.in_file)
        controls.append({"key": c.key, "label": c.label, "places": c.places,
                         "expected": str(want) if want is not None else "", "in_file": str(c.in_file),
                         "in_phaema": str(in_phaema) if in_phaema is not None else "", "matches": matches})
    record = MigrationRun.objects.create(
        kind=adapter.key, title=adapter.title, mode=mode, filename=getattr(uploaded, "name", "")[:255],
        file_sha256=sha, run_by=user, rows=len(outcome.rows), summary=[list(s) for s in outcome.summary],
        controls=controls, warnings=outcome.warning_count)
    record.report.save(f"migration-{record.pk}.xlsx", ContentFile(report(outcome, record)), save=True)
    return record, outcome


def sign_off(record, user, note=""):
    if record.signed_off_at:
        raise ValueError("This run has already been signed off.")
    if record.run_by_id == user.pk:
        raise ValueError("Someone other than the person who ran the import must sign it off.")
    record.signed_off_by, record.signed_off_at, record.sign_off_note = user, timezone.now(), note.strip()
    record.save(update_fields=["signed_off_by", "signed_off_at", "sign_off_note"])


def report(outcome, record=None, title="", filename=""):
    """The exception report: a summary sheet (counts and control totals) and every row with its outcome."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    bold, head = Font(bold=True), PatternFill("solid", fgColor="1D3557")
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    ws.append([f"PHAEMA import check: {record.title if record else title}"])
    ws["A1"].font = Font(bold=True, size=14)
    details = [("File", record.filename if record else filename)]
    if record:
        details += [("Fingerprint (SHA-256)", record.file_sha256), ("Run", record.get_mode_display()),
                    ("Run by", record.run_by.get_full_name() or record.run_by.username if record.run_by else ""),
                    ("Run at", timezone.localtime(record.run_at).strftime("%d %b %Y %H:%M"))]
    else:
        details.append(("Run", "Check only (nothing saved)"))
    problems = sum(1 for r in outcome.rows if r.errors)
    details += [("Rows", len(outcome.rows)), ("Rows with problems", problems),
                ("Rows with warnings", outcome.warning_count)]
    for label, value in details:
        ws.append([label, value])
        ws.cell(ws.max_row, 1).font = bold
    ws.append([])
    ws.append(["Sheet", "New", "Updated", "Unchanged"])
    for cell in ws[ws.max_row]:
        cell.font = bold
    for row in outcome.summary:
        ws.append(list(row))
    ws.append([])
    if record:
        ws.append(["Control total", "Old system", "In the file", "In PHAEMA after import", "Matches"])
        for cell in ws[ws.max_row]:
            cell.font = bold
        for c in record.controls:
            ws.append([c["label"], _cell(c["expected"]), _cell(c["in_file"]), _cell(c["in_phaema"]),
                       "Yes" if c["matches"] else "NO"])
    else:
        ws.append(["Control total", "In the file"])
        for cell in ws[ws.max_row]:
            cell.font = bold
        for c in outcome.controls:
            ws.append([c.label, float(c.in_file)])
    ws.column_dimensions["A"].width = 42
    for letter in "BCDE":
        ws.column_dimensions[letter].width = 22

    rows = wb.create_sheet("Rows")
    rows.append(["Sheet", "Row", "Record", "Result", "Changed", "Problems", "Warnings"])
    for cell in rows[1]:
        cell.font, cell.fill = Font(bold=True, color="FFFFFF"), head
    labels = {"create": "New", "update": "Update", "unchanged": "No change"}
    for r in outcome.rows:
        rows.append([r.sheet, r.number, r.reference, "Problem" if r.errors else labels.get(r.action, r.action),
                     ", ".join(r.changed), "\n".join(r.errors), "\n".join(r.warnings)])
    for col, width in zip("ABCDEFG", (18, 7, 22, 12, 30, 60, 60)):
        rows.column_dimensions[col].width = width
    for row in rows.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    rows.freeze_panes = "A2"
    rows.auto_filter.ref = rows.dimensions
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _cell(text):
    if text in ("", None):
        return None
    try:
        return float(text)
    except ValueError:
        return text
