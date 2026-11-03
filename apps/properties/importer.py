# SPDX-License-Identifier: AGPL-3.0-or-later
"""Import properties from an Excel (.xlsx) or CSV spreadsheet.

Rows are matched to existing records by asset reference: new references are created,
existing ones updated. Empty cells leave existing values unchanged. Nothing is saved
until every row passes validation.
"""
import csv
import io
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from .models import Property

# (column heading, model field, required, guidance)
COLUMNS = [
    ("Reference", "reference", True, "The council's unique asset reference. Existing references are updated."),
    ("Name", "name", True, "Name of the property, e.g. Unit 3 or Town Hall."),
    ("Type", "property_type", True, "Estate, Site, Building, Lettable unit or Land parcel."),
    ("Part of", "parent", False, "Reference of the property this is part of (already in PHAEMA or in this file)."),
    ("UPRN", "uprn", False, "Unique Property Reference Number (up to 12 digits)."),
    ("USRN", "usrn", False, "Unique Street Reference Number (up to 8 digits)."),
    ("Address line 1", "address_line_1", False, ""),
    ("Address line 2", "address_line_2", False, ""),
    ("Town", "town", False, ""),
    ("Postcode", "postcode", False, ""),
    ("Holding purpose", "holding_purpose", False, "Operational, Investment, Community, Surplus or Held for disposal."),
    ("Tenure", "tenure", False, "Freehold, Leasehold, Other, or None (managed, not owned)."),
    ("Occupation", "occupation", False, "Occupied by the council, Let to a third party, Partly let, Vacant or Not applicable."),
    ("Use", "use_description", False, "e.g. Retail, Office, Industrial, Car park."),
    ("Use class", "use_class", False, "e.g. E(a), B2, B8, Sui generis."),
    ("GIA m2", "gia_sqm", False, "Gross internal area in square metres."),
    ("NIA m2", "nia_sqm", False, "Net internal area in square metres."),
    ("Site area ha", "site_area_ha", False, "Site area in hectares."),
    ("Easting", "easting", False, "British National Grid easting (6 digits)."),
    ("Northing", "northing", False, "British National Grid northing (6 or 7 digits)."),
    ("Managing surveyor", "managing_surveyor", False, "The surveyor's PHAEMA username or email address."),
    ("Exclude from open data", "exclude_from_publication", False, "Yes for sensitive properties; otherwise leave blank."),
    ("Notes", "notes", False, ""),
]
CHOICE_FIELDS = {"property_type", "holding_purpose", "tenure", "occupation"}
DECIMAL_FIELDS = {"gia_sqm", "nia_sqm", "site_area_ha"}
INTEGER_FIELDS = {"easting", "northing"}


@dataclass
class RowResult:
    number: int
    reference: str
    action: str = "create"  # create, update, unchanged
    changed: list = field(default_factory=list)
    errors: list = field(default_factory=list)


@dataclass
class ImportResult:
    rows: list
    file_errors: list

    @property
    def ok(self):
        return not self.file_errors and not any(r.errors for r in self.rows)

    def count(self, action):
        return sum(1 for r in self.rows if r.action == action and not r.errors)

    @property
    def count_create(self):
        return self.count("create")

    @property
    def count_update(self):
        return self.count("update")

    @property
    def count_unchanged(self):
        return self.count("unchanged")


