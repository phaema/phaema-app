# SPDX-License-Identifier: AGPL-3.0-or-later
"""The user manual. It is open to everyone, including before signing in."""
from django.http import Http404
from django.shortcuts import render

from . import manual


def _context(**extra):
    return {"contents": manual.contents(), **extra}


def index(request):
    page = manual.get("index")
    return render(request, "help/page.html", _context(page=page, is_index=True, next_page=manual.neighbours("")[1]))


def page(request, slug):
    found = manual.get(slug)
    if found is None or slug == "index":
        raise Http404
    previous, following = manual.neighbours(slug)
    return render(request, "help/page.html", _context(page=found, previous_page=previous, next_page=following))


def search(request):
    q = request.GET.get("q", "").strip()[:100]
    return render(request, "help/search.html", _context(q=q, results=manual.search(q) if q else []))
