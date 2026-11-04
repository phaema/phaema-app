# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import date, timedelta
from decimal import Decimal

import pytest

from apps.core.models import ModuleSettings, StaffProfile
from apps.leases.models import Lease, Party
from apps.maintenance import responsibility, workflow
from apps.maintenance.models import Component, Contract, Contractor, Job, PlannedTask
from apps.properties.models import Property


@pytest.fixture
def setup(db, make_user):
    settings = ModuleSettings.load()
    settings.maintenance_enabled = settings.rent_ledger_enabled = True
    settings.save()
    surveyor = make_user("surv", "Surveyors", email="surv@example.org")
    building = Property.objects.create(reference="B1", name="Block", property_type="building",
                                       managing_surveyor=surveyor)
    unit = Property.objects.create(reference="U1", name="Unit 1", property_type="unit", parent=building,
                                   managing_surveyor=surveyor)
    tenant = Party.objects.create(name="Tenant Ltd", party_type="company")
    lease = Lease.objects.create(reference="L1", agreement_type="lease", counterparty=tenant,
                                 term_start=date(2020, 1, 1), annual_rent=Decimal("10000"), repairing="iri",
                                 service_charge_payable=True)
    lease.properties.add(unit)
    contractor = Contractor.objects.create(name="Fixit Ltd", email="orders@example.org",
                                           insurance_expires=date.today() + timedelta(days=100))
    return {"surveyor": surveyor, "building": building, "unit": unit, "lease": lease, "contractor": contractor}


def test_who_pays_follows_the_lease(setup):
    unit, building, lease = setup["unit"], setup["building"], setup["lease"]
    assert responsibility.decide(unit, "internal")[0] == "tenant"
    assert responsibility.decide(unit, "roof")[:1] == ("service",)
    assert responsibility.decide(building, "roof")[0] == "service"  # common parts of a let building
    lease.repairing = "fri"
    lease.save()
    assert responsibility.decide(unit, "roof")[0] == "tenant"
    lease.status = "ended"
    lease.save()
    assert responsibility.decide(unit, "roof")[0] == "landlord"
    assert len(responsibility.matrix(unit)) == 10


def test_reactive_job_through_to_recharge(client, setup, mailoutbox):
    client.force_login(setup["surveyor"])
    response = client.post("/maintenance/jobs/new/", {
        "property": setup["unit"].pk, "title": "Broken window", "category": "external", "priority": "urgent",
        "how_reported": "tenant", "reported_on": "2026-11-02"})
    job = Job.objects.get()
    assert response["Location"] == job.get_absolute_url()
    assert job.reference == f"JOB-2026-{job.number:04d}" and job.lease == setup["lease"]
    assert job.responsibility == "service" and job.target_date == date(2026, 11, 9)  # 5 working days
    url = job.get_absolute_url()
    client.post(url, {"action": "order_details", "contractor": setup["contractor"].pk, "estimate": "350"})
    client.post(url, {"action": "issue_order", "email": "1"})
    job.refresh_from_db()
    assert job.status == "ordered" and mailoutbox[-1].to == ["orders@example.org"]
    assert job.reference in mailoutbox[-1].body
    assert client.get(f"{url}order/").status_code == 200
    client.post(url, {"action": "responsibility", "responsibility": "recharge", "reason": "Tenant's van"})
    client.post(url, {"action": "complete", "date": "2026-11-05", "cost": "380.00", "invoice": "F-1"})
    client.post(url, {"action": "recharge"})
    client.post(url, {"action": "recharge"})  # not twice
    job.refresh_from_db()
    assert job.status == "completed" and job.recharge.net == Decimal("380.00")
    assert setup["lease"].charges.count() == 1


def test_large_orders_need_approval(client, make_user, setup):
    head = make_user("head", "Surveyors")
    job = workflow.open_job(setup["building"], "New roof", category="roof", contractor=setup["contractor"],
                            estimate=Decimal("9000"))
    url = job.get_absolute_url()
    client.force_login(setup["surveyor"])
    client.post(url, {"action": "issue_order"})
    job.refresh_from_db()
    assert job.status == "reported"
    client.post(url, {"action": "request_approval"})
    job.refresh_from_db()
    assert job.approval_status == ""  # no supervisor yet
    StaffProfile.objects.create(user=setup["surveyor"], supervisor=head)
    client.post(url, {"action": "request_approval"})
    job.refresh_from_db()
    assert job.approval_status == "pending" and job.approver == head
    assert client.post(url, {"action": "approve"}).status_code == 403  # not your own
    client.force_login(head)
    assert "1 works order waiting for your approval" in client.get("/").content.decode()
    client.post(url, {"action": "approve"})
    client.force_login(setup["surveyor"])
    client.post(url, {"action": "issue_order"})
    job.refresh_from_db()
    assert job.status == "ordered" and job.approved_by == head
    client.post(url, {"action": "order_details", "contractor": setup["contractor"].pk, "estimate": "12000"})
    job.refresh_from_db()
    assert job.approval_status == ""  # a new estimate needs approving again


