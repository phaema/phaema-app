# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path

import pytest
from django.conf import settings

from apps.core.models import ModuleSettings

pytestmark = pytest.mark.django_db

PO = Path(settings.BASE_DIR) / "locale" / "cy" / "LC_MESSAGES" / "django.po"
MO = PO.with_suffix(".mo")


def offer_welsh(on=True):
    modules = ModuleSettings.load()
    modules.welsh_enabled = on
    modules.save()


def test_english_unless_the_council_offers_welsh(client):
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = "cy"
    page = client.get("/login/", HTTP_ACCEPT_LANGUAGE="cy")
    assert page["Content-Language"] == "en"
    assert "Sign in" in page.content.decode()
    assert "Cymraeg" not in page.content.decode()  # no switch shown


def test_the_browser_language_alone_does_not_switch_to_welsh(client):
    offer_welsh()
    page = client.get("/login/", HTTP_ACCEPT_LANGUAGE="cy")
    assert page["Content-Language"] == "en"
    assert 'href="/language/cy/' in page.content.decode()


def test_choosing_cymraeg_shows_welsh(client):
    offer_welsh()
    response = client.get("/language/cy/?next=/login/")
    assert response.status_code == 302 and response["Location"] == "/login/"
    page = client.get("/login/")
    html = page.content.decode()
    assert page["Content-Language"] == "cy"
    assert '<html lang="cy"' in html
    assert "Mewngofnodi i PHAEMA" in html
    assert 'href="/language/en/' in html


def test_unknown_language_and_unsafe_next(client):
    assert client.get("/language/fr/").status_code == 404
    response = client.get("/language/cy/?next=https://example.com/")
    assert response["Location"] == "/"


def test_welsh_draft_is_complete_and_marked_for_review():
    text = PO.read_text(encoding="utf-8")
    assert "awaiting review" in text
    assert '\nmsgstr ""\n\n' not in text.split("\n\n", 1)[1]  # every entry after the header is translated
    # The compiled file is there and up to date: phrases added late in the draft read in Welsh.
    from django.utils.translation import gettext, override
    assert MO.exists()
    with override("cy"):
        assert gettext("Sign in to PHAEMA") == "Mewngofnodi i PHAEMA"
        assert gettext("Hide all") == "Cuddio'r cyfan"
