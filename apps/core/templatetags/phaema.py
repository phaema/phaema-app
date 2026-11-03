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
