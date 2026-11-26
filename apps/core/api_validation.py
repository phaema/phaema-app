# SPDX-License-Identifier: AGPL-3.0-or-later
"""Run a model's own checks (clean()) for records saved through the API, as the forms and admin site do.

Django REST framework's ModelSerializer checks field types and uniqueness but not Model.clean(), so rules such as
"a property cannot be part of itself" or "the expiry date must be after the term start" would otherwise be skipped
for anything sent to /api/. Use ModelCleanSerializer in place of ModelSerializer.
"""
import copy

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers


class ModelCleanSerializer(serializers.ModelSerializer):
    def validate(self, attrs):
        attrs = super().validate(attrs)
        model = self.Meta.model
        many = {f.name for f in model._meta.many_to_many}
        candidate = copy.copy(self.instance) if self.instance is not None else model()
        for name, value in attrs.items():
            if name not in many:
                setattr(candidate, name, value)
        try:
            candidate.clean()
        except DjangoValidationError as exc:
            if hasattr(exc, "error_dict"):
                raise serializers.ValidationError(
                    {field or "non_field_errors": [str(m) for m in messages]
                     for field, messages in exc.message_dict.items()}) from None
            raise serializers.ValidationError({"non_field_errors": list(exc.messages)}) from None
        return attrs
