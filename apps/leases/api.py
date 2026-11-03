# SPDX-License-Identifier: AGPL-3.0-or-later
from rest_framework import serializers, viewsets
from rest_framework.exceptions import PermissionDenied

from apps.core.roles import is_administrator

from .models import BreakOption, Lease, Party


class PartySerializer(serializers.ModelSerializer):
    class Meta:
        model = Party
        exclude = ["created_by", "updated_by"]
        read_only_fields = ["created_at", "updated_at"]


class BreakOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = BreakOption
        fields = ["id", "break_date", "exercisable_by", "notice_months", "notice_deadline", "conditions"]


class LeaseSerializer(serializers.ModelSerializer):
    breaks = BreakOptionSerializer(many=True, read_only=True)

    class Meta:
        model = Lease
        exclude = ["created_by", "updated_by"]
        read_only_fields = ["created_at", "updated_at"]


class PartyViewSet(viewsets.ModelViewSet):
    queryset = Party.objects.all()
    serializer_class = PartySerializer


class LeaseViewSet(viewsets.ModelViewSet):
    queryset = Lease.objects.select_related("counterparty").prefetch_related("properties", "breaks")
    serializer_class = LeaseSerializer

    def perform_update(self, serializer):
        new = serializer.validated_data.get("properties")
        if new is not None and not is_administrator(self.request.user):
            existing = set(serializer.instance.properties.values_list("pk", flat=True))
            if any(p.managing_surveyor_id != self.request.user.pk and p.pk not in existing for p in new):
                raise PermissionDenied("You can only add properties you manage to a lease.")
        serializer.save()
