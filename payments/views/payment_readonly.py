from __future__ import annotations

from decimal import Decimal

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
from purchase.services.ap_allocation_service import PurchaseApAllocationService
from financial.profile_access import account_gstno, account_pan, account_partytype


class PaymentVendorBillOpenItemListAPIView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = VendorBillOpenItemSerializer

    def _scope(self):
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

        return entity_id, entityfinid_id, subentity_id, vendor_id, open_flag

    def get_queryset(self):
        entity_id, entityfinid_id, subentity_id, vendor_id, open_flag = self._scope()
        return PurchaseApService.list_open_items(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            vendor_id=vendor_id,
            is_open=open_flag,
        )

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        rows = list(qs)
        payload = VendorBillOpenItemSerializer(rows, many=True).data

        entity_id, entityfinid_id, subentity_id, vendor_id, open_flag = self._scope()
        if vendor_id is None:
            return Response(payload)

        projected = PurchaseApAllocationService.build_open_item_projection(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            vendor_id=vendor_id,
        )
        by_id = {int(r["id"]): r for r in projected}

        out = []
        for row in payload:
            rid = int(row.get("id"))
            enrich = by_id.get(rid, {})
            row["raw_outstanding_amount"] = enrich.get("raw_outstanding_amount", row.get("outstanding_amount"))
            row["credit_adjusted_amount"] = enrich.get("credit_adjusted_amount", "0.00")
            row["allocatable_amount"] = enrich.get("allocatable_amount", "0.00")
            row["allocation_sequence"] = enrich.get("allocation_sequence")
            row["is_allocatable"] = enrich.get("is_allocatable", False)
            row["reference_invoice_header_id"] = enrich.get("reference_invoice_header_id")
            if open_flag:
                allocatable = Decimal(str(row.get("allocatable_amount") or "0"))
                if allocatable <= Decimal("0"):
                    continue
            out.append(row)
        return Response(out)


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


class PaymentAllocationPreviewAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @staticmethod
    def _parse_int(data, key: str, required: bool = True):
        raw = data.get(key)
        if raw in (None, "", "null"):
            if required:
                raise ValidationError({key: f"{key} is required."})
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            raise ValidationError({key: f"{key} must be an integer."})

    @staticmethod
    def _parse_decimal(data, key: str, default: str = "0") -> Decimal:
        raw = data.get(key, default)
        try:
            return Decimal(str(raw or default))
        except Exception:
            raise ValidationError({key: f"{key} must be numeric."})

    def post(self, request):
        data = request.data or {}
        entity_id = self._parse_int(data, "entity")
        entityfinid_id = self._parse_int(data, "entityfinid")
        vendor_id = self._parse_int(data, "vendor")
        subentity_id = self._parse_int(data, "subentity", required=False)

        cash_paid_amount = self._parse_decimal(data, "cash_paid_amount", default="0")
        adjustments = data.get("adjustments") or []
        if not isinstance(adjustments, list):
            raise ValidationError({"adjustments": "adjustments must be a list."})

        adjustment_total = Decimal("0")
        for idx, row in enumerate(adjustments, start=1):
            if not isinstance(row, dict):
                raise ValidationError({"adjustments": f"adjustments[{idx}] must be an object."})
            amount = self._parse_decimal(row, "amount", default="0")
            effect = str(row.get("settlement_effect") or "PLUS").upper().strip()
            if effect == "MINUS":
                adjustment_total -= amount
            else:
                adjustment_total += amount

        effective = cash_paid_amount + adjustment_total
        if effective < Decimal("0"):
            effective = Decimal("0")

        projection = PurchaseApAllocationService.preview_allocation(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            vendor_id=vendor_id,
            target_amount=effective,
        )
        return Response({
            "effective_settlement_amount": projection["target_amount"],
            "planned_amount": projection["planned_amount"],
            "unallocated_amount": projection["unallocated_amount"],
            "plan": projection["plan"],
            "open_items": projection["open_items"],
        })


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
                "partytype": account_partytype(vendor_obj),
                "gstno": account_gstno(vendor_obj),
                "pan": account_pan(vendor_obj),
            },
            "totals": data["totals"],
            "open_items": VendorBillOpenItemSerializer(data["open_items"], many=True).data,
            "open_advances": PaymentOpenAdvanceSerializer(data["advances"], many=True).data,
            "settlements": VendorSettlementSerializer(data["settlements"], many=True).data,
        })
