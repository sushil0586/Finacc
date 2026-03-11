from __future__ import annotations

from rest_framework import generics, permissions
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from payments.serializers.payment_readonly import PaymentOpenAdvanceSerializer
from purchase.models.purchase_ap import VendorSettlement
from purchase.serializers.purchase_ap import (
    VendorBillOpenItemSerializer,
    VendorSettlementSerializer,
)
from purchase.services.purchase_ap_service import PurchaseApService


class PaymentVendorBillOpenItemListAPIView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = VendorBillOpenItemSerializer

    def get_queryset(self):
        entity = self.request.query_params.get("entity")
        entityfinid = self.request.query_params.get("entityfinid")
        subentity = self.request.query_params.get("subentity")
        vendor = self.request.query_params.get("vendor")
        is_open = self.request.query_params.get("is_open")

        if not entity or not entityfinid:
            raise ValidationError({"detail": "entity and entityfinid query params are required."})

        try:
            entity_id = int(entity)
            entityfinid_id = int(entityfinid)
            subentity_id = int(subentity) if subentity not in (None, "", "null") else None
            if subentity_id == 0:
                subentity_id = None
            vendor_id = int(vendor) if vendor not in (None, "", "null") else None
        except (TypeError, ValueError):
            raise ValidationError({"detail": "entity/entityfinid/subentity/vendor must be integers."})

        if is_open in (None, "", "null"):
            open_flag = True
        else:
            open_flag = str(is_open).strip().lower() in ("1", "true", "yes", "y")

        return PurchaseApService.list_open_items(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            vendor_id=vendor_id,
            is_open=open_flag,
        )


class PaymentVendorAdvanceBalanceListAPIView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PaymentOpenAdvanceSerializer

    def get_queryset(self):
        entity = self.request.query_params.get("entity")
        entityfinid = self.request.query_params.get("entityfinid")
        subentity = self.request.query_params.get("subentity")
        vendor = self.request.query_params.get("vendor")
        is_open = self.request.query_params.get("is_open")

        if not entity or not entityfinid:
            raise ValidationError({"detail": "entity and entityfinid query params are required."})

        try:
            entity_id = int(entity)
            entityfinid_id = int(entityfinid)
            subentity_id = int(subentity) if subentity not in (None, "", "null") else None
            if subentity_id == 0:
                subentity_id = None
            vendor_id = int(vendor) if vendor not in (None, "", "null") else None
        except (TypeError, ValueError):
            raise ValidationError({"detail": "entity/entityfinid/subentity/vendor must be integers."})

        if is_open in (None, "", "null"):
            open_flag = True
        else:
            open_flag = str(is_open).strip().lower() in ("1", "true", "yes", "y")

        return PurchaseApService.list_open_advances(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            vendor_id=vendor_id,
            is_open=open_flag,
        ).select_related("payment_voucher")


class PaymentVendorSettlementListAPIView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = VendorSettlementSerializer

    def get_queryset(self):
        entity = self.request.query_params.get("entity")
        entityfinid = self.request.query_params.get("entityfinid")
        subentity = self.request.query_params.get("subentity")
        vendor = self.request.query_params.get("vendor")

        if not entity or not entityfinid:
            raise ValidationError({"detail": "entity and entityfinid query params are required."})

        try:
            entity_id = int(entity)
            entityfinid_id = int(entityfinid)
            subentity_id = int(subentity) if subentity not in (None, "", "null") else None
            if subentity_id == 0:
                subentity_id = None
            vendor_id = int(vendor) if vendor not in (None, "", "null") else None
        except (TypeError, ValueError):
            raise ValidationError({"detail": "entity/entityfinid/subentity/vendor must be integers."})

        qs = (
            VendorSettlement.objects
            .filter(entity_id=entity_id, entityfinid_id=entityfinid_id)
            .select_related(
                "vendor",
                "vendor__ledger",
                "advance_balance",
                "advance_balance__payment_voucher",
            )
            .prefetch_related("lines__open_item")
        )
        qs = PurchaseApService._apply_subentity_scope(qs, subentity_id)
        if vendor_id is not None:
            qs = qs.filter(vendor_id=vendor_id)
        return qs.order_by("-settlement_date", "-id")


class PaymentVendorStatementAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        entity = request.query_params.get("entity")
        entityfinid = request.query_params.get("entityfinid")
        subentity = request.query_params.get("subentity")
        vendor = request.query_params.get("vendor")

        if not entity or not entityfinid:
            raise ValidationError({"detail": "entity and entityfinid query params are required."})
        if not vendor:
            raise ValidationError({"vendor": "vendor query param is required."})

        try:
            entity_id = int(entity)
            entityfinid_id = int(entityfinid)
            subentity_id = int(subentity) if subentity not in (None, "", "null") else None
            if subentity_id == 0:
                subentity_id = None
            vendor_id = int(vendor)
        except (TypeError, ValueError):
            raise ValidationError({"detail": "entity/entityfinid/subentity/vendor must be integers."})

        include_closed = str(request.query_params.get("include_closed") or "").lower() in ("1", "true", "yes", "y")

        data = PurchaseApService.vendor_statement(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            vendor_id=vendor_id,
            include_closed=include_closed,
        )
        vendor_obj = data["vendor"]

        return Response({
            "vendor": {
                "id": vendor_obj.id,
                "accountname": getattr(vendor_obj, "accountname", None),
                "display_name": getattr(vendor_obj, "effective_accounting_name", None),
                "accountcode": getattr(vendor_obj, "effective_accounting_code", None),
                "ledger_id": getattr(vendor_obj, "ledger_id", None),
                "partytype": getattr(vendor_obj, "partytype", None),
                "gstno": getattr(vendor_obj, "gstno", None),
                "pan": getattr(vendor_obj, "pan", None),
            },
            "totals": data["totals"],
            "open_items": VendorBillOpenItemSerializer(data["open_items"], many=True).data,
            "open_advances": PaymentOpenAdvanceSerializer(data["advances"], many=True).data,
            "settlements": VendorSettlementSerializer(data["settlements"], many=True).data,
        })
