from __future__ import annotations

from django.db.models import Q
from rest_framework.exceptions import ValidationError
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateAPIView
from rest_framework.permissions import IsAuthenticated

from sales.models.sales_addons import SalesChargeType
from sales.serializers.sales_charge_serializers import SalesChargeTypeSerializer


class SalesChargeTypeListCreateAPIView(ListCreateAPIView):
    """
    GET  /api/sales/charge-types/?entity=<id>&is_active=true
    POST /api/sales/charge-types/
    """

    permission_classes = [IsAuthenticated]
    serializer_class = SalesChargeTypeSerializer
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["code", "name", "description", "hsn_sac_code_default"]
    ordering_fields = ["code", "name", "base_category", "is_active", "updated_at"]
    ordering = ["code"]

    def _entity_id(self) -> int:
        entity_raw = self.request.query_params.get("entity")
        if not entity_raw:
            raise ValidationError({"detail": "entity query param is required."})
        try:
            return int(entity_raw)
        except (TypeError, ValueError):
            raise ValidationError({"detail": "entity must be an integer."})

    def get_queryset(self):
        entity_id = self._entity_id()
        qs = SalesChargeType.objects.filter(Q(entity_id=entity_id) | Q(entity__isnull=True)).distinct()

        is_active_raw = self.request.query_params.get("is_active")
        if is_active_raw is not None:
            is_active = str(is_active_raw).strip().lower() in {"true", "1", "yes", "y"}
            qs = qs.filter(is_active=is_active)
        return qs


class SalesChargeTypeRetrieveUpdateAPIView(RetrieveUpdateAPIView):
    """
    GET   /api/sales/charge-types/<id>/?entity=<id>
    PUT   /api/sales/charge-types/<id>/?entity=<id>
    PATCH /api/sales/charge-types/<id>/?entity=<id>
    """

    permission_classes = [IsAuthenticated]
    serializer_class = SalesChargeTypeSerializer

    def get_queryset(self):
        entity_raw = self.request.query_params.get("entity")
        if not entity_raw:
            raise ValidationError({"detail": "entity query param is required."})
        try:
            entity_id = int(entity_raw)
        except (TypeError, ValueError):
            raise ValidationError({"detail": "entity must be an integer."})
        return SalesChargeType.objects.filter(Q(entity_id=entity_id) | Q(entity__isnull=True)).distinct()
