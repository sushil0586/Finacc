from rest_framework import generics, permissions, filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from purchase.models.purchase_core import PurchaseInvoiceLine, PurchaseTaxSummary


class PurchaseInvoiceLineROSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchaseInvoiceLine
        fields = "__all__"


class PurchaseTaxSummaryROSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchaseTaxSummary
        fields = "__all__"


class PurchaseInvoiceLinesListAPIView(generics.ListAPIView):
    serializer_class = PurchaseInvoiceLineROSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["header", "taxability", "is_service", "gst_rate", "is_itc_eligible"]
    ordering_fields = ["header", "line_no", "id"]
    ordering = ["header", "line_no"]

    def _scope_ids(self):
        entity = self.request.query_params.get("entity")
        entityfinid = self.request.query_params.get("entityfinid")
        subentity = self.request.query_params.get("subentity")
        if not entity or not entityfinid:
            raise ValidationError({"detail": "entity and entityfinid query params are required."})
        try:
            entity_id = int(entity)
            entityfinid_id = int(entityfinid)
            subentity_id = int(subentity) if subentity not in (None, "", "null") else None
        except (TypeError, ValueError):
            raise ValidationError({"detail": "entity/entityfinid/subentity must be integers."})
        return entity_id, entityfinid_id, subentity_id

    def get_queryset(self):
        entity_id, entityfinid_id, subentity_id = self._scope_ids()
        qs = PurchaseInvoiceLine.objects.select_related("header", "product", "uom").filter(
            header__entity_id=entity_id,
            header__entityfinid_id=entityfinid_id,
        )
        if subentity_id is None:
            return qs
        return qs.filter(header__subentity_id=subentity_id)


class PurchaseTaxSummaryListAPIView(generics.ListAPIView):
    serializer_class = PurchaseTaxSummaryROSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["header", "taxability", "is_service", "gst_rate", "is_reverse_charge"]
    ordering_fields = ["header", "gst_rate", "taxability"]
    ordering = ["header", "gst_rate"]

    def _scope_ids(self):
        entity = self.request.query_params.get("entity")
        entityfinid = self.request.query_params.get("entityfinid")
        subentity = self.request.query_params.get("subentity")
        if not entity or not entityfinid:
            raise ValidationError({"detail": "entity and entityfinid query params are required."})
        try:
            entity_id = int(entity)
            entityfinid_id = int(entityfinid)
            subentity_id = int(subentity) if subentity not in (None, "", "null") else None
        except (TypeError, ValueError):
            raise ValidationError({"detail": "entity/entityfinid/subentity must be integers."})
        return entity_id, entityfinid_id, subentity_id

    def get_queryset(self):
        entity_id, entityfinid_id, subentity_id = self._scope_ids()
        qs = PurchaseTaxSummary.objects.select_related("header").filter(
            header__entity_id=entity_id,
            header__entityfinid_id=entityfinid_id,
        )
        if subentity_id is None:
            return qs
        return qs.filter(header__subentity_id=subentity_id)
