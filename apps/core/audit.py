# SPDX-License-Identifier: AGPL-3.0-or-later
"""Audit trail: call register(Model) to record every create, change and delete.

The change log is written from Django's model signals, which QuerySet.update(), bulk_update() and bulk_create() do
not send. For a registered model, use audited_update() and audited_create() below instead, so those changes are
logged too. The database trigger (core.0023) then stops entries being changed or deleted through the application's
database account; someone with administrator rights over the database server itself could still alter it.
"""
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_delete, post_save, pre_save

from .middleware import get_current_user, get_current_via

_EXCLUDED = {"created_at", "updated_at", "created_by", "updated_by", "key_hash"}


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
        via=get_current_via(),
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


_REGISTERED = set()


def is_registered(model):
    return model in _REGISTERED


def audited_update(queryset, **changes):
    """QuerySet.update() that also writes a change log entry for each record whose values change."""
    from django.db import transaction

    model = queryset.model
    if model not in _REGISTERED:
        return queryset.update(**changes)
    with transaction.atomic():
        before = {item.pk: _snapshot(item) for item in queryset}
        if not before:
            return 0
        count = model._default_manager.filter(pk__in=before).update(**changes)
        names = {model._meta.get_field(name).name for name in changes}
        for item in model._default_manager.filter(pk__in=before):
            after = _snapshot(item)
            diff = {k: [before[item.pk].get(k), v] for k, v in after.items()
                    if k in names and before[item.pk].get(k) != v}
            if diff:
                _record(item, "update", diff)
    return count


def audited_create(model, items, **kwargs):
    """bulk_create() that also writes a change log entry for each new record."""
    created = model._default_manager.bulk_create(items, **kwargs)
    if model in _REGISTERED:
        for item in created:
            if item.pk is not None:
                _record(item, "create", {k: [None, v] for k, v in _snapshot(item).items() if v is not None})
    return created


def register(model):
    _REGISTERED.add(model)
    uid = f"phaema_audit_{model._meta.label}"
    pre_save.connect(_pre_save, sender=model, dispatch_uid=uid + "_pre")
    post_save.connect(_post_save, sender=model, dispatch_uid=uid + "_post")
    post_delete.connect(_post_delete, sender=model, dispatch_uid=uid + "_del")
    return model
