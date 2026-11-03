# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest


@pytest.fixture(autouse=True)
def _test_storage(settings, tmp_path):
    """Plain static storage (no collectstatic in tests) and a throwaway folder for uploads."""
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    settings.MEDIA_ROOT = str(tmp_path / "media")
