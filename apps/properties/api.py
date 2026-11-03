# SPDX-License-Identifier: AGPL-3.0-or-later
from rest_framework import serializers, viewsets

from .models import Property, Title


class PropertySerializer(serializers.ModelSerializer):
    boundary = serializers.SerializerMethodField(help_text="Boundary as GeoJSON (EPSG:27700).")

    class Meta:
        model = Property
        exclude = ["created_by", "updated_by"]
        read_only_fields = ["created_at", "updated_at"]

    def get_boundary(self, obj) -> dict | None:
        import json

        return json.loads(obj.boundary.geojson) if obj.boundary else None


class TitleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Title
        exclude = ["created_by", "updated_by"]
        read_only_fields = ["created_at", "updated_at"]


class PropertyViewSet(viewsets.ModelViewSet):
    """Property register. Read and write access for signed-in users."""

    queryset = Property.objects.all()
    serializer_class = PropertySerializer

    def get_queryset(self):
        qs = super().get_queryset()
        for param in ("property_type", "holding_purpose", "occupation", "uprn"):
            value = self.request.query_params.get(param)
            if value:
                qs = qs.filter(**{param: value})
        return qs


class TitleViewSet(viewsets.ModelViewSet):
    queryset = Title.objects.prefetch_related("properties")
    serializer_class = TitleSerializer
