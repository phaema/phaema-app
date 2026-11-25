# SPDX-License-Identifier: AGPL-3.0-or-later
"""Credit notes raised before this release did not carry the period and service charge year of the charge they
credit, so year-end service charge reconciliations left them out. Copy them across from the original charge."""
from django.db import migrations


def copy_from_original(apps, schema_editor):
    Charge = apps.get_model("ledger", "Charge")
    for note in Charge.objects.filter(credit_for__isnull=False).select_related("credit_for"):
        original = note.credit_for
        note.service_year_id = original.service_year_id
        note.period_start, note.period_end = original.period_start, original.period_end
        note.save(update_fields=["service_year", "period_start", "period_end"])


class Migration(migrations.Migration):
    dependencies = [("ledger", "0002_charge_service_year_alter_charge_kind_and_more")]

    operations = [migrations.RunPython(copy_from_original, migrations.RunPython.noop)]
