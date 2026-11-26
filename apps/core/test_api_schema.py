# SPDX-License-Identifier: AGPL-3.0-or-later
"""The OpenAPI description at /api/schema/ builds without warnings and is valid."""
from django.core.management import call_command


def test_api_schema_has_no_warnings(tmp_path, db):
    call_command("spectacular", "--validate", "--fail-on-warn", "--file", str(tmp_path / "schema.yml"))
    text = (tmp_path / "schema.yml").read_text()
    assert "apiToken:" in text and "YesNoEnum" in text
