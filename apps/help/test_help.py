# SPDX-License-Identifier: AGPL-3.0-or-later
import re
from pathlib import Path

import pytest
from django.urls import reverse

from apps.help import manual

TEMPLATES = Path(__file__).resolve().parents[2] / "templates"


def test_every_page_has_title_section_and_summary():
    for page in manual.pages().values():
        assert page.title and page.section in manual.SECTIONS, page.slug
        assert page.summary, page.slug


def test_links_between_pages_resolve():
    pages = manual.pages()
    for page in pages.values():
        for href in re.findall(r'href="(/help/[^"]*)"', page.html):
            path, _hash, anchor = href.partition("#")
            slug = path.strip("/").split("/")[1]
            assert slug in pages, f"{page.slug} links to missing page {slug}"
            if anchor:
                assert f'id="{anchor}"' in pages[slug].html, f"{page.slug} links to missing heading {href}"


def test_help_with_this_page_links_point_to_real_pages():
    slugs = set(manual.pages())
    for template in TEMPLATES.rglob("*.html"):
        for slug in re.findall(r"{% block help_page %}([\w-]*){% endblock %}", template.read_text()):
            assert not slug or slug in slugs, f"{template.name} points to missing help page {slug}"
        for page, anchor in re.findall(r'page="([\w-]+)"(?: anchor="([\w-]+)")?', template.read_text()):
            assert page in slugs, f"{template.name} hint points to missing page {page}"
            if anchor:
                assert f'id="{anchor}"' in manual.get(page).html, f"{template.name} hint: missing #{anchor}"


@pytest.mark.django_db
def test_manual_is_readable_without_signing_in(client):
    assert client.get(reverse("help:index")).status_code == 200
    response = client.get(reverse("help:page", args=["events"]))
    assert response.status_code == 200
    assert b"Record the outcome" in response.content
    assert client.get("/help/events").status_code == 200
    assert client.get("/help/index/").status_code == 404
    assert client.get("/help/missing/").status_code == 404


@pytest.mark.django_db
def test_search(client):
    response = client.get(reverse("help:search"), {"q": "WAULT"})
    slugs = [p.slug for p, _snippet in response.context["results"]]
    assert "glossary" in slugs and "dashboard" in slugs
    assert client.get(reverse("help:search"), {"q": "zzzzqqq"}).context["results"] == []


@pytest.mark.django_db
def test_signed_in_pages_link_to_their_help(client, make_user):
    client.force_login(make_user("viewer", "Viewers"))
    content = client.get(reverse("leases:events")).content.decode()
    assert 'href="/help/events"' in content and "Help with this page" in content
    assert "Where do these events come from?" in content
