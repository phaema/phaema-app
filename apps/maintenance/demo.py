# SPDX-License-Identifier: AGPL-3.0-or-later
"""Demonstration maintenance records on the fictional Exampleton estate."""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model

from apps.core.dates import add_months
from apps.core.models import ModuleSettings
from apps.properties.models import Property

from . import library, workflow
from .models import Component, Contract, Contractor, Job, PlannedTask, Responsibility

MARK = "DEMO"
D = Decimal


def _contractors(today):
    rows = [
        ("Exampleton Roofing Ltd", "Roofing, guttering", 200, "roofing"),
        ("Brightwire Electrical Services", "Electrical, fire alarms, emergency lighting", 20, "electrical"),
        ("Heatwell Mechanical Ltd", "Gas, heating, water hygiene, lifts", 300, "heating"),
        ("Riverside Building Maintenance", "General building repairs", -10, "building"),
    ]
    made = {}
    for name, trades, days, key in rows:
        made[key], _created = Contractor.objects.get_or_create(name=name, defaults={
            "trades": trades, "contact_name": "Service desk", "email": f"{key}@example.org",
            "phone": "01632 960000", "emergency_phone": "01632 960999", "insurer": "Example Mutual Insurance",
            "public_liability": D("5000000"), "insurance_expires": today + timedelta(days=days),
            "accreditations": "CHAS accredited (fictional)", "finance_supplier_ref": f"{MARK}-{key.upper()}",
            "notes": "Fictional demonstration contractor."})
    return made


