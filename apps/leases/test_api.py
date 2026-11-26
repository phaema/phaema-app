# SPDX-License-Identifier: AGPL-3.0-or-later
"""Agreements saved through the API get the same checks as on screen."""
from datetime import date

import pytest
from django.contrib.auth.models import Group, User
from django.test import Client

from apps.leases.models import Lease, Party


@pytest.fixture
def api(db):
    user = User.objects.create_user("ann", password="a-long-test-password")
    user.groups.add(Group.objects.get(name="Administrators"))
    client = Client(HTTP_HOST="localhost")
    client.force_login(user)
    return client


def test_expiry_before_start_refused(api):
    lease = Lease.objects.create(reference="L-1", term_start=date(2020, 1, 1),
                                 counterparty=Party.objects.create(name="Acme Ltd"))
    response = api.patch(f"/api/leases/{lease.pk}/", {"term_end": "2019-12-31"}, content_type="application/json")
    assert response.status_code == 400
    assert "term_end" in response.json()
    assert api.patch(f"/api/leases/{lease.pk}/", {"term_end": "2030-12-31"},
                     content_type="application/json").status_code == 200
