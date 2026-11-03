# SPDX-License-Identifier: AGPL-3.0-or-later
"""Audit trail: call register(Model) to record every create, change and delete."""
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_delete, post_save, pre_save

from .middleware import get_current_user

_EXCLUDED = {"created_at", "updated_at", "created_by", "updated_by"}


def _snapshot(instance):
    data = {}
    for field in instance._meta.concrete_fields:
        if field.name in _EXCLUDED:
            continue
        value = field.value_from_object(instance)
        if value is not None and field.get_internal_type() == "DecimalField":
            # Store 480 and 480.00 the same way so unchanged values are not logged as changes.
            value = f"{Decimal(str(value)):.{field.decimal_places}f}"
        data[field.name] = None if value is None else str(value)
    return data


def _record(instance, action, changes):
    from .models import AuditEntry

    AuditEntry.objects.create(
        user=get_current_user(),
        content_type=ContentType.objects.get_for_model(instance.__class__),
        object_id=str(instance.pk),
        object_repr=str(instance)[:255],
        action=action,
        changes=changes,
    )


def _pre_save(sender, instance, **kwargs):
    user = get_current_user()
    if hasattr(instance, "updated_by_id") and user:
        instance.updated_by = user
        if instance._state.adding and not instance.created_by_id:
            instance.created_by = user
    if instance.pk and not instance._state.adding:
        try:
            old = sender.objects.get(pk=instance.pk)
        except sender.DoesNotExist:
            old = None
        instance._audit_before = _snapshot(old) if old else None


def _post_save(sender, instance, created, update_fields=None, **kwargs):
    after = _snapshot(instance)
    if created:
        _record(instance, "create", {k: [None, v] for k, v in after.items() if v is not None})
        return
    before = getattr(instance, "_audit_before", None) or {}
    if update_fields:
        after = {k: v for k, v in after.items() if k in update_fields or k.removesuffix("_id") in update_fields}
    diff = {k: [before.get(k), v] for k, v in after.items() if before.get(k) != v}
    if diff:
        _record(instance, "update", diff)


def _post_delete(sender, instance, **kwargs):
    _record(instance, "delete", {})


def register(model):
    uid = f"phaema_audit_{model._meta.label}"
    pre_save.connect(_pre_save, sender=model, dispatch_uid=uid + "_pre")
    post_save.connect(_post_save, sender=model, dispatch_uid=uid + "_post")
    post_delete.connect(_post_delete, sender=model, dispatch_uid=uid + "_del")
    return model
