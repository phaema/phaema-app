# SPDX-License-Identifier: AGPL-3.0-or-later
"""Build the website's document pages from exports of the PHAEMA docs.

    python3 website/build_docs.py

Each document is exported from its claude.ai doc twice, as HTML and as an A4 PDF, into website/docs/source/
(<slug>.html and <slug>.pdf). Diagrams and screenshots only come through in the PDF, so this script takes the
pictures from the PDF, in order, and puts them where the HTML has a figure or an image. It writes:

    website/docs/<slug>.html   the document as a page on the website, with contents and a PDF download
    website/docs/<slug>.pdf    the PDF, for printing or sending
    website/docs/img/          the pictures
    website/training/          a copy of the e-learning (static/training)

Needs poppler-utils (pdfimages) and pypdf.
"""
import html
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "docs" / "source"
OUT = HERE / "docs"
IMG = OUT / "img"

DOCS = [
    # slug, title on the page, one-line description
    ("user-manual", "User manual", "How to do each task in PHAEMA, with worked examples from the demonstration data."),
    ("technical-manual", "Technical manual",
     "Architecture, technology, data model, security, hosting and how to extend PHAEMA."),
    ("test-programme", "Test programme",
     "The tests council staff run before go-live, with expected results to record."),
    ("integrations-review", "Integrations review",
     "The market review behind the connectors plan, including Microsoft 365 and open-source alternatives."),
]

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]

# Links between the docs on claude.ai become links between the pages here.
ARTIFACT_LINKS = {
    "CTsfQjqNtVH4qBZjg5QjRo": "user-manual.html",
    "8sTYq44xi5Ps3NuVFDrEm2": "technical-manual.html",
    "7jMMkZAmCZMEgvEfYhhiK1": "test-programme.html",
    "8nri1SACnG6YVXkp1HSJgU": "integrations-review.html",
    "7wkjDTdrtqLZwuf3zo79VE": "../training/index.html",
    "TtwKosLGe5xGLTF2EpDs6g": "../tour.html",
}


def pictures(slug, pdf):
    """Extract the PDF's pictures in reading order, once each (a tall picture can run over two pages)."""
    listing = subprocess.run(["pdfimages", "-list", str(pdf)], check=True, capture_output=True, text=True).stdout
    rows = [line.split() for line in listing.splitlines()[2:] if line.strip()]
    # columns: page num type width height color comp bpc enc interp object ID ...
    keep, seen = [], set()
    for row in rows:
        if row[2] != "image":
            continue  # soft masks and stencils
        obj = row[10]
        if obj not in seen:
            seen.add(obj)
            keep.append(int(row[1]))
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["pdfimages", "-j", "-png", str(pdf), f"{tmp}/p"], check=True)
        files = {int(p.stem.split("-")[1]): p for p in Path(tmp).iterdir()}
        names = []
        for i, num in enumerate(keep, start=1):
            src = files[num]
            name = f"{slug}-{i}{src.suffix}"
            shutil.copy(src, IMG / name)
            names.append(name)
    return names


def nice_date(iso):
    y, m, d = (int(x) for x in iso.split("-"))
    return f"{d} {MONTHS[m - 1]} {y}"


def body_html(slug, source_html, images):
    text = source_html
    # Title and byline: the page template supplies them.
    text = re.sub(r"^\s*<h1[^>]*>.*?</h1>\s*", "", text, count=1, flags=re.S)
    byline = re.match(r"\s*<p>(.*?)</p>\s*", text, flags=re.S)
    updated = ""
    if byline and "data-atom" in byline.group(1):
        found = re.search(r'datetime="(\d{4}-\d{2}-\d{2})"', byline.group(1))
        updated = nice_date(found.group(1)) if found else ""
        text = text[byline.end():]
    text = re.sub(r'<span data-atom="mention"[^>]*>@[^<]*</span>', "Stuart", text)
    text = re.sub(r'<time data-atom="date" datetime="(\d{4}-\d{2}-\d{2})">[^<]*</time>',
                  lambda m: nice_date(m.group(1)), text)

    queue = list(images)

    def place(match):
        caption, alt = match.group(1), match.group(2)
        picture = queue.pop(0) if queue else None
        if caption is not None:
            img = f'<img src="img/{picture}" alt="{caption}" loading="lazy">' if picture else ""
            return f"<figure>{img}<figcaption>{caption}</figcaption></figure>"
        return f'<img src="img/{picture}" alt="{alt}" loading="lazy">' if picture else ""

    pattern = re.compile(r'<figure data-embed="[^"]*"><figcaption>(.*?)</figcaption></figure>'
                         r'|<img src="blob/[^"]*" alt="([^"]*)"[^>]*>', re.S)
    text = pattern.sub(place, text)
    if queue:
        print(f"  {slug}: {len(queue)} picture(s) in the PDF had no place in the HTML", file=sys.stderr)

    for key, local in ARTIFACT_LINKS.items():
        text = re.sub(rf'href="https://claude\.ai/(?:code/)?artifact/(?:[^"/]*-)?{key}"', f'href="{local}"', text)
    # Wide tables scroll sideways on phones.
    text = text.replace("<table>", '<div class="table"><table>').replace("</table>", "</table></div>")
    return text, updated


