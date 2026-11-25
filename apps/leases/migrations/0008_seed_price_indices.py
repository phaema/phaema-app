# SPDX-License-Identifier: AGPL-3.0-or-later
"""The three price indices used in most index-linked leases, with their ONS series so figures can be fetched."""
from django.db import migrations

SERIES = [
    ("CPI", "Consumer Prices Index (CPI), all items, 2015=100", "D7BT"),
    ("CPIH", "CPI including owner occupiers' housing costs (CPIH), all items, 2015=100", "L522"),
    ("RPI", "Retail Prices Index (RPI), all items, January 1987=100", "CHAW"),
]


def seed(apps, schema_editor):
    IndexSeries = apps.get_model("leases", "IndexSeries")
    for code, name, ons in SERIES:
        IndexSeries.objects.get_or_create(code=code, defaults={"name": name, "ons_series": ons, "ons_dataset": "mm23"})


class Migration(migrations.Migration):
    dependencies = [("leases", "0007_index_linked_reviews")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
