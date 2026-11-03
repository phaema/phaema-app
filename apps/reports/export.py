# SPDX-License-Identifier: AGPL-3.0-or-later
"""Write tables to Excel (.xlsx) or CSV for download."""
import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal

from django.http import HttpResponse
from django.utils import timezone

from .datasets import NUMERIC

FORMATS = {"money": "£#,##0.00", "area": "#,##0.00", "number": "#,##0", "date": "dd/mm/yyyy"}
MAX_ROWS = 100_000


def _clean(value):
    if isinstance(value, datetime):
        value = timezone.localtime(value).date() if timezone.is_aware(value) else value.date()
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if value is None:
        return ""
    if isinstance(value, (date, Decimal, int, float)):
        return value
    text = str(value)
    # Stop spreadsheet programs treating text as a formula (CSV/formula injection).
    if text[:1] in ("=", "+", "-", "@", "\t", "\r"):
        text = "'" + text
    return text


def _filename(title, ext):
    slug = re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-").lower() or "phaema"
    return f"{slug}-{date.today():%Y-%m-%d}.{ext}"


def xlsx_response(title, fields, row_iter, totals=False):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = re.sub(r"[\[\]\*\?/\\:]", "", title)[:31] or "PHAEMA"
    ws.append([f.label for f in fields])
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1D3557")
    widths = [len(f.label) for f in fields]
    sums = [Decimal("0") for _f in fields]
    n = 0
    for row in row_iter:
        n += 1
        if n > MAX_ROWS:
            break
        values = [_clean(v) for v in row]
        ws.append(values)
        for i, (f, v) in enumerate(zip(fields, values)):
            widths[i] = min(max(widths[i], len(str(v)) if not isinstance(v, date) else 10), 60)
            if f.type in NUMERIC and isinstance(v, (int, float, Decimal)):
                sums[i] += Decimal(str(v))
    for i, f in enumerate(fields, start=1):
        letter = get_column_letter(i)
        ws.column_dimensions[letter].width = widths[i - 1] + 2
        if f.type in FORMATS:
            for cell in ws[letter][1:]:
                cell.number_format = FORMATS[f.type]
    if totals and n:
        ws.append([("Total" if i == 0 else (sums[i] if f.type in ("money", "area") else "")) for i, f in enumerate(fields)])
        for i, f in enumerate(fields, start=1):
            cell = ws.cell(ws.max_row, i)
            cell.font = Font(bold=True)
            if f.type in FORMATS:
                cell.number_format = FORMATS[f.type]
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(fields))}{max(n + 1, 1)}"
    out = io.BytesIO()
    wb.save(out)
    response = HttpResponse(out.getvalue(),
                            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="{_filename(title, "xlsx")}"'
    return response


def csv_response(title, fields, row_iter):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{_filename(title, "csv")}"'
    response.write("﻿")  # so Excel opens UTF-8 (e.g. £ and ²) correctly
    writer = csv.writer(response)
    writer.writerow([f.label for f in fields])
    for n, row in enumerate(row_iter):
        if n >= MAX_ROWS:
            break
        writer.writerow([v.strftime("%d/%m/%Y") if isinstance(v, date) else v for v in map(_clean, row)])
    return response


def download(request, title, dataset, qs, columns=None, totals=False):
    """Respond with the export the request asked for (?format=xlsx or csv), or None."""
    from .datasets import rows

    fmt = request.GET.get("format")
    if fmt not in ("xlsx", "csv"):
        return None
    fields, row_iter = rows(dataset, qs, columns or dataset.default_columns)
    if fmt == "xlsx":
        return xlsx_response(title, fields, row_iter, totals)
    return csv_response(title, fields, row_iter)