def read_rows(uploaded):
    """Return the data rows as lists of dicts keyed by model field name."""
    name = uploaded.name.lower()
    if name.endswith(".csv"):
        text = uploaded.read().decode("utf-8-sig", errors="replace")
        table = list(csv.reader(io.StringIO(text)))
    elif name.endswith(".xlsx"):
        from openpyxl import load_workbook

        wb = load_workbook(uploaded, read_only=True, data_only=True)
        ws = wb["Properties"] if "Properties" in wb.sheetnames else wb.worksheets[0]
        table = [list(r) for r in ws.iter_rows(values_only=True)]
    else:
        raise ValidationError("Upload an Excel (.xlsx) or CSV (.csv) file.")
    if not table:
        raise ValidationError("The file is empty.")

    by_heading = {h.lower(): f for h, f, _r, _g in COLUMNS}
    by_heading.update({f: f for _h, f, _r, _g in COLUMNS})
    headers = [by_heading.get(str(h or "").strip().lower().rstrip("*").strip()) for h in table[0]]
    missing = [h for h, f, req, _g in COLUMNS if req and f not in headers]
    if missing:
        raise ValidationError(f"Missing column(s): {', '.join(missing)}. Use the PHAEMA template.")
    rows = []
    for number, raw in enumerate(table[1:], start=2):
        values = {}
        for f, cell in zip(headers, raw):
            if f is None:
                continue
            text = "" if cell is None else str(cell).strip()
            if isinstance(cell, float) and cell.is_integer() and f not in DECIMAL_FIELDS:
                text = str(int(cell))  # Excel stores 445000 as 445000.0
            values[f] = text
        if any(values.values()):
            rows.append((number, values))
    return rows


def _choice(field_name, text):
    choices = Property._meta.get_field(field_name).choices
    t = text.strip().lower()
    for value, label in choices:
        if t in (str(value).lower(), str(label).lower()):
            return value
    raise ValueError(f"'{text}' is not a valid {Property._meta.get_field(field_name).verbose_name}. "
                     f"Use one of: {', '.join(str(label) for _v, label in choices)}.")


def validate(rows, user_model=None):
    """Check every row and work out what would change. Returns an ImportResult and the prepared objects."""
    User = user_model or get_user_model()
    all_refs = {v.get("reference", "") for _n, v in rows}
    file_parents = {v.get("reference", ""): v.get("parent", "") for _n, v in rows}
    refs_in_file = {}
    results, prepared = [], []
    existing = {p.reference: p for p in Property.objects.filter(reference__in=[v.get("reference", "") for _n, v in rows])}
    for number, values in rows:
        ref = values.get("reference", "")
        result = RowResult(number, ref)
        if not ref:
            result.errors.append("Reference is missing.")
        elif ref in refs_in_file:
            result.errors.append(f"Reference {ref} appears more than once (also row {refs_in_file[ref]}).")
        refs_in_file.setdefault(ref, number)

        obj = existing.get(ref)
        if obj is None:
            obj = Property(reference=ref)
        else:
            result.action = "update"
        parent_ref = None
        for f, text in values.items():
            if f == "reference" or text == "":
                continue
            try:
                if f in CHOICE_FIELDS:
                    value = _choice(f, text)
                elif f in DECIMAL_FIELDS:
                    try:
                        value = Decimal(text.replace(",", ""))
                    except InvalidOperation:
                        raise ValueError(f"{text} is not a number.")
                elif f in INTEGER_FIELDS:
                    if not text.replace(",", "").isdigit():
                        raise ValueError(f"{text} is not a whole number.")
                    value = int(text.replace(",", ""))
                elif f == "exclude_from_publication":
                    if text.lower() not in ("yes", "y", "true", "1", "no", "n", "false", "0"):
                        raise ValueError(f"'{text}' should be Yes or No.")
                    value = text.lower() in ("yes", "y", "true", "1")
                elif f == "managing_surveyor":
                    user = User.objects.filter(Q(username__iexact=text) | Q(email__iexact=text)).first()
                    if user is None:
                        raise ValueError(f"No PHAEMA user with username or email '{text}'.")
                    value = user
                elif f == "parent":
                    parent_ref = text
                    continue
                else:
                    value = text
            except ValueError as exc:
                label = next(h for h, ff, _r, _g in COLUMNS if ff == f)
                result.errors.append(f"{label}: {exc}")
                continue
            current = getattr(obj, f)
            if obj.pk and current != value and not (isinstance(current, Decimal) and value == current):
                result.changed.append(f)
            setattr(obj, f, value)

        if parent_ref:
            if parent_ref == ref:
                result.errors.append("Part of: a property cannot be part of itself.")
            elif parent_ref not in all_refs and not Property.objects.filter(reference=parent_ref).exists():
                result.errors.append(f"Part of: no property with reference {parent_ref} in PHAEMA or in this file.")
            else:
                seen, node = {ref}, parent_ref
                while node in file_parents and file_parents[node]:
                    if node in seen:
                        result.errors.append("Part of: these rows are parts of each other in a loop.")
                        break
                    seen.add(node)
                    node = file_parents[node]
        if obj.pk and parent_ref and (obj.parent.reference if obj.parent_id else None) != parent_ref:
            result.changed.append("parent")

        if not result.errors:
            try:
                obj.full_clean(exclude=["parent", "reference"] if obj.pk else ["parent"],
                               validate_unique=not obj.pk)
            except ValidationError as exc:
                for f, msgs in exc.message_dict.items():
                    label = next((h for h, ff, _r, _g in COLUMNS if ff == f), "Row")
                    result.errors.extend(f"{label}: {m}" for m in msgs)
        if obj.pk and not result.changed and not result.errors:
            result.action = "unchanged"
        results.append(result)
        prepared.append((obj, parent_ref))
    return ImportResult(results, []), prepared


