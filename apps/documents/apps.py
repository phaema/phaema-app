# SPDX-License-Identifier: AGPL-3.0-or-later
from django.apps import AppConfig
from django.db import connection
from django.db.models.signals import post_migrate


class DocumentsConfig(AppConfig):
    name = "apps.documents"
    label = "documents"
    verbose_name = "Document library"

    def ready(self):
        from apps.core import audit

        from .models import DocumentTemplate

        audit.register(DocumentTemplate)

        def seed(sender, **kwargs):
            if sender.label == "documents" and "documents_documenttemplate" in connection.introspection.table_names():
                from .seed import ensure_templates

                ensure_templates()

        post_migrate.connect(seed, dispatch_uid="phaema_document_templates", weak=False)
