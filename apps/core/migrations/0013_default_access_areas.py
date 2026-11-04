# SPDX-License-Identifier: AGPL-3.0-or-later
"""Create the five standard access areas and put every existing user in all of them, so nobody loses anything
when access areas arrive. Administrators then narrow access."""
from django.conf import settings
from django.db import migrations

AREAS = [
    ("estates", "Estates", "Surveyors and estates managers: rent, arrears and service charges for their own patch.",
     [], True, False),
    ("finance", "Finance", "Finance officers: the rent ledger, service charges and asset valuation, and maintenance to "
     "read.", ["ledger", "servicecharges", "valuations", "maintenance"], False, True),
    ("maintenance", "Maintenance and compliance", "Building and facilities staff.", ["maintenance", "compliance"],
     False, False),
    ("valuation", "Valuation", "Internal valuers.", ["valuations"], False, False),
    ("legal", "Legal", "The legal team: core PHAEMA and the cases they are added to.", [], False, False),
]


def create(apps, schema_editor):
    AccessArea = apps.get_model("core", "AccessArea")
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    users = list(User.objects.all())
    for order, (code, name, description, modules, patch, finance) in enumerate(AREAS):
        area, created = AccessArea.objects.get_or_create(code=code, defaults={
            "name": name, "description": description, "modules": modules, "own_patch_finance": patch,
            "finance_actions": finance, "order": order})
        if created:
            area.members.add(*users)


def remove(apps, schema_editor):
    apps.get_model("core", "AccessArea").objects.filter(code__in=[a[0] for a in AREAS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0012_access_areas_and_cover"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [migrations.RunPython(create, remove)]
