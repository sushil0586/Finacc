from __future__ import annotations

from rest_framework import generics, permissions
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from financial.models import account
from financial.profile_access import account_gstno, account_pan, account_partytype
from receipts.serializers.receipt_readonly import ReceiptOpenAdvanceSerializer
from sales.models.sales_ar import CustomerSettlement
from sales.serializers.sales_ar import CustomerBillOpenItemSerializer, CustomerSettlementSerializer
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
            if subentity_id == 0:
                subentity_id = None
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
