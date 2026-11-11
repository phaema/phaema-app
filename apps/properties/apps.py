# SPDX-License-Identifier: AGPL-3.0-or-later
from django.apps import AppConfig


class PropertiesConfig(AppConfig):
    name = "apps.properties"
    label = "properties"
    verbose_name = "Property register"

    def ready(self):
        from apps.core import audit

        from django.db.models.signals import post_delete

        from .models import Property, PropertyPhoto, PropertyPlan, Title, TitleDocument

        for model in (Property, Title, PropertyPhoto, TitleDocument, PropertyPlan):
            audit.register(model)

        def remove_file(sender, instance, **kwargs):
            field = instance.image if sender is PropertyPhoto else instance.file
            if field:
                field.storage.delete(field.name)

        post_delete.connect(remove_file, sender=PropertyPhoto, dispatch_uid="phaema_photo_file", weak=False)
        post_delete.connect(remove_file, sender=TitleDocument, dispatch_uid="phaema_titledoc_file", weak=False)
        post_delete.connect(remove_file, sender=PropertyPlan, dispatch_uid="phaema_plan_file", weak=False)
