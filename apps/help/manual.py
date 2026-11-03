# SPDX-License-Identifier: AGPL-3.0-or-later
"""The user manual: Markdown files in apps/help/pages, rendered with GOV.UK styles.

Each file starts with a few "key: value" lines (title, section, order, summary) and a line of
three dashes. Links between pages are written as ordinary Markdown links to the .md file,
e.g. [rent reviews](events.md#rent-reviews), so the manual also reads correctly on GitHub.
"""
import html
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import markdown
from django.conf import settings
from django.urls import reverse

PAGES_DIR = Path(__file__).resolve().parent / "pages"
SECTIONS = ["Start here", "Records", "Key dates", "Data in and out", "Running PHAEMA", "Reference"]


@dataclass
class Page:
    slug: str
    title: str
    section: str
    order: int
    summary: str
    html: str  # the page body, without its main heading
    heading: str  # the page's main (h1) heading, as HTML
    text: str
    headings: list  # [(id, text)] of the page's level-2 headings

    def get_absolute_url(self):
        return reverse("help:page", args=[self.slug])


CLASSES = [
    (r"<h1>", '<h1 class="govuk-heading-xl">'), (r'<h1 id="', '<h1 class="govuk-heading-xl" id="'),
    (r"<h2>", '<h2 class="govuk-heading-l">'), (r'<h2 id="', '<h2 class="govuk-heading-l" id="'),
    (r"<h3>", '<h3 class="govuk-heading-m">'), (r'<h3 id="', '<h3 class="govuk-heading-m" id="'),
    (r"<h4>", '<h4 class="govuk-heading-s">'), (r'<h4 id="', '<h4 class="govuk-heading-s" id="'),
    (r"<p>", '<p class="govuk-body">'),
    (r"<ul>", '<ul class="govuk-list govuk-list--bullet">'),
    (r"<ol>", '<ol class="govuk-list govuk-list--number">'),
    (r"<table>", '<table class="govuk-table">'), (r"<thead>", '<thead class="govuk-table__head">'),
    (r"<tbody>", '<tbody class="govuk-table__body">'), (r"<tr>", '<tr class="govuk-table__row">'),
    (r"<th>", '<th scope="col" class="govuk-table__header">'), (r"<td>", '<td class="govuk-table__cell">'),
    (r"<blockquote>", '<div class="govuk-inset-text">'), (r"</blockquote>", "</div>"),
    (r"<hr />", '<hr class="govuk-section-break govuk-section-break--l govuk-section-break--visible">'),
    (r"<dl>", '<dl class="phaema-glossary">'),
]
LINK = re.compile(r'<a href="([^"]*)"')
MD_LINK = re.compile(r"^([a-z0-9-]+)\.md(#[\w-]+)?$")


def _link(match):
    href = match.group(1)
    found = MD_LINK.match(href)
    if found:
        href = reverse("help:page", args=[found.group(1)]) + (found.group(2) or "")
    external = href.startswith("http")
    extra = ' rel="noreferrer noopener" target="_blank"' if external else ""
    return f'<a class="govuk-link" href="{href}"{extra}'


def _render(body):
    md = markdown.Markdown(extensions=["toc", "tables", "attr_list", "def_list", "sane_lists"],
                           extension_configs={"toc": {"permalink": False}})
    out = md.convert(body)
    for old, new in CLASSES:
        out = out.replace(old, new)
    out = LINK.sub(_link, out)
    headings = [(t["id"], t["name"]) for top in md.toc_tokens for t in (top.get("children") or [])] or \
               [(t["id"], t["name"]) for t in md.toc_tokens if t["level"] == 2]
    return out, headings


def _parse(path):
    raw = path.read_text(encoding="utf-8")
    meta, _sep, body = raw.partition("\n---\n")
    fields = dict(line.split(":", 1) for line in meta.splitlines() if ":" in line)
    fields = {k.strip(): v.strip() for k, v in fields.items()}
    rendered, headings = _render(body)
    h1 = re.search(r"<h1[^>]*>.*?</h1>", rendered, flags=re.S)
    heading = h1.group(0) if h1 else ""
    plain = re.sub(r"</?(strong|em|a|code)\b[^>]*>", "", rendered)  # inline tags: no gap
    plain = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", plain))).strip()
    return Page(slug=path.stem, title=fields.get("title", path.stem), section=fields.get("section", "Reference"),
                order=int(fields.get("order", 99)), summary=fields.get("summary", ""), html=rendered.replace(heading, "", 1).strip(), heading=heading, text=plain,
                headings=headings)


@lru_cache(maxsize=1)
def _load():
    pages = [_parse(p) for p in PAGES_DIR.glob("*.md")]
    return {p.slug: p for p in sorted(pages, key=lambda p: (SECTIONS.index(p.section)
                                                           if p.section in SECTIONS else 99, p.order, p.title))}


def pages():
    if settings.DEBUG:
        _load.cache_clear()  # pick up edits straight away while writing the manual
    return _load()


def get(slug):
    return pages().get(slug)


def contents():
    """[(section, [pages])] in reading order."""
    grouped = {}
    for page in pages().values():
        if page.slug != "index":
            grouped.setdefault(page.section, []).append(page)
    return [(s, grouped[s]) for s in SECTIONS if s in grouped] + \
           [(s, p) for s, p in grouped.items() if s not in SECTIONS]


def neighbours(slug):
    order = [p for _s, group in contents() for p in group]
    for i, page in enumerate(order):
        if page.slug == slug:
            return (order[i - 1] if i else None), (order[i + 1] if i + 1 < len(order) else None)
    return None, (order[0] if order else None)


def search(query, limit=20):
    """Pages containing every word of the query, best matches first, with a short extract."""
    words = [w for w in re.findall(r"\w+", query.lower()) if len(w) > 1]
    if not words:
        return []
    hits = []
    for page in pages().values():
        haystack = f"{page.title} {page.summary} {page.text}".lower()
        if not all(w in haystack for w in words):
            continue
        score = sum(haystack.count(w) + 10 * page.title.lower().count(w) for w in words)
        at = page.text.lower().find(words[0])
        start = max(0, at - 80)
        snippet = ("…" if start else "") + page.text[start:start + 220].strip() + "…"
        hits.append((score, page, snippet))
    return [(p, s) for _score, p, s in sorted(hits, key=lambda h: -h[0])[:limit]]
