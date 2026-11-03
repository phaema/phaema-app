# SPDX-License-Identifier: AGPL-3.0-or-later
from django.apps import AppConfig


class LeasesConfig(AppConfig):
    name = "apps.leases"
    label = "leases"
    verbose_name = "Leases and licences"

    def ready(self):
        from apps.core import audit

        from django.db.models.signals import m2m_changed, post_delete, post_save

        from . import workflow
        from .models import BreakOption, Lease, LeaseDocument, LeaseEvent, Party, RentScheduleEntry

        for model in (Party, Lease, BreakOption, LeaseDocument, LeaseEvent, RentScheduleEntry):
            audit.register(model)

        def lease_saved(sender, instance, update_fields=None, **kwargs):
            if update_fields and set(update_fields) <= {"annual_rent", "updated_at"}:
                return  # rent refreshed from the schedule: nothing else to do
            workflow.ensure_initial_entry(instance)
            workflow.sync_events(instance)

        def break_changed(sender, instance, **kwargs):
            origin = kwargs.get("origin")
            origin_model = getattr(origin, "model", type(origin)) if origin is not None else None
            if origin is not None and origin_model is not BreakOption:
                return  # deleted along with its lease
            try:
                lease = Lease.objects.get(pk=instance.lease_id)
            except Lease.DoesNotExist:
                return  # the whole lease is being deleted
            workflow.sync_events(lease)

        def premises_changed(sender, instance, action, reverse, **kwargs):
            if action == "post_add" and not reverse:
                workflow.sync_events(instance)  # assign events to the premises' surveyor

        def schedule_changed(sender, instance, **kwargs):
            origin = kwargs.get("origin")
            if origin is not None and getattr(origin, "model", type(origin)) is not RentScheduleEntry:
                return  # deleted along with its lease
            try:
                workflow.refresh_current_rent(Lease.objects.get(pk=instance.lease_id))
            except Lease.DoesNotExist:
                pass

        post_save.connect(lease_saved, sender=Lease, dispatch_uid="phaema_lease_sync", weak=False)
        post_save.connect(break_changed, sender=BreakOption, dispatch_uid="phaema_break_sync", weak=False)
        post_delete.connect(break_changed, sender=BreakOption, dispatch_uid="phaema_break_del_sync", weak=False)
        m2m_changed.connect(premises_changed, sender=Lease.properties.through, dispatch_uid="phaema_premises", weak=False)
        post_save.connect(schedule_changed, sender=RentScheduleEntry, dispatch_uid="phaema_rent_saved", weak=False)
        post_delete.connect(schedule_changed, sender=RentScheduleEntry, dispatch_uid="phaema_rent_del", weak=False)

        def remove_file(sender, instance, **kwargs):
            if instance.file:
                instance.file.storage.delete(instance.file.name)

        post_delete.connect(remove_file, sender=LeaseDocument, dispatch_uid="phaema_leasedoc_file", weak=False)
