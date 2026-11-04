# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fill a template and turn its simple markup into Word (.docx) or an HTML preview.

Markup, one block per line or paragraph:
    # Heading            ## Subheading
    - bullet             1. numbered paragraph
    | a | b |            table row (consecutive rows make one table)
    ---                  new page
    [[signature]]        the signature block
    **bold**             inline bold
Blank lines separate paragraphs. Text in [square brackets] is highlighted for completing.
"""
import io
import re
from html import escape

from django.template import Context, Engine

from .merge import FIELDS, OPTIONAL

ENGINE = Engine(string_if_invalid="", autoescape=False)
BRACKETS = re.compile(r"(\[[^\[\]\n]{1,120}\])")
BOLD = re.compile(r"\*\*(.+?)\*\*")
ITALIC = re.compile(r"(?<![*\w])\*(?!\*)([^*\n]+?)\*(?![*\w])")


def fill(template, values, extras=()):
    """The template text with every merge field filled in; blanks become [Label] to complete."""
    data = dict(values)
    labels = {k: label for k, (_g, label) in FIELDS.items() if k not in OPTIONAL}
    labels.update({f["key"]: f.get("label", f["key"]) for f in extras if not f.get("optional")})
    for key, label in labels.items():
        if not str(data.get(key, "") or "").strip():
            data[key] = f"[{label}]"
    for key, value in list(data.items()):
        if key.startswith("hot_") and not str(value).strip():
            data[key] = "[to be agreed]"
    return ENGINE.from_string(template.body).render(Context(data, autoescape=False))


def blocks(text):
    """[(kind, payload)] with kinds h1, h2, p, bullet, number, table, pagebreak, signature."""
    out, para, table = [], [], []

    def flush():
        if para:
            out.append(("p", "\n".join(para)))
            para.clear()
        if table:
            out.append(("table", [r[:] for r in table]))
            table.clear()

    lines, pending = [], None
    for raw in text.splitlines():  # a table row may span lines when a filled-in value has line breaks
        if pending is not None:
            pending += "\n" + raw.strip()
            if raw.rstrip().endswith("|"):
                lines.append(pending)
                pending = None
            continue
        if raw.strip().startswith("|") and not raw.rstrip().endswith("|"):
            pending = raw.strip()
            continue
        lines.append(raw)
    if pending is not None:
        lines.append(pending)
    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|") and len(stripped) > 1:
            if para:
                out.append(("p", "\n".join(para)))
                para.clear()
            cells = [c.strip() for c in stripped[1:-1].split("|")]
            if not all(set(c) <= set("-: ") for c in cells):  # skip a markdown separator row
                table.append(cells)
            continue
        if table:
            out.append(("table", [r[:] for r in table]))
            table.clear()
        if not stripped:
            flush()
        elif stripped == "---":
            flush()
            out.append(("pagebreak", ""))
        elif stripped == "[[signature]]":
            flush()
            out.append(("signature", ""))
        elif stripped.startswith("## "):
            flush()
            out.append(("h2", stripped[3:]))
        elif stripped.startswith("# "):
            flush()
            out.append(("h1", stripped[2:]))
        elif stripped.startswith("- "):
            flush()
            out.append(("bullet", stripped[2:]))
        elif re.match(r"^\d+\.\s", stripped):
            flush()
            num, rest = stripped.split(" ", 1)
            out.append(("number", (num, rest)))
        else:
            para.append(stripped)
    flush()
    return out


# ------------------------------------------------------------------ HTML preview

def _inline_html(text):
    html = escape(text)
    html = BOLD.sub(r"<strong>\1</strong>", html)
    html = ITALIC.sub(r"<em>\1</em>", html)
    html = BRACKETS.sub(r'<mark class="phaema-blank">\1</mark>', html)
    return html.replace("\n", "<br>")


def to_html(text, values):
    parts = []
    for kind, payload in blocks(text):
        if kind == "h1":
            parts.append(f'<h2 class="govuk-heading-m">{_inline_html(payload)}</h2>')
        elif kind == "h2":
            parts.append(f'<h3 class="govuk-heading-s">{_inline_html(payload)}</h3>')
        elif kind == "p":
            parts.append(f'<p class="govuk-body">{_inline_html(payload)}</p>')
        elif kind == "bullet":
            parts.append(f'<p class="govuk-body phaema-doc-bullet">• {_inline_html(payload)}</p>')
        elif kind == "number":
            parts.append(f'<p class="govuk-body phaema-doc-number"><span>{escape(payload[0])}</span> '
                         f'{_inline_html(payload[1])}</p>')
        elif kind == "table":
            rows = "".join("<tr class='govuk-table__row'>" + "".join(
                f"<td class='govuk-table__cell'>{_inline_html(c)}</td>" for c in row) + "</tr>" for row in payload)
            parts.append(f'<table class="govuk-table"><tbody class="govuk-table__body">{rows}</tbody></table>')
        elif kind == "pagebreak":
            parts.append('<hr class="govuk-section-break govuk-section-break--l govuk-section-break--visible">')
        elif kind == "signature":
            parts.append(f'<p class="govuk-body">{_signature_lines(values, html=True)}</p>')
    return "\n".join(parts)


def _signature_lines(values, html=False):
    lines = ["Yours faithfully", "", "", values.get("author_name") or "[Name]",
             values.get("author_title") or "[Job title]",
             f"For and on behalf of {values.get('council_name') or 'the Council'}"]
    return "<br>".join(_inline_html(x) for x in lines) if html else lines


# ------------------------------------------------------------------ Word

def _runs(paragraph, text, size=None):
    from docx.enum.text import WD_COLOR_INDEX
    from docx.shared import Pt

    pos = 0
    tokens = []
    for m in re.finditer(r"\*\*(.+?)\*\*|(\[[^\[\]\n]{1,120}\])|(?<![*\w])\*(?!\*)([^*\n]+?)\*(?![*\w])", text):
        if m.start() > pos:
            tokens.append(("t", text[pos:m.start()]))
        if m.group(1) is not None:
            tokens.append(("b", m.group(1)))
        elif m.group(2) is not None:
            tokens.append(("m", m.group(2)))
        else:
            tokens.append(("i", m.group(3)))
        pos = m.end()
    tokens.append(("t", text[pos:]))
    for kind, chunk in tokens:
        lines = chunk.split("\n")
        for i, part in enumerate(lines):
            run = paragraph.add_run(part)
            if size:
                run.font.size = Pt(size)
            if kind == "b":
                run.bold = True
            if kind == "i":
                run.italic = True
            if kind == "m":
                run.font.highlight_color = WD_COLOR_INDEX.YELLOW
            if i < len(lines) - 1:
                run.add_break()


def _page_number(paragraph):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    run = paragraph.add_run()
    for kind, text in (("begin", None), (None, "PAGE"), ("end", None)):
        if kind:
            el = OxmlElement("w:fldChar")
            el.set(qn("w:fldCharType"), kind)
        else:
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = text
        run._r.append(el)


def to_docx(template, text, values):
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
    from docx.shared import Cm, Pt, RGBColor

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name, style.font.size = "Arial", Pt(11)
    style.paragraph_format.space_after = Pt(8)
    from docx.oxml.ns import qn

    for name, size in (("Normal", 11), ("Heading 1", 14), ("Heading 2", 12)):
        st = doc.styles[name]
        st.font.name, st.font.size = "Arial", Pt(size)
        fonts = st.element.get_or_add_rPr().get_or_add_rFonts()
        for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
            fonts.set(qn(attr), "Arial")
        for attr in ("w:asciiTheme", "w:hAnsiTheme", "w:cstheme", "w:eastAsiaTheme"):
            fonts.attrib.pop(qn(attr), None)
        if name != "Normal":
            st.font.color.rgb = RGBColor(0, 0, 0)
    section = doc.sections[0]
    section.page_height, section.page_width = Cm(29.7), Cm(21.0)
    section.left_margin = section.right_margin = Cm(2.2)
    section.top_margin, section.bottom_margin = Cm(2.0), Cm(2.0)
    if template.letterhead:
        head = section.header.paragraphs[0]
        head.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        run = head.add_run(values.get("council_name") or "")
        run.bold, run.font.size = True, Pt(13)
        details = [values.get("department"), (values.get("council_address") or "").replace("\n", ", "),
                   " · ".join(x for x in (values.get("council_phone"), values.get("council_email")) if x)]
        for line in (d for d in details if d):
            head.add_run().add_break()
            r = head.add_run(line)
            r.font.size = Pt(9)
    foot = section.footer.paragraphs[0]
    foot.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if values.get("our_ref"):
        foot.add_run(f"Our ref: {values['our_ref']}    Page ").font.size = Pt(8)
    else:
        foot.add_run("Page ").font.size = Pt(8)
    _page_number(foot)
    if template.prescribed_form:
        warn = doc.add_paragraph()
        r = warn.add_run(f"PRESCRIBED FORM: {template.prescribed_form}. The notice itself must be given on the "
                         "current version of that form (or one substantially to the like effect), including all its "
                         "notes. Transfer the particulars below into the form, and have the council's legal team "
                         "check it before it is served. Delete this paragraph before issue.")
        r.bold, r.font.size = True, Pt(9)
        r.font.color.rgb = RGBColor(0xD4, 0x35, 0x1C)
    for kind, payload in blocks(text):
        if kind == "h1":
            doc.add_heading(level=1).add_run(payload.replace("**", ""))
        elif kind == "h2":
            doc.add_heading(level=2).add_run(payload.replace("**", ""))
        elif kind == "p":
            _runs(doc.add_paragraph(), payload)
        elif kind == "bullet":
            _runs(doc.add_paragraph(style="List Bullet"), payload)
        elif kind == "number":
            p = doc.add_paragraph()
            p.paragraph_format.left_indent, p.paragraph_format.first_line_indent = Cm(1), Cm(-1)
            _runs(p, f"{payload[0]}\t{payload[1]}")
        elif kind == "table":
            cols = max(len(r) for r in payload)
            table = doc.add_table(rows=0, cols=cols)
            table.style = "Table Grid"
            for row in payload:
                cells = table.add_row().cells
                for i, value in enumerate(row):
                    _runs(cells[i].paragraphs[0], value, size=10)
            doc.add_paragraph()
        elif kind == "pagebreak":
            doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
        elif kind == "signature":
            for i, line in enumerate(_signature_lines(values)):
                p = doc.add_paragraph()
                p.paragraph_format.space_after = Pt(0 if i else 24)
                _runs(p, line)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
