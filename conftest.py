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


@pytest.fixture
def make_user(db):
    """make_user("name", "Surveyors") creates a user in a PHAEMA role group."""
    from django.contrib.auth.models import Group, User

    def make(username, role=None, **extra):
        user = User.objects.create_user(username, password="a-long-test-password", **extra)
        if role:
            user.groups.add(Group.objects.get(name=role))
            user.refresh_from_db()
        return user

    return make
