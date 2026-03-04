from __future__ import annotations

from rest_framework.generics import ListCreateAPIView, RetrieveUpdateAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.exceptions import ValidationError
from django_filters.rest_framework import DjangoFilterBackend

from purchase.models.purchase_addons import PurchaseChargeType
from purchase.serializers.purchase_charge import PurchaseChargeTypeSerializer
from purchase.filters.purchase_charge_type_filter import PurchaseChargeTypeFilter


class PurchaseChargeTypeListCreateAPIView(ListCreateAPIView):
    """
    GET  /api/purchase/charge-types/?entity=<id>&is_active=true
    POST /api/purchase/charge-types/
    """
    permission_classes = [IsAuthenticated]
    serializer_class = PurchaseChargeTypeSerializer

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = PurchaseChargeTypeFilter
    search_fields = ["code", "name", "description", "hsn_sac_code_default"]
    ordering_fields = ["code", "name", "base_category", "is_active", "updated_at"]
    ordering = ["code"]

    def _entity_id(self):
        entity_raw = self.request.query_params.get("entity")
        if not entity_raw:
            raise ValidationError({"detail": "entity query param is required."})
        try:
            return int(entity_raw)
        except (TypeError, ValueError):
            raise ValidationError({"detail": "entity must be an integer."})

    def get_queryset(self):
        qs = PurchaseChargeType.objects.all()

        entity_id = self._entity_id()
        # entity-specific + global (entity is NULL)
        qs = qs.filter(entity_id=entity_id) | qs.filter(entity__isnull=True)
        qs = qs.distinct()

        return qs


class PurchaseChargeTypeRetrieveUpdateAPIView(RetrieveUpdateAPIView):
    """
    GET   /api/purchase/charge-types/<id>/
    PUT   /api/purchase/charge-types/<id>/
    PATCH /api/purchase/charge-types/<id>/
    """
    permission_classes = [IsAuthenticated]
    serializer_class = PurchaseChargeTypeSerializer

    def get_queryset(self):
        entity_raw = self.request.query_params.get("entity")
        if not entity_raw:
            raise ValidationError({"detail": "entity query param is required."})
        try:
            entity_id = int(entity_raw)
        except (TypeError, ValueError):
            raise ValidationError({"detail": "entity must be an integer."})
        return (PurchaseChargeType.objects.filter(entity_id=entity_id) | PurchaseChargeType.objects.filter(entity__isnull=True)).distinct()
