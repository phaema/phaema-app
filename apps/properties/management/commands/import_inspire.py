# SPDX-License-Identifier: AGPL-3.0-or-later
from django.core.management.base import BaseCommand, CommandError

from apps.properties.inspire import InspireImportError, import_inspire


class Command(BaseCommand):
    help = "Import HM Land Registry INSPIRE Index Polygons from a .zip or .gml file."

    def add_arguments(self, parser):
        parser.add_argument("path", help="Path to the INSPIRE zip or GML file")

    def handle(self, *args, **options):
        try:
            created, updated, skipped = import_inspire(options["path"], source_name=options["path"].rsplit("/", 1)[-1])
        except InspireImportError as exc:
            raise CommandError(str(exc))
        self.stdout.write(self.style.SUCCESS(
            f"INSPIRE import finished: {created} parcels added, {updated} updated, {skipped} skipped."
        ))
