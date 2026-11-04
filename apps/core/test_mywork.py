# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import date, timedelta
from decimal import Decimal as D

from apps.cases import workflow
from apps.cases.models import CaseType
from apps.core import mywork
from apps.core.models import StaffProfile
from apps.leases.models import Lease, LeaseEvent, Party
from apps.properties.models import Property


def _estate(surveyor):
    estate = Property.objects.create(reference="E1", name="Estate", property_type="estate", managing_surveyor=surveyor)
    unit = Property.objects.create(reference="E1-U1", name="Unit 1", property_type="unit", parent=estate)
    lease = Lease.objects.create(reference="L1", agreement_type="lease", annual_rent=D("12000"),
                                 counterparty=Party.objects.create(name="Tenant Ltd", party_type="company"),
                                 term_start=date(2020, 1, 1), term_end=date(2030, 12, 31))
    lease.properties.add(unit)
    return estate, unit, lease


def test_my_work_lists_what_is_due(client, make_user):
    surveyor = make_user("surv", "Surveyors")
    estate, unit, lease = _estate(surveyor)
    today = date.today()
    LeaseEvent.objects.create(lease=lease, event_type="review", due_date=today - timedelta(days=5))  # unassigned
    LeaseEvent.objects.create(lease=lease, event_type="expiry", due_date=today + timedelta(days=30))
    LeaseEvent.objects.create(lease=lease, event_type="review", due_date=today + timedelta(days=400))  # too far
    case = workflow.open_case(CaseType.objects.get(code="enquiry"), title="Query", property=unit)
    case.owner, case.target_date = surveyor, today - timedelta(days=1)
    case.save()
    data = mywork.build(surveyor)
    assert data["property_count"] == 2  # the estate and its unit
    assert len(data["now"]) == 2 and len(data["ahead"]) == 1
    assert data["properties"][0]["rent"] == D("12000") and data["properties"][0]["parts"] == 1

    client.force_login(surveyor)
    page = client.get("/").content.decode()  # surveyors land on My work
    assert "Needs attention now" in page and "Query" in page and "E1" in page
    estate_page = client.get("/?view=estate")
    assert "Register by type" in estate_page.content.decode()
    assert "Register by type" in client.get("/").content.decode()  # the choice is remembered


def test_who_can_see_whose_work(client, make_user):
    head, surveyor, other = make_user("head", "Surveyors"), make_user("surv", "Surveyors"), make_user("x", "Surveyors")
    admin = make_user("admin", "Administrators")
    StaffProfile.objects.create(user=surveyor, supervisor=head)
    client.force_login(head)
    assert client.get(f"/?view=mine&person={surveyor.pk}").status_code == 200
    assert client.get(f"/?view=mine&person={other.pk}").status_code == 403
    client.force_login(surveyor)
    assert client.get(f"/?view=mine&person={head.pk}").status_code == 403
    client.force_login(admin)
    page = client.get(f"/?view=mine&person={other.pk}").content.decode()
    assert "Work for x" in page and "admin (administrator)" in page  # the header still shows who is signed in


def test_styles(client, make_user):
    client.force_login(make_user("v", "Viewers"))
    assert 'data-skin="classic"' in client.get("/").content.decode()
    response = client.get("/style/clear/?next=/")
    assert response.status_code == 302 and response.cookies["phaema_skin"].value == "clear"
    assert 'data-skin="clear"' in client.get("/").content.decode()
    assert client.get("/style/purple/").status_code == 404
    page = client.get("/").content.decode()
    assert 'data-panel="estate-types"' in page and "phaema-panel__body" in page  # viewers land on the estate
