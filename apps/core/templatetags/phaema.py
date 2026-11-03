# SPDX-License-Identifier: AGPL-3.0-or-later
from django import template
from django.core.exceptions import FieldDoesNotExist

register = template.Library()


@register.filter
def field_labels(entry):
    """Readable names of the fields an audit entry changed, e.g. "NIA (m²), managing surveyor"."""
    model = entry.content_type.model_class()
    labels = []
    for name in entry.changes or {}:
        try:
            labels.append(str(model._meta.get_field(name).verbose_name))
        except (FieldDoesNotExist, AttributeError):
            labels.append(name)
    return ", ".join(labels)


@register.filter
def get_item(sequence, index):
    """{{ list|get_item:i }}"""
    try:
        return sequence[index]
    except (IndexError, KeyError, TypeError):
        return None


@register.filter
def attr_type(field):
    return getattr(field, "type", "")


@register.filter
def file_size(fieldfile):
    """Size of a stored file, e.g. "1.2 MB", or "file missing" if it is no longer in storage."""
    from django.template.defaultfilters import filesizeformat

    try:
        return filesizeformat(fieldfile.size)
    except (OSError, ValueError):
        return "file missing"


@register.filter
def person(user, empty=""):
    """A user's full name, or their username, or `empty` if there is no user."""
    if not user:
        return empty
    return user.get_full_name() or user.get_username()


@register.filter
def percent(fraction, places=2):
    """0.12 → "12.00%"."""
    from decimal import Decimal, InvalidOperation

    try:
        return f"{Decimal(fraction) * 100:.{int(places)}f}%"
    except (InvalidOperation, TypeError, ValueError):
        return ""


@register.filter
def subtract(a, b):
    try:
        return a - b
    except TypeError:
        return None
