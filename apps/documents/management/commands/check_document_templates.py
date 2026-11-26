# SPDX-License-Identifier: AGPL-3.0-or-later
"""List document templates that use anything outside the letter template language, so they can be corrected.

    python manage.py check_document_templates

Exits with status 1 if any template needs correcting. Such a template still opens, but its letters show a message
asking an administrator to correct it instead of the letter text.
"""
from django.core.management.base import BaseCommand, CommandError
from django.template import TemplateSyntaxError

from apps.documents import render
from apps.documents.models import DocumentTemplate


class Command(BaseCommand):
    help = "List document templates that need correcting for the letter template language."

    def handle(self, *args, **options):
        bad = 0
        for template in DocumentTemplate.objects.order_by("name"):
            try:
                render.check(template.body)
            except TemplateSyntaxError as exc:
                bad += 1
                self.stdout.write(f"{template.name} ({template.code}): {exc}")
        if bad:
            raise CommandError(f"{bad} template(s) to correct in Manage data, Document templates.")
        self.stdout.write("Every document template is fine.")
