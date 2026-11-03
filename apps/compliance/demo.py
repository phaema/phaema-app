# SPDX-License-Identifier: AGPL-3.0-or-later
"""Demonstration compliance records and building information on the fictional Exampleton estate."""
from datetime import date, timedelta

from django.core.files.base import ContentFile

from apps.core.dates import add_months
from apps.properties.demo_media import placeholder_pdf as _placeholder
from apps.properties.models import Property

from . import workflow
from .models import Action, BuildingDocument, BuildingSafety, Certificate, ComplianceType, Requirement


def placeholder_pdf(title):
    return _placeholder(title, ["A fictional document for demonstrating PHAEMA."],
                        banner="FICTIONAL DEMONSTRATION DOCUMENT")


def load(today=None):
    today = today or date.today()
    props = {p.reference: p for p in Property.objects.filter(reference__startswith="DM-")}
    if "DM-S07" not in props or Requirement.objects.filter(property__in=props.values()).exists():
        return Requirement.objects.count()
    kinds = {k.code: k for k in ComplianceType.objects.all()}
    plan = {
        "DM-S07": ["fra", "fire_alarm", "emergency_lighting", "gas", "eicr", "legionella", "asbestos", "lift", "epc"],
        "DM-S02": ["fra", "fire_alarm", "emergency_lighting", "gas", "eicr", "asbestos", "dec"],
        "DM-S01-B01": ["fra", "eicr", "asbestos"],
        "DM-S05": ["fra", "gas", "eicr", "epc"],
        "DM-E01-U03": ["epc"], "DM-E01-U08": ["epc"], "DM-S01-U03": ["epc"],
    }
    reqs = {}
    for ref, codes in plan.items():
        if ref in props:
            for req in workflow.add_requirements(props[ref], [kinds[c] for c in codes]):
                reqs[(ref, req.kind.code)] = req

    def cert(ref, code, months_ago, result="ok", rating="", actions=(), by="Fictional inspector"):
        req = reqs.get((ref, code))
        if req is None:
            return None
        issued = add_months(today, -months_ago)
        c = Certificate(requirement=req, issued_on=issued, result=result, rating=rating, carried_out_by=by,
                        reference=f"DEMO-{code.upper()}-{req.pk}")
        c.file.save(f"{code}.pdf", ContentFile(placeholder_pdf(f"{req.kind.name}, {req.property.name}")), save=False)
        c.original_filename = f"{code}.pdf"
        c.save()
        for text, priority in actions:
            Action.objects.create(certificate=c, description=text, priority=priority)
        return c

    cert("DM-S07", "fra", 1, "actions", actions=[
        ("Fit a self-closing device to the first floor store room door", "high"),
        ("Replace the damaged fire door seal to the stair core", "medium"),
        ("Update the evacuation plan in reception", "low")])
    cert("DM-S07", "fire_alarm", 7)          # expired: the six-monthly service is overdue
    cert("DM-S07", "emergency_lighting", 11)  # expires within 60 days
    cert("DM-S07", "gas", 10)
    eicr = cert("DM-S07", "eicr", 26, "actions",
                actions=[("Replace the cracked socket in the kitchenette (C2)", "medium")])
    if eicr:
        eicr.actions.update(done_on=eicr.issued_on + timedelta(days=12))
    cert("DM-S07", "legionella", 5)
    cert("DM-S07", "lift", 4)
    cert("DM-S07", "epc", 40, rating="D")
    # DM-S07 asbestos: missing
    cert("DM-S02", "fra", 3)
    cert("DM-S02", "fire_alarm", 2)
    cert("DM-S02", "emergency_lighting", 6)
    cert("DM-S02", "gas", 13)                # expired
    cert("DM-S02", "eicr", 70, "fail")       # long out of date
    cert("DM-S02", "asbestos", 8)
    cert("DM-S02", "dec", 9, rating="E")
    cert("DM-S01-B01", "fra", 6)
    cert("DM-S01-B01", "eicr", 30)
    cert("DM-S01-B01", "asbestos", 2)
    cert("DM-S05", "fra", 9, by="Brookside Community Association")
    cert("DM-S05", "gas", 4, by="Brookside Community Association")
    cert("DM-S05", "epc", 60, rating="C")
    cert("DM-E01-U03", "epc", 90, rating="F")  # below the minimum standard for letting
    cert("DM-E01-U08", "epc", 20, rating="C")

    # Higher-risk screening
    for ref, height, storeys, homes, tier, rp in [
        ("DM-S07", "12.5", 4, 0, "B", "Exampleton Council, Estates (common parts); tenants for their suites"),
        ("DM-S02", "16.0", 4, 0, "B", "Exampleton Council, Facilities"),
        ("DM-S01-B01", "9.0", 3, 6, "B", "Exampleton Council, Estates"),
        ("DM-S06", None, None, 0, "C", ""),
    ]:
        if ref in props:
            BuildingSafety.objects.create(property=props[ref], height_m=height, storeys=storeys,
                                          residential_units=homes, tier=tier, confirmed_on=today - timedelta(days=30),
                                          confirmed_by=props[ref].managing_surveyor, responsible_person=rp)

    # Building information
    docs = [
        ("DM-S07", "plans", "Floor plans, ground to third floor", 2005),
        ("DM-S07", "fire", "Fire strategy and regulation 38 information", 2005),
        ("DM-S07", "hs_file", "Health and safety file: 2019 roof repairs", 2019),
        ("DM-S07", "asbestos", "Asbestos management survey", 2018),
        ("DM-S02", "plans", "Measured survey drawings", 2016),
        ("DM-S02", "om", "Boiler plant operation and maintenance manual", 2012),
    ]
    for ref, category, title, year in docs:
        if ref in props:
            d = BuildingDocument(property=props[ref], category=category, title=title,
                                 document_date=date(year, 6, 1), original_filename=f"{category}.pdf")
            d.file.save(f"{category}.pdf", ContentFile(placeholder_pdf(title)), save=False)
            d.save()
    if "DM-S07" in props:
        old = BuildingDocument.objects.get(property=props["DM-S07"], category="plans")
        new = BuildingDocument(property=props["DM-S07"], category="plans", title=old.title, supersedes=old,
                               document_date=date(2021, 3, 1), notes="Updated after the suite 3 partitions.",
                               original_filename="plans-2021.pdf")
        new.file.save("plans-2021.pdf", ContentFile(placeholder_pdf(old.title + " (2021)")), save=False)
        new.save()
    return Requirement.objects.count()


def remove():
    refs = Property.objects.filter(reference__startswith="DM-")
    docs = BuildingDocument.objects.filter(property__in=refs)
    while docs.exists():  # newest versions first: an older version cannot go while a newer one points at it
        docs.filter(superseded_by__isnull=True).delete()
    BuildingSafety.objects.filter(property__in=refs).delete()
    Requirement.objects.filter(property__in=refs).delete()