def load(today=None):
    today = today or date.today()
    modules = ModuleSettings.load()
    if not modules.maintenance_enabled:
        modules.maintenance_enabled = True
        modules.save()
    if Contractor.objects.filter(finance_supplier_ref__startswith=MARK).exists():
        return Job.objects.count()
    props = {p.reference: p for p in Property.objects.filter(reference__startswith="DM-")}
    if "DM-S07" not in props:
        return 0
    c = _contractors(today)
    fire = Contract.objects.create(contractor=c["electrical"], title="Fire alarm and emergency lighting servicing",
                                   reference="EXC/FIRE/23", starts=add_months(today, -38),
                                   ends=add_months(today, 10), annual_value=D("14200"), service_charge=True)
    fire.properties.add(*[props[r] for r in ("DM-S07", "DM-S02", "DM-E01") if r in props])
    gas = Contract.objects.create(contractor=c["heating"], title="Gas, heating and lift maintenance",
                                  reference="EXC/MECH/25", starts=add_months(today, -13), ends=add_months(today, 47),
                                  annual_value=D("22800"))
    gas.properties.add(*[props[r] for r in ("DM-S07", "DM-S02") if r in props])
    water = Contract.objects.create(contractor=c["heating"], title="Water hygiene (legionella) monitoring",
                                    reference="EXC/WATER/24", starts=add_months(today, -32), annual_value=D("3900"),
                                    service_charge=True)
    water.properties.add(props["DM-S07"])

    # Components
    comp = {}
    for ref, name, cat, loc, uniclass, installed, life, cond, cost, capital in [
        ("DM-S07", "Main roof covering (felt)", "roof", "Whole building", "Ss_30_10_30", 2001, 25, "C", 85000, True),
        ("DM-S07", "Gas boilers (2)", "mechanical", "Plant room", "Ss_60_40_36", 2009, 20, "C", 38000, True),
        ("DM-S07", "Fire alarm panel and detection", "fire", "Reception", "Ss_75_50_28", 2016, 15, "B", 12000, True),
        ("DM-S07", "Passenger lift", "lift", "Core", "Ss_80_30_50", 1998, 25, "D", 95000, True),
        ("DM-S07", "Windows (aluminium)", "external", "All elevations", "Ss_25_30_95", 2005, 30, "B", 120000, True),
        ("DM-S07", "Common parts decorations", "internal", "Corridors and stairs", "", 2020, 7, "B", 8000, False),
        ("DM-E01-B01", "Roof and wall cladding", "roof", "Block A", "Ss_25_10_32", 1995, 35, "B", 160000, True),
        ("DM-S02", "Heating boilers", "mechanical", "Basement plant room", "Ss_60_40_36", 2012, 20, "B", 60000, True),
        ("DM-S02", "Electrical installation", "electrical", "Whole building", "Ss_70_30", 1990, 30, "C", 140000, True),
    ]:
        if ref in props:
            comp[name] = Component.objects.create(
                property=props[ref], name=name, category=cat, location=loc, uniclass=uniclass, installed_year=installed,
                life_years=life, condition=cond, condition_on=today - timedelta(days=200), replacement_cost=D(cost),
                capital=capital)

    # Planned maintenance from the library
    plan = [
        ("DM-S07", "fire_alarm", -10, "electrical", fire), ("DM-S07", "emergency_lighting", 20, "electrical", fire),
        ("DM-S07", "gas_safety", 60, "heating", gas), ("DM-S07", "legionella_ra", 150, "heating", water),
        ("DM-S07", "water_temps", 5, "heating", water), ("DM-S07", "lift_exam", 45, "heating", gas),
        ("DM-S07", "lift_service", 15, "heating", gas), ("DM-S07", "fra_review", 40, None, None),
        ("DM-S02", "eicr", 400, "electrical", None), ("DM-S02", "gas_safety", 25, "heating", gas),
        ("DM-S02", "asbestos", 90, None, None), ("DM-E01-B01", "roof_gutters", 70, "roofing", None),
        ("DM-E01-L01", "drains", 120, "building", None),
    ]
    for ref, code, due, contractor, contract in plan:
        if ref not in props:
            continue
        _c, title, category, months, statutory, regulation = library.BY_CODE[code]
        next_due = today + timedelta(days=due)
        PlannedTask.objects.create(
            property=props[ref], title=title, category=category, frequency_months=months, statutory=statutory,
            regulation=regulation, contractor=c.get(contractor), contract=contract, next_due=next_due,
            last_done=add_months(next_due, -months), estimated_cost=D("350") if months <= 12 else D("1200"))
    workflow.auto_raise(today)

    # Reactive jobs
    users = {u.username: u for u in get_user_model().objects.filter(username__startswith="demo.")}
    head = users.get("demo.head")

    def job(ref, title, **fields):
        return workflow.open_job(props[ref], title, **fields) if ref in props else None

    j = job("DM-S07", "Roof leak above the Suite 3 corridor", category="roof", priority="urgent",
            reported_on=today - timedelta(days=9), how_reported="tenant", reported_by="Suite 3 tenant",
            component=comp.get("Main roof covering (felt)"), contractor=c["roofing"], estimate=D("1850"),
            description="Water coming through the ceiling tiles after heavy rain. Buckets in place.")
    if j:
        workflow.issue_order(j, email_contractor=False, on=today - timedelta(days=7))
    j = job("DM-E01-U07", "Cracked external wall panel beside the loading door", category="external",
            priority="routine", reported_on=today - timedelta(days=40), how_reported="inspection",
            contractor=c["building"], estimate=D("640"))
    if j:
        workflow.issue_order(j, email_contractor=False, on=today - timedelta(days=38))
        workflow.complete(j, today - timedelta(days=20), D("640"), "Panel replaced and sealed.", "RBM-4471")
    j = job("DM-S01-U02", "Shop front glass broken by the tenant's delivery van", category="external",
            priority="urgent", reported_on=today - timedelta(days=30), how_reported="phone",
            reported_by="Shop manager", contractor=c["building"], estimate=D("420"),
            responsibility=Responsibility.RECHARGE,
            responsibility_reason="Damage caused by the tenant: recharge under the lease")
    if j:
        workflow.issue_order(j, email_contractor=False, on=today - timedelta(days=30))
        workflow.complete(j, today - timedelta(days=26), D("420"), "Toughened glass pane replaced.", "RBM-4402")
    j = job("DM-S02", "Replace the boiler flue and heating controls", category="mechanical", priority="routine",
            reported_on=today - timedelta(days=6), how_reported="inspection", contractor=c["heating"],
            estimate=D("7800"), component=comp.get("Heating boilers"),
            description="Flue corroded at the roof penetration; controls obsolete. Found at the annual service.")
    if j and head and j.owner:
        j.approval_status, j.approver = "pending", head
        j.save()
    j = job("DM-S07", "Lift stopped between floors with a passenger inside", category="lift", priority="emergency",
            reported_on=today - timedelta(days=55), how_reported="phone", contractor=c["heating"],
            estimate=D("280"), component=comp.get("Passenger lift"))
    if j:
        workflow.issue_order(j, email_contractor=False, on=today - timedelta(days=55))
        workflow.complete(j, today - timedelta(days=55), D("280"), "Passenger released within 40 minutes; door "
                          "lock reset.", "HWM-1180")
        j.status = Job.Status.CLOSED
        j.save()
    return Job.objects.count()


def remove():
    refs = Property.objects.filter(reference__startswith="DM-")
    Job.objects.filter(property__in=refs).delete()
    PlannedTask.objects.filter(property__in=refs).delete()
    Component.objects.filter(property__in=refs).delete()
    demo = Contractor.objects.filter(finance_supplier_ref__startswith=MARK)
    Contract.objects.filter(contractor__in=demo).delete()
    Job.objects.filter(contractor__in=demo).update(contractor=None)
    demo.delete()
