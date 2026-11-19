# SPDX-License-Identifier: AGPL-3.0-or-later
"""Recognise the text in scanned PDFs waiting to be read. Run every few minutes by the scheduler.

    python manage.py ocr_scans               read up to 20 waiting documents
    python manage.py ocr_scans --backlog     first queue every PDF already held (for existing documents)
"""
from django.core.management.base import BaseCommand

from apps.core import ocr


class Command(BaseCommand):
    help = "Recognise the text in scanned PDFs (OCR) so that Find works on them."

    def add_arguments(self, parser):
        parser.add_argument("--backlog", action="store_true", help="Queue every PDF already held first.")
        parser.add_argument("--limit", type=int, default=20, help="Most documents to read this time (default 20).")

    def handle(self, *args, backlog=False, limit=20, **options):
        if not ocr.enabled():
            self.stdout.write("Recognising text in scanned PDFs is switched off in Module settings.")
            return
        if backlog:
            self.stdout.write(f"Queued {ocr.backlog()} documents already held.")
        result = ocr.process(limit=limit)
        if "missing" in result:
            self.stdout.write(f"Not reading scanned PDFs: {result['missing']}")
            return
        removed = ocr.tidy()
        summary = ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in sorted(result.items())) or "nothing waiting"
        self.stdout.write(f"Scanned PDFs: {summary}. Copies tidied away: {removed}.")
