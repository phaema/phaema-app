# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, InternalError, ProgrammingError, connection, transaction

from apps.core.models import AuditEntry

pytestmark = pytest.mark.django_db

REFUSED = (InternalError, ProgrammingError, IntegrityError)


def test_pages_carry_a_content_security_policy_with_a_nonce(client):
    response = client.get("/login/")
    policy = response["Content-Security-Policy"]
    assert "script-src 'self' 'nonce-" in policy
    assert "object-src 'none'" in policy and "frame-ancestors 'none'" in policy
    nonce = policy.split("'nonce-")[1].split("'")[0]
    page = response.content.decode()
    assert f'nonce="{nonce}"' in page
    assert page.count("<script") == page.count("nonce=") + page.count("src=")  # no inline script without a nonce
    assert response["Permissions-Policy"].startswith("camera=()")


def test_each_request_gets_a_new_nonce(client):
    first = client.get("/login/")["Content-Security-Policy"]
    second = client.get("/login/")["Content-Security-Policy"]
    assert first != second


def test_report_only_and_off(client, settings):
    settings.PHAEMA_CSP_REPORT_ONLY = True
    response = client.get("/login/")
    assert "Content-Security-Policy" not in response
    assert "Content-Security-Policy-Report-Only" in response
    settings.PHAEMA_CSP_ENABLED = False
    assert "Content-Security-Policy-Report-Only" not in client.get("/login/")


def test_extra_map_sources(client, settings):
    settings.PHAEMA_CSP_IMG_SOURCES = ["https://tiles.example.gov.uk"]
    directives = dict(part.split(" ", 1) for part in client.get("/login/")["Content-Security-Policy"].split("; "))
    assert directives["img-src"].split()[-1] == "https://tiles.example.gov.uk"


def _entry(user=None):
    return AuditEntry.objects.create(user=user, content_type=ContentType.objects.get_for_model(AuditEntry),
                                     object_id="1", object_repr="x", action="create")


def test_the_database_refuses_to_change_or_delete_the_audit_trail():
    entry = _entry()
    with pytest.raises(REFUSED), transaction.atomic():
        AuditEntry.objects.filter(pk=entry.pk).update(object_repr="changed")
    with pytest.raises(REFUSED), transaction.atomic():
        AuditEntry.objects.filter(pk=entry.pk).delete()
    with connection.cursor() as cursor:  # TRUNCATE is refused too (not run here: the test's insert is still pending)
        cursor.execute("SELECT tgname FROM pg_trigger WHERE tgrelid = 'core_auditentry'::regclass")
        assert {"phaema_audit_no_change", "phaema_audit_no_truncate"} <= {row[0] for row in cursor.fetchall()}
    assert AuditEntry.objects.get(pk=entry.pk).object_repr == "x"


def test_deleting_a_user_keeps_their_entries():
    user = get_user_model().objects.create_user("leaver", password="x" * 20)
    entry = _entry(user)
    user.delete()
    entry = AuditEntry.objects.get(pk=entry.pk)
    assert entry.user is None and entry.object_repr == "x"


def test_a_retention_purge_can_switch_the_lock_off_for_one_transaction():
    entry = _entry()
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SET LOCAL phaema.audit_purge = 'on'")
        AuditEntry.objects.filter(pk=entry.pk).delete()
    assert not AuditEntry.objects.filter(pk=entry.pk).exists()