def test_planned_tasks_raise_jobs_and_roll_forward(client, setup):
    client.force_login(setup["surveyor"])
    client.post(f"/maintenance/property/{setup['building'].pk}/", {
        "task": ["gas_safety", "eicr"], "first_due": (date.today() + timedelta(days=10)).isoformat(),
        "contractor": setup["contractor"].pk})
    gas = PlannedTask.objects.get(title__startswith="Gas safety")
    assert gas.statutory and gas.frequency_months == 12 and PlannedTask.objects.count() == 2
    assert workflow.auto_raise() == 2 and workflow.auto_raise() == 0
    job = gas.jobs.get()
    assert job.priority == "planned" and job.target_date == gas.next_due and job.contractor == setup["contractor"]
    workflow.complete(job, date(2026, 11, 20))
    gas.refresh_from_db()
    assert gas.last_done == date(2026, 11, 20) and gas.next_due == date(2027, 11, 20)
    client.post(f"/maintenance/planned/{gas.pk}/", {"action": "done", "date": "2027-11-01"})
    gas.refresh_from_db()
    assert gas.next_due == date(2028, 11, 1)


def test_service_charge_and_lifecycle(client, setup):
    from apps.servicecharges.models import CostHeading, Schedule, ScheduleYear

    schedule = Schedule.objects.create(name="Block")
    schedule.properties.add(setup["building"])
    year = ScheduleYear.objects.create(schedule=schedule, start=date(2026, 4, 1), end=date(2027, 3, 31))
    job = workflow.open_job(setup["building"], "Roof repair", category="roof", contractor=setup["contractor"])
    workflow.complete(job, date(2026, 11, 3), Decimal("500"))
    assert list(workflow.service_charge_years(job)) == [year]
    workflow.add_to_service_charge(job, year, CostHeading.objects.first())
    assert year.expenditure.get().amount == Decimal("500.00")
    Component.objects.create(property=setup["building"], name="Roof", category="roof", installed_year=2000,
                             life_years=25, replacement_cost=Decimal("50000"))
    client.force_login(setup["surveyor"])
    page = client.get("/maintenance/forecast/").content.decode()
    assert "£50,000" in page
    assert client.get("/maintenance/forecast/?format=xlsx").status_code == 200


def test_contracts_retender_dates(setup):
    contract = Contract.objects.create(contractor=setup["contractor"], title="Fire alarms", starts=date(2024, 1, 1))
    assert contract.retender_due == date(2027, 1, 1)
    contract.last_tested = date(2025, 6, 1)
    contract.save()
    assert contract.retender_due == date(2028, 6, 1)


def test_pages_permissions_and_reports(client, make_user, setup):
    job = workflow.open_job(setup["unit"], "Leak", category="roof")
    viewer = make_user("view", "Viewers")
    client.force_login(viewer)
    for url in ("/maintenance/", "/maintenance/jobs/", "/maintenance/jobs/?format=xlsx", job.get_absolute_url(),
                "/maintenance/planned/", "/maintenance/components/", "/maintenance/contractors/",
                setup["contractor"].get_absolute_url(), "/maintenance/contracts/",
                f"/maintenance/property/{setup['unit'].pk}/", "/", setup["unit"].get_absolute_url()):
        assert client.get(url).status_code == 200, url
    assert client.post(job.get_absolute_url(), {"action": "close"}).status_code == 403
    assert client.get("/maintenance/jobs/new/").status_code == 403
    from apps.reports.models import Report

    for report in Report.objects.filter(starter__in=["jobs_past_target", "statutory_overdue", "planned_90",
                                                     "repair_spend_12m", "replacements_5y", "contracts_retender",
                                                     "contractor_insurance"]):
        assert client.get(report.get_absolute_url()).status_code == 200, report.starter
    settings = ModuleSettings.load()
    settings.maintenance_enabled = False
    settings.save()
    assert client.get("/maintenance/").status_code == 404


def test_demo(db):
    from django.core.management import call_command

    call_command("load_demo_data", verbosity=0)
    assert Job.objects.filter(approval_status="pending").exists()
    assert PlannedTask.objects.filter(statutory=True, next_due__lt=date.today()).exists()
    call_command("load_demo_data", "--reset", verbosity=0)
    assert Contractor.objects.count() == 6
