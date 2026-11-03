# SPDX-License-Identifier: AGPL-3.0-or-later
from django.apps import AppConfig


class LeasesConfig(AppConfig):
    name = "apps.leases"
    label = "leases"
    verbose_name = "Leases and licences"

    def ready(self):
        from apps.core import audit

        from django.db.models.signals import post_delete

        from .models import BreakOption, Lease, LeaseDocument, Party

        for model in (Party, Lease, BreakOption, LeaseDocument):
            audit.register(model)

        def remove_file(sender, instance, **kwargs):
            if instance.file:
                instance.file.storage.delete(instance.file.name)

        post_delete.connect(remove_file, sender=LeaseDocument, dispatch_uid="phaema_leasedoc_file", weak=False)
