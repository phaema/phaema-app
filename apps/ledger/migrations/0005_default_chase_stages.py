# SPDX-License-Identifier: AGPL-3.0-or-later
"""A starting credit control sequence, which administrators can change under Manage data."""
from django.db import migrations

STAGES = [
    (1, "Reminder letter", 7, "letter", "arrears-reminder"),
    (2, "Final notice", 21, "letter", "arrears-final"),
    (3, "Rent arrears recovery case", 35, "case", ""),
    (4, "Review: payment plan, debt collectors or legal", 60, "review", ""),
]


def seed(apps, schema_editor):
    ChaseStage = apps.get_model("ledger", "ChaseStage")
    if ChaseStage.objects.exists():
        return
    for order, name, days, action, code in STAGES:
        ChaseStage.objects.create(order=order, name=name, days_overdue=days, action=action, template_code=code)


class Migration(migrations.Migration):
    dependencies = [("ledger", "0004_interest_and_credit_control")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
