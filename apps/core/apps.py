# SPDX-License-Identifier: AGPL-3.0-or-later
from django.apps import AppConfig
from django.db.models.signals import m2m_changed, post_migrate


class CoreConfig(AppConfig):
    name = "apps.core"
    label = "core"
    verbose_name = "PHAEMA core"

    def ready(self):
        from django.contrib.auth import get_user_model

        from .roles import ensure_roles, sync_staff_status

        def create_roles(sender, **kwargs):
            if sender.label == "leases":  # the last PHAEMA app to migrate, so all permissions exist
                ensure_roles()

        post_migrate.connect(create_roles, dispatch_uid="phaema_create_roles", weak=False)

        User = get_user_model()

        def groups_changed(sender, instance, action, reverse, pk_set, **kwargs):
            if action not in ("post_add", "post_remove", "post_clear"):
                return
            if not reverse:  # user.groups changed
                sync_staff_status(instance)
            else:  # group.user_set changed
                users = User.objects.filter(pk__in=pk_set) if pk_set else instance.user_set.all()
                for user in users:
                    sync_staff_status(user)

        m2m_changed.connect(groups_changed, sender=User.groups.through, dispatch_uid="phaema_sync_staff", weak=False)

        # Access areas and cover go in the change log, so it is clear who could see what, and when.
        from . import audit
        from .models import AccessArea, Cover

        audit.register(Cover)
        audit.register(AccessArea)

        def members_changed(sender, instance, action, reverse, pk_set, **kwargs):
            if action not in ("post_add", "post_remove") or not pk_set:
                return
            verb = "added" if action == "post_add" else "removed"
            if reverse:  # user.access_areas changed: instance is the user
                names = ", ".join(AccessArea.objects.filter(pk__in=pk_set).values_list("name", flat=True))
                audit._record(instance, "update", {"access areas": [None, f"{verb}: {names}"]})
            else:  # area.members changed
                for user in User.objects.filter(pk__in=pk_set):
                    audit._record(user, "update", {"access areas": [None, f"{verb}: {instance.name}"]})

        m2m_changed.connect(members_changed, sender=AccessArea.members.through, dispatch_uid="phaema_area_members",
                            weak=False)
