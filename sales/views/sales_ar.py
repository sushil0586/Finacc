from __future__ import annotations

from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from sales.models.sales_ar import CustomerSettlement
from sales.serializers.sales_ar import (
    CustomerAdvanceBalanceSerializer,
    CustomerBillOpenItemSerializer,
    CustomerSettlementSerializer,
    CustomerSettlementCreateInputSerializer,
)
from sales.services.sales_ar_service import SalesArService
from sales.views.rbac import require_sales_scope_permission
from financial.models import account
from financial.profile_access import account_gstno, account_pan, account_partytype


def _parse_scope(request):
    entity = request.query_params.get("entity")
    entityfinid = request.query_params.get("entityfinid")
    subentity = request.query_params.get("subentity")
    if not entity or not entityfinid:
        raise ValidationError({"detail": "entity and entityfinid query params are required."})
    try:
        entity_id = int(entity)
        entityfinid_id = int(entityfinid)
        subentity_id = int(subentity) if subentity not in (None, "", "null") else None
        if subentity_id == 0:
            subentity_id = None
    except (TypeError, ValueError):
        raise ValidationError({"detail": "entity/entityfinid/subentity must be integers."})
    return entity_id, entityfinid_id, subentity_id


def _require_ar_view_permission(*, user, entity_id: int):
    require_sales_scope_permission(
        user=user,
        entity_id=entity_id,
        permission_codes=("sales.invoice.view", "sales.invoice.update"),
        access_mode="operational",
        feature_code="feature_sales",
        message="Missing permission to access sales AR data.",
    )


def _require_ar_manage_permission(*, user, entity_id: int):
    require_sales_scope_permission(
        user=user,
        entity_id=entity_id,
        permission_codes=("sales.invoice.update", "sales.invoice.post", "sales.invoice.unpost"),
        access_mode="operational",
        feature_code="feature_sales",
        message="Missing permission to manage sales AR data.",
    )


class CustomerBillOpenItemListAPIView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CustomerBillOpenItemSerializer

    def get_queryset(self):
        entity_id, entityfinid_id, subentity_id = _parse_scope(self.request)
        _require_ar_view_permission(user=self.request.user, entity_id=entity_id)

        customer = self.request.query_params.get("customer")
        is_open = self.request.query_params.get("is_open")
        customer_id = int(customer) if customer not in (None, "", "null") else None

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
        ).select_related("customer", "customer__ledger", "header")


class CustomerAdvanceBalanceListAPIView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CustomerAdvanceBalanceSerializer

    def get_queryset(self):
        entity_id, entityfinid_id, subentity_id = _parse_scope(self.request)
        _require_ar_view_permission(user=self.request.user, entity_id=entity_id)
        customer = self.request.query_params.get("customer")
        is_open = self.request.query_params.get("is_open")
        customer_id = int(customer) if customer not in (None, "", "null") else None

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
        ).select_related("customer", "customer__ledger", "receipt_voucher").prefetch_related("settlements__lines__open_item")


class CustomerSettlementListCreateAPIView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CustomerSettlementSerializer

    def get_queryset(self):
        entity_id, entityfinid_id, subentity_id = _parse_scope(self.request)
        _require_ar_view_permission(user=self.request.user, entity_id=entity_id)
        qs = CustomerSettlement.objects.prefetch_related("lines").filter(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
        )
        if subentity_id is None:
            qs = qs.filter(subentity__isnull=True)
        else:
            qs = qs.filter(subentity_id=subentity_id)
        customer = self.request.query_params.get("customer")
        if customer not in (None, "", "null"):
            qs = qs.filter(customer_id=int(customer))
        return qs.order_by("-settlement_date", "-id")

    def create(self, request, *args, **kwargs):
        inp = CustomerSettlementCreateInputSerializer(data=request.data)
        inp.is_valid(raise_exception=True)
        data = inp.validated_data
        _require_ar_manage_permission(user=request.user, entity_id=data["entity"])

        try:
            res = SalesArService.create_settlement(
                entity_id=data["entity"],
                entityfinid_id=data["entityfinid"],
                subentity_id=data.get("subentity"),
                customer_id=data["customer"],
                settlement_type=data["settlement_type"],
                settlement_date=data["settlement_date"],
                reference_no=data.get("reference_no"),
                external_voucher_no=data.get("external_voucher_no"),
                remarks=data.get("remarks"),
                lines=data.get("lines"),
                amount=data.get("amount"),
                advance_balance_id=data.get("advance_balance"),
            )
        except ValueError as e:
            raise ValidationError({"detail": str(e)})

        out = CustomerSettlementSerializer(res.settlement, context=self.get_serializer_context())
        return Response({"message": res.message, "data": out.data}, status=status.HTTP_201_CREATED)


class CustomerSettlementPostAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        settlement = CustomerSettlement.objects.filter(pk=pk).only("id", "entity_id").first()
        if settlement is None:
            raise ValidationError({"detail": "Settlement not found."})
        _require_ar_manage_permission(user=request.user, entity_id=settlement.entity_id)
        try:
            res = SalesArService.post_settlement(settlement_id=pk, posted_by_id=request.user.id)
        except ValueError as e:
            raise ValidationError({"detail": str(e)})
        return Response({
            "message": res.message,
            "applied_total": str(res.applied_total),
            "data": CustomerSettlementSerializer(res.settlement).data,
        })


class CustomerSettlementCancelAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        settlement = CustomerSettlement.objects.filter(pk=pk).only("id", "entity_id").first()
        if settlement is None:
            raise ValidationError({"detail": "Settlement not found."})
        _require_ar_manage_permission(user=request.user, entity_id=settlement.entity_id)
        try:
            res = SalesArService.cancel_settlement(settlement_id=pk, cancelled_by_id=request.user.id)
        except ValueError as e:
            raise ValidationError({"detail": str(e)})
        return Response({
            "message": res.message,
            "data": CustomerSettlementSerializer(res.settlement).data,
        })


class CustomerStatementAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        entity_id, entityfinid_id, subentity_id = _parse_scope(request)
        _require_ar_view_permission(user=request.user, entity_id=entity_id)
        customer = request.query_params.get("customer")
        if not customer:
            raise ValidationError({"customer": "customer query param is required."})
        try:
            customer_id = int(customer)
        except (TypeError, ValueError):
            raise ValidationError({"customer": "customer must be an integer."})
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
            .select_related("ledger")
            .select_related("ledger", "compliance_profile", "commercial_profile").only("id", "accountname", "ledger_id", "ledger__ledger_code", "ledger__name")
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

        return Response({
            "customer": customer_block,
            "totals": data["totals"],
            "open_items": CustomerBillOpenItemSerializer(data["open_items"], many=True).data,
            "advances": CustomerAdvanceBalanceSerializer(data["advances"], many=True).data,
            "settlements": CustomerSettlementSerializer(data["settlements"], many=True).data,
        })
