# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import date
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.urls import reverse

from apps.leases import events
from apps.leases.models import BreakOption, Lease, LeaseDocument, Party
from apps.properties.models import Property

TODAY = date(2026, 11, 3)


@pytest.fixture
def setup(db):
    inv = Property.objects.create(reference="P1", name="Shop", property_type="unit", holding_purpose="investment")
    com = Property.objects.create(reference="P2", name="Hall", property_type="building", holding_purpose="community")
    tenant = Party.objects.create(name="Tenant Ltd", party_type="company")
    guarantor = Party.objects.create(name="Parent plc", party_type="company")
    landlord = Party.objects.create(name="Landlord Ltd", party_type="company")

    def lease(ref, prop, party=tenant, **kw):
        obj = Lease.objects.create(reference=ref, agreement_type="lease", counterparty=party, **kw)
        obj.properties.add(prop)
        return obj

    review_overdue = lease("A", inv, term_start=date(2020, 1, 1), term_end=date(2030, 12, 31), annual_rent=Decimal("10000"),
                           review_basis="om_up", next_review_date=date(2026, 6, 1), guarantor=guarantor)
    lease("B", inv, term_start=date(2021, 1, 1), term_end=date(2026, 9, 30), annual_rent=Decimal("5000"))  # expired, still current
    lease("C", inv, status="holding_over", term_start=date(2016, 1, 1), term_end=date(2025, 12, 31), annual_rent=Decimal("3000"))
    soon = lease("D", com, term_start=date(2024, 1, 1), term_end=date(2027, 3, 31), annual_rent=Decimal("2000"),
                 review_basis="cpi", next_review_date=date(2027, 1, 1))
    BreakOption.objects.create(lease=soon, break_date=date(2027, 6, 1), exercisable_by="tenant", notice_months=6)  # notice 1 Dec 2026
    lease("E", com, term_start=date(2020, 1, 1), term_end=None, annual_rent=Decimal("0"), rent_frequency="peppercorn")
    lease("F", inv, status="ended", term_start=date(2010, 1, 1), term_end=date(2015, 1, 1), annual_rent=Decimal("9999"),
          next_review_date=date(2012, 1, 1), review_basis="om_up")  # ended: never counted
    lease("G", com, party=landlord, direction="in", term_start=date(2004, 1, 1), term_end=date(2100, 1, 1),
          annual_rent=Decimal("750"))
    return {"tenant": tenant, "guarantor": guarantor, "review_overdue": review_overdue}


def test_event_summary(setup):
    rows = {r["type"]: r for r in events.event_summary(TODAY)}
    assert rows["review"]["overdue"] == 1 and rows["review"]["due"] == 1       # A overdue, D due
    assert rows["expiry"]["overdue"] == 1 and rows["expiry"]["due"] == 1       # B expired but current; D soon
    assert rows["holding_over"]["overdue"] == 1                                # C (not double counted as expiry)
    assert rows["notice"]["due"] == 1 and rows["notice"]["overdue"] is None
    assert rows["break"]["due"] == 0
    # the lease list filters (used from lease searches) agree
    assert [lease.reference for lease in events.filter_leases(Lease.objects.all(), "review_overdue", TODAY)] == ["A"]
    assert [lease.reference for lease in events.filter_leases(Lease.objects.all(), "notice_due", TODAY)] == ["D"]


def test_rent_roll_and_wault(setup):
    roll = events.rent_roll(TODAY)
    assert roll["total"] == Decimal("20000") and roll["agreements"] == 5 and roll["nil_rent"] == 1
    assert dict(roll["by_purpose"])["Investment"]["rent"] == Decimal("18000")
    assert roll["payable"] == Decimal("750") and roll["payable_count"] == 1
    # WAULT to expiry: A 10000 x 4.16y, B and C expired (0), D 2000 x 0.4y; periodic E excluded
    assert Decimal("2.0") < roll["wault_expiry"] < Decimal("2.3")
    assert roll["wault_break"] <= roll["wault_expiry"]


def test_party_arrangements(setup):
    tenant, guarantor = setup["tenant"], setup["guarantor"]
    rows = tenant.arrangements()
    assert {r["lease"].reference for r in rows} == {"A", "B", "C", "D", "E", "F"}
    assert {str(r["role"]) for r in rows} == {"Tenant"}
    assert [str(r["role"]) for r in guarantor.arrangements()] == ["Guarantor"]
    assert [p.reference for p in tenant.properties_involved()] == ["P1", "P2"]


def test_party_pages(client, make_user, setup):
    client.force_login(make_user("ann", "Administrators"))
    tenant = setup["tenant"]
    resp = client.get(reverse("leases:parties"), {"sort": "-rent"})
    names = [p.name for p in resp.context["page_obj"]]
    assert names[0] == "Tenant Ltd"
    html = client.get(tenant.get_absolute_url()).content.decode()
    assert "Shop" in html and "Hall" in html and "5 current agreements" in html
    html = client.get(reverse("admin:leases_party_change", args=[tenant.pk])).content.decode()
    assert "All agreements and properties" in html and "P1 Shop" in html and "Open the full party page" in html
    html = client.get(reverse("admin:leases_party_change", args=[setup["guarantor"].pk])).content.decode()
    assert "Guarantor" in html


def test_dashboard_sections(client, make_user, setup):
    client.force_login(make_user("vic", "Viewers"))
    html = client.get(reverse("dashboard")).content.decode()
    assert "Lease events" in html and "Rent roll" in html and "window=overdue" in html and "WAULT to expiry" in html


def test_lease_documents(client, make_user, db, tmp_path):
    call_command("load_demo_data", verbosity=0)
    lease = Lease.objects.get(reference="DL-0003")
    assert lease.documents.count() == 1
    viewer = make_user("vic", "Viewers")
    client.force_login(viewer)
    html = client.get(lease.get_absolute_url()).content.decode()
    doc = lease.documents.first()
    assert doc.file.url in html and "Add documents" not in html
    assert client.get(doc.file.url).status_code == 200

    # The managing surveyor of the premises can add documents; others cannot.
    owner = lease.properties.first().managing_surveyor
    owner.set_password("a-long-test-password"); owner.save()
    client.force_login(owner)
    assert "Add documents" in client.get(lease.get_absolute_url()).content.decode()
    other = make_user("sue", "Surveyors")
    client.force_login(other)
    assert "Add documents" not in client.get(lease.get_absolute_url()).content.decode()

    bad = LeaseDocument(lease=lease, document_type="lease", file=SimpleUploadedFile("x.pdf", b"not a pdf"))
    with pytest.raises(Exception):
        bad.full_clean()
    path = doc.file.path
    doc.delete()
    import os
    assert not os.path.exists(path)


def test_party_list_does_not_double_count_tenant_who_is_also_guarantor(client, make_user, setup):
    tenant = setup["tenant"]
    other = Party.objects.create(name="Other Ltd", party_type="company")
    extra = Lease.objects.create(reference="H", agreement_type="lease", counterparty=other, guarantor=tenant,
                                 term_start=date(2024, 1, 1), annual_rent=Decimal("1"))
    extra.properties.add(Property.objects.first())
    client.force_login(make_user("ann", "Administrators"))
    row = next(p for p in client.get(reverse("leases:parties")).context["page_obj"] if p.pk == tenant.pk)
    assert row.n_current == 5 and row.current_rent == Decimal("20000") and row.n_guarantees
