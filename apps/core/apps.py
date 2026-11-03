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
