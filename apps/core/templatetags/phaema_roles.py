# SPDX-License-Identifier: AGPL-3.0-or-later
from django import template

from apps.core.roles import can_edit as _can_edit

register = template.Library()


@register.filter
def can_edit(user, obj):
    """{% if user|can_edit:object %} ... {% endif %}"""
    return _can_edit(user, obj)
