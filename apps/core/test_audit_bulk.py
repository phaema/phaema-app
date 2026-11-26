# SPDX-License-Identifier: AGPL-3.0-or-later
"""Changes made in bulk (QuerySet.update, bulk_create) reach the change log too."""
from datetime import date

import pytest
from django.contrib.contenttypes.models import ContentType

from apps.core.audit import audited_create, audited_update
from apps.core.models import AuditEntry
from apps.properties.models import Property


def _entries(model, action):
    return AuditEntry.objects.filter(content_type=ContentType.objects.get_for_model(model), action=action)


@pytest.mark.django_db
def test_audited_update_logs_each_changed_record_only():
    a = Property.objects.create(reference="A", name="A", purpose_review_date=date(2027, 1, 1))
    b = Property.objects.create(reference="B", name="B", purpose_review_date=date(2028, 1, 1))
    before = _entries(Property, "update").count()
    count = audited_update(Property.objects.filter(pk__in=[a.pk, b.pk]), purpose_review_date=date(2028, 1, 1))
    assert count == 2
    new = list(_entries(Property, "update").order_by("pk"))[before:]
    assert [e.object_id for e in new] == [str(a.pk)]  # b already had that date
    assert new[0].changes == {"purpose_review_date": ["2027-01-01", "2028-01-01"]}
    a.refresh_from_db()
    assert a.purpose_review_date == date(2028, 1, 1)


@pytest.mark.django_db
def test_audited_create_logs_each_new_record():
    before = _entries(Property, "create").count()
    made = audited_create(Property, [Property(reference="C", name="C"), Property(reference="D", name="D")])
    assert len(made) == 2 and _entries(Property, "create").count() == before + 2


@pytest.mark.django_db
def test_new_events_get_the_surveyor_in_the_change_log(make_user):
    from apps.leases.models import Lease, LeaseEvent, Party
    from apps.leases.workflow import sync_events

    sam = make_user("sam", "Surveyors")
    prop = Property.objects.create(reference="U-1", name="Unit 1", managing_surveyor=sam)
    lease = Lease.objects.create(reference="L-1", term_start=date(2020, 1, 1), term_end=date(2030, 1, 1),
                                 counterparty=Party.objects.create(name="Acme Ltd"))
    lease.properties.add(prop)
    event = LeaseEvent.objects.create(lease=lease, event_type="other", due_date=date(2029, 6, 1), title="Check")
    sync_events(lease)
    event.refresh_from_db()
    assert event.assigned_to == sam
    entry = _entries(LeaseEvent, "update").filter(object_id=str(event.pk)).latest("pk")
    assert entry.changes["assigned_to"][1] == str(sam.pk)


def test_strategy_review_date_is_logged_on_the_property(db):
    from apps.core.models import ModuleSettings
    from apps.properties.models import AssetStrategy, AssetStrategyOption

    ModuleSettings.load()
    depot = Property.objects.create(reference="D-1", name="Depot")
    option = AssetStrategyOption.objects.first() or AssetStrategyOption.objects.create(name="Retain as is")
    AssetStrategy.objects.create(property=depot, strategy=option, decided_on=date(2026, 1, 10), reason="Needed")
    entry = _entries(Property, "update").filter(object_id=str(depot.pk)).latest("pk")
    assert "purpose_review_date" in entry.changes