def contents(text):
    items = re.findall(r'<h2 id="([^"]+)">(.*?)</h2>', text, flags=re.S)
    return "\n".join(f'<li><a href="#{i}">{t}</a></li>' for i, t in items)


PAGE = """<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} · PHAEMA</title>
<meta name="description" content="{description}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:ital,wght@0,400;0,700;1,400&family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,800&display=swap">
<style>
:root {{ --paper:#f6f8f7; --sheet:#fff; --ink:#13233a; --muted:#4a5864; --line:#cfd6d8; --edge:#c1272d;
  --survey:#2c6a3e; --link:#1b5c89; --tint:#e8efec; --focus:#ffdd00;
  --display:"Bricolage Grotesque","Arial Narrow",Arial,sans-serif; --body:"Atkinson Hyperlegible",Verdana,Arial,sans-serif; }}
@media (prefers-color-scheme: dark) {{ :root {{ --paper:#0e151d; --sheet:#15202b; --ink:#e6ecef; --muted:#a9b5be;
  --line:#2d3b48; --edge:#ff6f69; --survey:#7fc78f; --link:#86bfe9; --tint:#1a2732; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--paper); color:var(--ink); font:1.0625rem/1.6 var(--body); }}
a {{ color:var(--link); text-underline-offset:.15em; }}
a:focus-visible {{ outline:3px solid var(--focus); background:var(--focus); color:#0b0c0c; }}
.skip {{ position:absolute; left:-9999px; }} .skip:focus {{ left:16px; top:8px; background:var(--focus); color:#0b0c0c; padding:8px 12px; }}
.top {{ background:#13233a; color:#f6f8f7; }}
.top__inner {{ max-width:1180px; margin:0 auto; padding:12px 16px; display:flex; flex-wrap:wrap; gap:6px 24px; align-items:center; }}
.brand {{ color:#f6f8f7; text-decoration:none; font:800 1.3rem var(--display); letter-spacing:.14em; display:inline-flex; gap:10px; align-items:center; }}
.brand__mark {{ width:18px; height:14px; border:2.5px solid #c1272d; display:inline-block; }}
.top nav a {{ color:#f6f8f7; font-weight:700; margin-right:18px; }}
.layout {{ max-width:1180px; margin:0 auto; padding:32px 16px 64px; display:grid; grid-template-columns:260px minmax(0,1fr); gap:48px; }}
.toc {{ position:sticky; top:16px; align-self:start; max-height:calc(100vh - 32px); overflow:auto; font-size:.95rem; }}
.toc h2 {{ font:800 1rem var(--display); text-transform:uppercase; letter-spacing:.08em; color:var(--muted); }}
.toc ul {{ list-style:none; padding:0; margin:0; }} .toc li {{ margin:.45em 0; }}
article {{ background:var(--sheet); border:1px solid var(--line); border-top:4px solid var(--edge); padding:32px clamp(18px,4vw,48px); min-width:0; }}
h1, h2, h3 {{ font-family:var(--display); line-height:1.15; margin:1.6em 0 .5em; }}
h1 {{ font-size:clamp(2rem,4.5vw,3rem); margin-top:0; }} h2 {{ font-size:1.7rem; border-top:1px solid var(--line); padding-top:1em; }}
h3 {{ font-size:1.25rem; }}
.meta {{ color:var(--muted); display:flex; flex-wrap:wrap; gap:8px 20px; align-items:center; }}
.button {{ display:inline-block; background:var(--survey); color:#fff; font-weight:700; text-decoration:none; padding:8px 16px; border-radius:3px; }}
@media (prefers-color-scheme: dark) {{ .button {{ color:#0e151d; }} }}
p, li {{ max-width:75ch; }}
code {{ font-family:ui-monospace,Menlo,Consolas,monospace; font-size:.9em; background:var(--tint); padding:0 .25em; }}
pre {{ background:var(--tint); padding:12px; overflow:auto; }} pre code {{ background:none; padding:0; }}
.table {{ overflow-x:auto; margin:1em 0; }}
table {{ border-collapse:collapse; width:100%; font-size:.95rem; }}
th, td {{ border:1px solid var(--line); padding:6px 10px; text-align:left; vertical-align:top; }}
th {{ background:var(--tint); }}
figure {{ margin:1.5em 0; }} img {{ max-width:100%; height:auto; border:1px solid var(--line); }}
figcaption {{ color:var(--muted); font-size:.92rem; margin-top:.4em; }}
article > img {{ display:block; margin:1em 0; }}
.foot {{ color:var(--muted); font-size:.92rem; margin-top:3em; border-top:1px solid var(--line); padding-top:1em; }}
@media (max-width:900px) {{ .layout {{ grid-template-columns:minmax(0,1fr); }} .toc {{ position:static; max-height:none; }} }}
@media print {{ .top, .toc, .meta .button {{ display:none; }} .layout {{ display:block; padding:0; }} article {{ border:0; }} }}
</style>
</head>
<body>
<a class="skip" href="#doc">Skip to the document</a>
<header class="top"><div class="top__inner">
  <a class="brand" href="../index.html"><span class="brand__mark" aria-hidden="true"></span>PHAEMA</a>
  <nav aria-label="Website"><a href="../index.html">Website</a><a href="../index.html#resources">All resources</a><a href="../tour.html">Tour</a></nav>
</div></header>
<div class="layout">
  <nav class="toc" aria-label="Contents"><h2>Contents</h2><ul>
{contents}
  </ul></nav>
  <article id="doc">
    <h1>{title}</h1>
    <p class="meta">{updated}<a class="button" href="{slug}.pdf" download>Download PDF</a></p>
{body}
    <p class="foot">PHAEMA is free software under the GNU Affero General Public License v3.0. Screenshots show fictional
    demonstration data. Questions or corrections: <a href="mailto:stuart@phaema.co.uk">stuart@phaema.co.uk</a>.</p>
  </article>
</div>
</body>
</html>
"""


