# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "own_areas: users start with no access areas (tests of access areas)")
    config.addinivalue_line("markers", "two_step: the council's two-step sign-in rule is enforced")


@pytest.fixture(autouse=True)
def _two_step_rule(request, settings):
    """Most tests sign people in without two-step sign-in. Tests marked two_step enforce the council's rule."""
    settings.PHAEMA_ENFORCE_TWO_STEP = bool(request.node.get_closest_marker("two_step"))


@pytest.fixture(autouse=True)
def _all_access_areas(request):
    """Most tests are about what a role can do, not access areas, so new users join every area, as existing users
    did when access areas arrived. Tests marked own_areas set areas themselves."""
    if request.node.get_closest_marker("own_areas"):
        yield
        return
    from django.contrib.auth import get_user_model
    from django.db.models.signals import post_save

    def join(sender, instance, created, **kwargs):
        if created:
            from apps.core.models import AccessArea

            instance.access_areas.add(*AccessArea.objects.all())

    User = get_user_model()
    post_save.connect(join, sender=User, dispatch_uid="test_all_areas")
    yield
    post_save.disconnect(sender=User, dispatch_uid="test_all_areas")


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
