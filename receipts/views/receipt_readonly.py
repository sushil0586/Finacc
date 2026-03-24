from __future__ import annotations

from decimal import Decimal

from rest_framework import generics, permissions
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from financial.models import account
from financial.profile_access import account_gstno, account_pan, account_partytype
from receipts.serializers.receipt_readonly import ReceiptOpenAdvanceSerializer
from receipts.services.receipt_allocation_service import ReceiptAllocationService
from sales.models.sales_ar import CustomerSettlement
from sales.serializers.sales_ar import CustomerBillOpenItemSerializer, CustomerSettlementSerializer
from sales.services.sales_ar_service import SalesArService


class ReceiptCustomerBillOpenItemListAPIView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CustomerBillOpenItemSerializer

    def _scope(self):
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
            if subentity_id == 0:
                subentity_id = None
            customer_id = int(customer) if customer not in (None, "", "null") else None
        except (TypeError, ValueError):
            raise ValidationError({"detail": "entity/entityfinid/subentity/customer must be integers."})

        if is_open in (None, "", "null"):
            open_flag = True
        else:
            open_flag = str(is_open).strip().lower() in ("1", "true", "yes", "y")

        return entity_id, entityfinid_id, subentity_id, customer_id, open_flag

    def get_queryset(self):
        entity_id, entityfinid_id, subentity_id, customer_id, open_flag = self._scope()
        return SalesArService.list_open_items(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            customer_id=customer_id,
            is_open=open_flag,
        )

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        rows = list(qs)
        payload = CustomerBillOpenItemSerializer(rows, many=True).data

        _, _, subentity_id, customer_id, open_flag = self._scope()
        if customer_id is None:
            return Response(payload)

        entity_id = int(request.query_params.get("entity"))
        entityfinid_id = int(request.query_params.get("entityfinid"))
        projected = ReceiptAllocationService.build_open_item_projection(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            customer_id=customer_id,
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
            if subentity_id == 0:
                subentity_id = None
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


class ReceiptCustomerSettlementListAPIView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CustomerSettlementSerializer

    def get_queryset(self):
        entity = self.request.query_params.get("entity")
        entityfinid = self.request.query_params.get("entityfinid")
        subentity = self.request.query_params.get("subentity")
        customer = self.request.query_params.get("customer")

        if not entity or not entityfinid:
            raise ValidationError({"detail": "entity and entityfinid query params are required."})

        try:
            entity_id = int(entity)
            entityfinid_id = int(entityfinid)
            subentity_id = int(subentity) if subentity not in (None, "", "null") else None
            if subentity_id == 0:
                subentity_id = None
            customer_id = int(customer) if customer not in (None, "", "null") else None
        except (TypeError, ValueError):
            raise ValidationError({"detail": "entity/entityfinid/subentity/customer must be integers."})

        qs = (
            CustomerSettlement.objects
            .filter(entity_id=entity_id, entityfinid_id=entityfinid_id)
            .select_related(
                "customer",
                "customer__ledger",
                "advance_balance",
                "advance_balance__receipt_voucher",
            )
            .prefetch_related("lines__open_item")
        )
        if subentity_id is None:
            qs = qs.filter(subentity__isnull=True)
        else:
            qs = qs.filter(subentity_id=subentity_id)
        if customer_id is not None:
            qs = qs.filter(customer_id=customer_id)
        return qs.order_by("-settlement_date", "-id")


class ReceiptAllocationPreviewAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @staticmethod
    def _parse_int(data, key: str, required: bool = True):
        raw = data.get(key)
        if raw in (None, "", "null"):
            if required:
                raise ValidationError({key: f"{key} is required."})
            return None
        try:
            v = int(raw)
            if key == "subentity" and v == 0:
                return None
            return v
        except (TypeError, ValueError):
            raise ValidationError({key: f"{key} must be an integer."})

    def post(self, request):
        data = request.data if isinstance(request.data, dict) else {}
        entity_id = self._parse_int(data, "entity", required=True)
        entityfinid_id = self._parse_int(data, "entityfinid", required=True)
        subentity_id = self._parse_int(data, "subentity", required=False)
        customer_id = self._parse_int(data, "customer", required=True)

        cash = Decimal(str(data.get("cash_received_amount") or "0"))
        adjustments = data.get("adjustments") or []
        adjustment_total = Decimal("0.00")
        for row in adjustments:
            amt = Decimal(str((row or {}).get("amount") or "0"))
            eff = str((row or {}).get("settlement_effect") or "PLUS").upper()
            adjustment_total += (-amt if eff == "MINUS" else amt)

        target = cash + adjustment_total
        if target < Decimal("0.00"):
            target = Decimal("0.00")

        preview = ReceiptAllocationService.preview_allocation(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            customer_id=customer_id,
            target_amount=target,
        )
        preview["cash_received_amount"] = cash
        preview["adjustment_total"] = adjustment_total
        preview["effective_amount"] = target
        return Response(preview)


class ReceiptCustomerStatementAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        entity = request.query_params.get("entity")
        entityfinid = request.query_params.get("entityfinid")
        subentity = request.query_params.get("subentity")
        customer = request.query_params.get("customer")

        if not entity or not entityfinid:
            raise ValidationError({"detail": "entity and entityfinid query params are required."})
        if not customer:
            raise ValidationError({"customer": "customer query param is required."})

        try:
            entity_id = int(entity)
            entityfinid_id = int(entityfinid)
            subentity_id = int(subentity) if subentity not in (None, "", "null") else None
            if subentity_id == 0:
                subentity_id = None
            customer_id = int(customer)
        except (TypeError, ValueError):
            raise ValidationError({"detail": "entity/entityfinid/subentity/customer must be integers."})

        include_closed = str(request.query_params.get("include_closed") or "").lower() in ("1", "true", "yes", "y")
        data = SalesArService.customer_statement(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            customer_id=customer_id,
            include_closed=include_closed,
        )
        customer_obj = (
            account.objects.filter(id=customer_id)
            .select_related("ledger", "compliance_profile", "commercial_profile")
            .only(
                "id",
                "accountname",
                "ledger_id",
                "ledger__ledger_code",
                "ledger__name",
                "compliance_profile__gstno",
                "compliance_profile__pan",
                "commercial_profile__partytype",
            )
            .first()
        )
        customer_block = None
        if customer_obj is not None:
            customer_block = {
                "id": customer_obj.id,
                "accountname": customer_obj.accountname,
                "display_name": customer_obj.effective_accounting_name,
                "accountcode": customer_obj.effective_accounting_code,
                "ledger_id": customer_obj.ledger_id,
                "partytype": account_partytype(customer_obj),
                "gstno": account_gstno(customer_obj),
                "pan": account_pan(customer_obj),
            }
        return Response(
            {
                "customer": customer_block,
                "totals": data["totals"],
                "open_items": CustomerBillOpenItemSerializer(data["open_items"], many=True).data,
                "open_advances": ReceiptOpenAdvanceSerializer(data["advances"], many=True).data,
                "settlements": CustomerSettlementSerializer(data["settlements"], many=True).data,
            }
        )