def build():
    IMG.mkdir(parents=True, exist_ok=True)
    for old in IMG.iterdir():
        old.unlink()
    for slug, title, description in DOCS:
        source_html = (SOURCE / f"{slug}.html").read_text(encoding="utf-8")
        pdf = SOURCE / f"{slug}.pdf"
        images = pictures(slug, pdf)
        body, updated = body_html(slug, source_html, images)
        page = PAGE.format(title=html.escape(title), description=html.escape(description), slug=slug,
                           contents=contents(body), body=body,
                           updated=f"<span>Updated {updated}</span>" if updated else "")
        (OUT / f"{slug}.html").write_text(page, encoding="utf-8")
        shutil.copy(pdf, OUT / f"{slug}.pdf")
        print(f"Wrote {OUT / slug}.html ({len(images)} pictures) and {slug}.pdf")
    training = HERE / "training"
    if training.exists():
        shutil.rmtree(training)
    shutil.copytree(HERE.parent / "static" / "training", training)
    # Inside PHAEMA the footer links to its help; on the website it links to the user manual.
    index = training / "index.html"
    index.write_text(index.read_text(encoding="utf-8").replace(
        '<a href="/help/">Back to the PHAEMA manual</a>', '<a href="../docs/user-manual.html">The PHAEMA user manual</a>'
        ' · <a href="../index.html">PHAEMA website</a>'), encoding="utf-8")
    print(f"Copied the training to {training}")


if __name__ == "__main__":
    build()