@transaction.atomic
def apply(prepared):
    """Save validated rows. Parents are saved before their parts."""
    saved = {}
    pending = list(prepared)
    while pending:
        progress = False
        for item in list(pending):
            obj, parent_ref = item
            if parent_ref and parent_ref not in saved and any(o.reference == parent_ref for o, _p in pending):
                continue  # wait until the parent from this file is saved
            if parent_ref:
                obj.parent = saved.get(parent_ref) or Property.objects.get(reference=parent_ref)
            obj.save()
            saved[obj.reference] = obj
            pending.remove(item)
            progress = True
        if not progress:
            raise ValidationError("Some rows are parts of each other in a loop. Check the 'Part of' column.")
    return len(saved)


def template_workbook():
    """An Excel template with a Properties sheet, drop-down lists and a Guidance sheet."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = Workbook()
    ws = wb.active
    ws.title = "Properties"
    ws.append([f"{h}*" if req else h for h, _f, req, _g in COLUMNS])
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1D3557")
    ws.append(["EX-001", "Example Business Park", "Site", "", "", "", "Example Road", "", "Exampletown", "",
               "Investment", "Freehold", "Partly let", "Business park", "", "", "", "2.5", "", "", "", "", "Delete this example row"])
    ws.freeze_panes = "A2"
    for i, (h, _f, _r, _g) in enumerate(COLUMNS, start=1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = max(12, len(h) + 4)

    lists = wb.create_sheet("Lists")
    for col, f in enumerate(["property_type", "holding_purpose", "tenure", "occupation"], start=1):
        labels = [str(label) for _v, label in Property._meta.get_field(f).choices]
        for row, label in enumerate(labels, start=1):
            lists.cell(row, col, label)
        letter = lists.cell(1, col).column_letter
        target = next(i for i, (_h, ff, _r, _g) in enumerate(COLUMNS, start=1) if ff == f)
        dv = DataValidation(type="list", formula1=f"=Lists!${letter}$1:${letter}${len(labels)}", allow_blank=True)
        ws.add_data_validation(dv)
        dv.add(f"{ws.cell(2, target).column_letter}2:{ws.cell(2, target).column_letter}5000")
    yes_no = DataValidation(type="list", formula1='"Yes,No"', allow_blank=True)
    ws.add_data_validation(yes_no)
    excl = next(i for i, (_h, ff, _r, _g) in enumerate(COLUMNS, start=1) if ff == "exclude_from_publication")
    yes_no.add(f"{ws.cell(2, excl).column_letter}2:{ws.cell(2, excl).column_letter}5000")
    lists.sheet_state = "hidden"

    guide = wb.create_sheet("Guidance")
    guide.append(["Column", "Required", "Guidance"])
    for cell in guide[1]:
        cell.font = Font(bold=True)
    for h, _f, req, g in COLUMNS:
        guide.append([h, "Yes" if req else "", g])
    guide.append([])
    guide.append(["Notes", "", "Rows are matched by Reference: new references are added, existing ones updated. "
                  "Empty cells leave existing values unchanged. Put estates and buildings above their parts, "
                  "or make sure they already exist in PHAEMA."])
    guide.column_dimensions["A"].width = 24
    guide.column_dimensions["C"].width = 100
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
