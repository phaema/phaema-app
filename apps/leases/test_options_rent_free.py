# SPDX-License-Identifier: AGPL-3.0-or-later
"""Agreement terms added 18 November: rent-free period end, and options to renew, extend, purchase and others."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import reverse

from apps.core.models import ModuleSettings
from apps.core.roles import ADMINISTRATORS
from apps.leases import workflow
from apps.leases.models import Lease, LeaseEvent, LeaseOption, Party
from apps.properties.models import Property

TODAY = date.today()


@pytest.fixture
def lease(db):
    prop = Property.objects.create(reference="P1", name="Shop", property_type="unit", holding_purpose="investment")
    tenant = Party.objects.create(name="Tenant Ltd", party_type="company")
    guarantor = Party.objects.create(name="Parent plc", party_type="company")
    obj = Lease.objects.create(reference="L1", counterparty=tenant, guarantor=guarantor, agreement_type="lease",
                               term_start=TODAY - timedelta(days=30), term_end=TODAY + timedelta(days=3650),
                               annual_rent=Decimal("12000"), rent_free_until=TODAY + timedelta(days=150),
                               incentives="6 months rent-free")
    obj.properties.add(prop)
    return obj


def test_rent_free_end_creates_an_event(lease):
    event = lease.events.get(source="rent_start")
    assert event.event_type == LeaseEvent.EventType.RENT_START
    assert event.due_date == lease.rent_free_until
    lease.rent_free_until = None
    lease.save()
    assert not lease.events.filter(source="rent_start").exists()


def test_option_creates_event_and_follows_changes(lease):
    option = LeaseOption.objects.create(lease=lease, option_type="renew", exercise_by=TODAY + timedelta(days=400),
                                        notice_months=6, terms="New 10-year lease at open market rent")
    event = lease.events.get(source=f"option:{option.pk}")
    assert event.event_type == LeaseEvent.EventType.OPTION
    assert event.title == "Last date: option to renew (tenant only)"
    option.exercise_by = TODAY + timedelta(days=500)
    option.save()
    event.refresh_from_db()
    assert event.due_date == option.exercise_by
    option.delete()
    assert not lease.events.filter(source__startswith="option:").exists()


def test_option_without_a_date_creates_no_event(lease):
    LeaseOption.objects.create(lease=lease, option_type="first_refusal", terms="On any sale of the freehold")
    assert not lease.events.filter(source__startswith="option:").exists()


def test_key_dates_include_options_and_rent_start(lease):
    LeaseOption.objects.create(lease=lease, option_type="purchase", exercise_by=TODAY + timedelta(days=90))
    kinds = [kind for _d, _label, kind in lease.key_dates()]
    assert "option" in kinds and "rent_start" in kinds


def test_option_reminders_have_their_own_days(db):
    settings = ModuleSettings.load()
    assert settings.reminder_days("option") == [180, 90, 30, 7]
    assert settings.reminder_days("rent_start") == settings.reminder_days("other")


def test_agreement_page_shows_new_terms(client, lease):
    LeaseOption.objects.create(lease=lease, option_type="renew", exercise_by=TODAY + timedelta(days=400),
                               terms="New lease for 5 years")
    user = get_user_model().objects.create_user("boss", password="x", is_staff=True)
    user.groups.add(Group.objects.get(name=ADMINISTRATORS))
    client.force_login(user)
    page = client.get(lease.get_absolute_url()).content.decode()
    assert "Rent-free until" in page
    assert "Option to renew" in page and "New lease for 5 years" in page
    assert "Parent plc" in page  # guarantor, already held


def test_surveyors_can_edit_options(make_user):
    surveyor = make_user("sue", "Surveyors")
    assert surveyor.has_perm("leases.add_leaseoption") and surveyor.has_perm("leases.change_leaseoption")


def test_admin_form_has_options_and_rent_free(client, lease):
    user = get_user_model().objects.create_user("boss2", password="x", is_staff=True)
    user.groups.add(Group.objects.get(name=ADMINISTRATORS))
    client.force_login(user)
    page = client.get(reverse("admin:leases_lease_change", args=[lease.pk])).content.decode()
    assert "rent_free_until" in page and "options-TOTAL_FORMS" in page
