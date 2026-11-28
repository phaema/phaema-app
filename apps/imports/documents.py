# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bringing documents across from another system in bulk: a zip file of documents with an index saying what each
one is and which record it belongs to.

The index is a sheet called "Documents" (in index.xlsx or index.csv inside the zip) with one row per file: the
file's name in the zip, what it is attached to (agreement, title, floor plan or building document), the record's
reference, the kind of document, a description and a date. Every row is checked before anything is saved, as with
every other import, and the documents are checked as each record's own upload page would check them.
"""
import csv
import io
import os
import zipfile
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile

from .engine import cell_text, to_date
from .migration import Control, Outcome, Row

TARGETS = {
    "agreement": "Agreement document", "title": "Title document", "plan": "Floor plan",
    "building": "Building document",
}
ALIASES = {"lease": "agreement", "licence": "agreement", "agreement document": "agreement",
           "title document": "title", "floor plan": "plan", "plans": "plan", "building document": "building",
           "compliance": "building"}
COLUMNS = [
    ("File", "file", True, "The file's name in the zip, with any folder, for example leases/DL-0001.pdf."),
    ("Attach to", "target", True, "Agreement document, Title document, Floor plan or Building document."),
    ("Reference", "reference", True, "The agreement reference, title number or property reference."),
    ("Type", "kind", False, "Agreements: Lease or licence, Deed of variation, Licence to assign, Notice and so on. "
                            "Titles: Official copy of the register, Title plan, Conveyance and so on. Building "
                            "documents: Plans and drawings, Fire safety information, Surveys and reports and so on. "
                            "Left blank: Other."),
    ("Description", "description", False, "What the document is. Floor plans and building documents need one; "
                                          "left blank, the file name is used."),
    ("Date", "date", False, "The document's date, dd/mm/yyyy."),
]
MAX_FILES = 500
# Limits on what the zip holds once unzipped, checked from the zip's own listing before anything is read, so a small
# upload cannot expand into something that fills the server's memory or disk. Python's zipfile never returns more
# than an entry's listed size (a mismatch fails its checksum), so the listing can be trusted for this.
MAX_ENTRIES = MAX_FILES + 50           # documents, the index and a few stray files such as __MACOSX entries
MAX_EXPANDED = 500 * 1024 * 1024       # everything in the zip, unzipped
MAX_DOCUMENT = 50 * 1024 * 1024        # any one document
MAX_INDEX = 5 * 1024 * 1024            # index.xlsx or index.csv


def _choice(choices, text):
    t = (text or "").strip().lower()
    if not t:
        return "other"
    for value, label in choices:
        if t in (str(value).lower(), str(label).lower()) or str(label).lower().startswith(t):
            return value
    raise ValueError(f"'{text}' is not a type for this kind of document. Use one of: "
                     + ", ".join(str(label) for _v, label in choices) + ".")


def _check_sizes(archive):
    entries = [info for info in archive.infolist() if not info.is_dir()]
    if len(entries) > MAX_ENTRIES:
        raise ValidationError(f"The zip holds {len(entries)} files. Send at most {MAX_FILES} documents in one zip.")
    if sum(info.file_size for info in entries) > MAX_EXPANDED:
        raise ValidationError(f"The documents in the zip come to more than {MAX_EXPANDED // 1024 ** 2} MB once "
                              "unzipped. Split them across several zips.")
    for info in entries:
        if info.filename.lower() in ("index.xlsx", "index.csv"):
            if info.file_size > MAX_INDEX:
                raise ValidationError(f"The index is larger than {MAX_INDEX // 1024 ** 2} MB once unzipped. It "
                                      "should only list the documents.")
        elif info.file_size > MAX_DOCUMENT:
            raise ValidationError(f"{info.filename} is larger than {MAX_DOCUMENT // 1024 ** 2} MB once unzipped. "
                                  "Add very large documents one at a time.")


def _index(archive):
    names = {n.lower(): n for n in archive.namelist() if not n.endswith("/")}
    if "index.xlsx" in names:
        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(archive.read(names["index.xlsx"])), read_only=True, data_only=True)
        ws = wb["Documents"] if "Documents" in wb.sheetnames else wb.worksheets[0]
        table = [list(r) for r in ws.iter_rows(values_only=True)]
    elif "index.csv" in names:
        text = archive.read(names["index.csv"]).decode("utf-8-sig", errors="replace")
        table = list(csv.reader(io.StringIO(text)))
    else:
        raise ValidationError("The zip file needs an index: index.xlsx or index.csv, listing each document.")
    if not table:
        raise ValidationError("The index is empty.")
    by_heading = {h.lower(): f for h, f, _r, _g in COLUMNS}
    headers = [by_heading.get(str(h or "").strip().lower().rstrip("*").strip()) for h in table[0]]
    missing = [h for h, f, req, _g in COLUMNS if req and f not in headers]
    if missing:
        raise ValidationError(f"The index is missing column(s) {', '.join(missing)}. Use the PHAEMA template.")
    rows = []
    for number, raw in enumerate(table[1:], start=2):
        values = {f: (cell_text(cell), cell) for f, cell in zip(headers, raw) if f}
        if any(t for t, _r in values.values()):
            rows.append((number, values))
    return rows, names


class DocumentsAdapter:
    key, title = "documents", "Documents"
    description = ("Documents from another system in bulk: a zip file of PDFs and drawings with an index saying "
                   "which agreement, title or property each belongs to.")
    supports_trial, supports_mapping, max_bytes = False, False, 50 * 1024 * 1024

    @property
    def template_url(self):
        from django.urls import reverse

        return reverse("imports:documents-template")

    def check(self, uploaded, mapping=None):
        from apps.compliance.models import BuildingDocument
        from apps.leases.models import Lease, LeaseDocument
        from apps.properties.models import Property, PropertyPlan, Title, TitleDocument

        if not uploaded.name.lower().endswith(".zip"):
            raise ValidationError("Upload a zip file holding the documents and an index (index.xlsx or index.csv).")
        try:
            archive = zipfile.ZipFile(uploaded)
        except zipfile.BadZipFile:
            raise ValidationError("This file could not be opened as a zip file.") from None
        _check_sizes(archive)
        index, names = _index(archive)
        if len(index) > MAX_FILES:
            raise ValidationError(f"The index lists {len(index)} documents. Send at most {MAX_FILES} in one zip.")
        rows, plans, seen = [], [], {}
        for number, values in index:
            def get(name, values=values):
                return values.get(name, ("", None))[0].strip()

            row = Row("Documents", number, get("file"), "create")
            path = get("file").replace("\\", "/").lstrip("/")
            target = ALIASES.get(get("target").lower(), get("target").lower())
            reference = get("reference")
            when = None
            if not path:
                row.errors.append("File is missing.")
            elif path.lower() not in names:
                row.errors.append(f"There is no file called {path} in the zip.")
            elif path.lower() in seen:
                row.errors.append(f"This file is also listed on row {seen[path.lower()]}.")
            else:
                seen[path.lower()] = number
            if target not in TARGETS:
                row.errors.append("Attach to: use Agreement document, Title document, Floor plan or Building "
                                  "document.")
            if values.get("date", ("", None))[0]:
                try:
                    when = to_date(values["date"][1], values["date"][0])
                except ValueError as exc:
                    row.errors.append(f"Date: {exc}")
            record = None
            if target == "agreement":
                record = Lease.objects.filter(reference=reference).first()
            elif target == "title":
                record = Title.objects.filter(title_number=reference.replace(" ", "").upper()).first()
            elif target in ("plan", "building"):
                record = Property.objects.filter(reference__iexact=reference).first()
            if target in TARGETS and record is None:
                row.errors.append(f"Reference: nothing called {reference} to attach a {TARGETS[target].lower()} to.")
            kind = None
            try:
                if target == "agreement":
                    kind = _choice(LeaseDocument.DocumentType.choices, get("kind"))
                elif target == "title":
                    kind = _choice(TitleDocument.DocumentType.choices, get("kind"))
                elif target == "building":
                    kind = _choice(BuildingDocument.Category.choices, get("kind"))
            except ValueError as exc:
                row.errors.append(f"Type: {exc}")
            if not row.errors:
                filename = os.path.basename(path)
                content = ContentFile(archive.read(names[path.lower()]), name=filename)
                description = get("description") or os.path.splitext(filename)[0]
                if target == "agreement":
                    obj = LeaseDocument(lease=record, document_type=kind, description=description[:200],
                                        document_date=when, original_filename=filename)
                    exists = record.documents.filter(original_filename=filename).exists()
                elif target == "title":
                    obj = TitleDocument(title=record, document_type=kind, description=description[:200],
                                        document_date=when, original_filename=filename)
                    exists = record.documents.filter(original_filename=filename).exists()
                elif target == "plan":
                    obj = PropertyPlan(property=record, title=description[:200], drawn_on=when,
                                       original_filename=filename)
                    exists = record.plans.filter(original_filename=filename).exists()
                else:
                    obj = BuildingDocument(property=record, category=kind, title=description[:200],
                                           document_date=when, original_filename=filename)
                    exists = record.building_documents.filter(original_filename=filename).exists()
                obj.file = content
                try:
                    obj.full_clean()
                except ValidationError as exc:
                    for field, messages in exc.message_dict.items():
                        row.errors.extend(f"{field}: {m}" for m in messages)
                if exists:
                    row.warnings.append(f"{record} already has a document called {filename}. Importing adds "
                                        "another copy.")
                row.changed = [f"{TARGETS[target]} for {reference}"]
                plans.append((obj, content))
            rows.append(row)
        by_target = {t: sum(1 for r in rows if not r.errors and r.changed and r.changed[0].startswith(label))
                     for t, label in TARGETS.items()}
        summary = [(f"{label}s", by_target[t], 0, 0) for t, label in TARGETS.items() if by_target[t]]
        size = sum(len(c) for _o, c in plans)
        controls = [Control("documents:rows", "Documents: files", Decimal(len(rows))),
                    Control("documents:bytes", "Documents: total size (MB)", Decimal(size) / Decimal(1048576), 2)]

        def save():
            for obj, content in plans:
                content.seek(0)
                obj.file.save(content.name, content, save=False)
                obj.save()
            stored = sum(obj.file.size for obj, _c in plans)
            return {"documents:rows": Decimal(len(plans)),
                    "documents:bytes": Decimal(stored) / Decimal(1048576)}

        outcome = Outcome(None, rows, summary, controls, save)
        outcome.result = outcome
        return outcome


def template():
    """The index as an Excel template, with guidance."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "Documents"
    ws.append([f"{h}*" if req else h for h, _f, req, _g in COLUMNS])
    for cell in ws[1]:
        cell.font, cell.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="1D3557")
    ws.append(["leases/EX-L-001 lease.pdf", "Agreement document", "EX-L-001", "Lease or licence", "Signed lease",
               date(2024, 3, 25).strftime("%d/%m/%Y")])
    ws.append(["titles/ZZ100001.pdf", "Title document", "ZZ100001", "Official copy of the register", "", ""])
    ws.append(["plans/EX-001 ground floor.pdf", "Floor plan", "EX-001", "", "Ground floor plan", ""])
    for col, width in zip("ABCDEF", (34, 22, 16, 28, 30, 12)):
        ws.column_dimensions[col].width = width
    guide = wb.create_sheet("Guidance")
    guide.append(["Column", "Required", "Guidance"])
    for h, _f, req, g in COLUMNS:
        guide.append([h, "Yes" if req else "", g])
    guide.append([])
    guide.append(["Notes", "", "Save this sheet as index.xlsx (or index.csv) and put it in the zip with the "
                               "documents. Delete the example rows first. At most 500 documents and 50 MB in one zip: "
                               "split larger sets into several zips."])
    guide.column_dimensions["A"].width = 14
    guide.column_dimensions["C"].width = 110
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
