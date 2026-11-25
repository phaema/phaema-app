# SPDX-License-Identifier: AGPL-3.0-or-later
"""Makes the database table for PHAEMA's shared cache (sign-in limits and other short-lived counts)."""
from django.core.management import call_command
from django.db import migrations


def make_cache_table(apps, schema_editor):
    call_command("createcachetable", database=schema_editor.connection.alias, verbosity=0)


class Migration(migrations.Migration):
    dependencies = [("core", "0021_text_copies")]

    operations = [migrations.RunPython(make_cache_table, migrations.RunPython.noop)]
