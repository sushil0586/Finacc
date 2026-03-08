from __future__ import annotations

from rest_framework import generics, permissions
from rest_framework.exceptions import ValidationError

from receipts.serializers.receipt_readonly import ReceiptOpenAdvanceSerializer
from sales.serializers.sales_ar import CustomerBillOpenItemSerializer
from sales.services.sales_ar_service import SalesArService


class ReceiptCustomerBillOpenItemListAPIView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CustomerBillOpenItemSerializer

    def get_queryset(self):
        entity = self.request.query_params.get("entity")
        entityfinid = self.request.query_params.get("entityfinid")
        subentity = self.request.query_params.get("subentity")
        customer = self.request.query_params.get("customer")
        is_open = self.request.query_params.get("is_open")

        if not entity or not entityfinid:
            raise ValidationError({"detail": "entity and entityfinid query params are required."})

        try:
            entity_id = int(entity)
            entityfinid_id = int(entityfinid)
            subentity_id = int(subentity) if subentity not in (None, "", "null") else None
            customer_id = int(customer) if customer not in (None, "", "null") else None
        except (TypeError, ValueError):
            raise ValidationError({"detail": "entity/entityfinid/subentity/customer must be integers."})

        if is_open in (None, "", "null"):
            open_flag = True
        else:
            open_flag = str(is_open).strip().lower() in ("1", "true", "yes", "y")

        return SalesArService.list_open_items(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            customer_id=customer_id,
            is_open=open_flag,
        )


class ReceiptCustomerAdvanceBalanceListAPIView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ReceiptOpenAdvanceSerializer

    def get_queryset(self):
        entity = self.request.query_params.get("entity")
        entityfinid = self.request.query_params.get("entityfinid")
        subentity = self.request.query_params.get("subentity")
        customer = self.request.query_params.get("customer")
        is_open = self.request.query_params.get("is_open")

        if not entity or not entityfinid:
            raise ValidationError({"detail": "entity and entityfinid query params are required."})

        try:
            entity_id = int(entity)
            entityfinid_id = int(entityfinid)
            subentity_id = int(subentity) if subentity not in (None, "", "null") else None
            customer_id = int(customer) if customer not in (None, "", "null") else None
        except (TypeError, ValueError):
            raise ValidationError({"detail": "entity/entityfinid/subentity/customer must be integers."})

        if is_open in (None, "", "null"):
            open_flag = True
        else:
            open_flag = str(is_open).strip().lower() in ("1", "true", "yes", "y")

        return SalesArService.list_open_advances(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            customer_id=customer_id,
            is_open=open_flag,
        ).select_related("receipt_voucher")
