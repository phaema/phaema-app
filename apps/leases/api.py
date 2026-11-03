# SPDX-License-Identifier: AGPL-3.0-or-later
from rest_framework import serializers, viewsets

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
