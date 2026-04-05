from __future__ import annotations

from decimal import Decimal

from django.shortcuts import get_object_or_404
from django.db.models import Sum
from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from entity.models import Entity, SubEntity, EntityFinancialYear
from financial.models import account
from gst_tds.models import EntityGstTdsConfig, GstTdsContractLedger, GstTdsMasterRule
from gst_tds.serializers import (
    EntityGstTdsConfigSerializer,
    GstTdsContractLedgerSerializer,
)


def _to_int(raw, field_name: str, *, required: bool = False):
    if raw in (None, "", "null"):
        if required:
            raise ValidationError({field_name: "This value is required."})
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ValidationError({field_name: "Must be an integer."})


class GstTdsConfigAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _scope(self, request):
        entity_id = _to_int(
            request.query_params.get("entity", request.data.get("entity")),
            "entity",
            required=True,
        )
        subentity_id = _to_int(
            request.query_params.get("subentity", request.data.get("subentity")),
            "subentity",
            required=False,
        )

        entity = get_object_or_404(Entity, pk=entity_id)
        subentity = None
        if subentity_id is not None:
            subentity = get_object_or_404(SubEntity, pk=subentity_id)
            if int(subentity.entity_id) != int(entity.id):
                raise ValidationError({"subentity": "Subentity does not belong to the selected entity."})
        return entity, subentity

    def get(self, request):
        entity, subentity = self._scope(request)
        obj = EntityGstTdsConfig.objects.filter(
            entity_id=entity.id,
            subentity_id=(subentity.id if subentity else None),
        ).first()
        if obj is None:
            return Response(
                {
                    "exists": False,
                    "config": {
                        "entity": entity.id,
                        "subentity": subentity.id if subentity else None,
                        "master_rule": None,
                        "enabled": False,
                        "threshold_amount": str(Decimal("250000.00")),
                        "enforce_pos_rule": True,
                    },
                },
                status=status.HTTP_200_OK,
            )
        return Response({"exists": True, "config": EntityGstTdsConfigSerializer(obj).data}, status=status.HTTP_200_OK)

    def put(self, request):
        entity, subentity = self._scope(request)
        obj = EntityGstTdsConfig.objects.filter(
            entity_id=entity.id,
            subentity_id=(subentity.id if subentity else None),
        ).first()
        if obj is None:
            obj = EntityGstTdsConfig(entity=entity, subentity=subentity)
        serializer = EntityGstTdsConfigSerializer(
            obj,
            data={
                "master_rule": request.data.get("master_rule", getattr(obj, "master_rule_id", None)),
                "enabled": request.data.get("enabled", getattr(obj, "enabled", False)),
                "threshold_amount": request.data.get("threshold_amount", getattr(obj, "threshold_amount", Decimal("250000.00"))),
                "enforce_pos_rule": request.data.get("enforce_pos_rule", getattr(obj, "enforce_pos_rule", True)),
            },
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        master_rule_id = serializer.validated_data.get("master_rule")
        if master_rule_id is not None:
            get_object_or_404(GstTdsMasterRule, pk=getattr(master_rule_id, "id", master_rule_id))
        serializer.save(entity=entity, subentity=subentity)
        return Response({"message": "GST-TDS config saved.", "config": serializer.data}, status=status.HTTP_200_OK)

    patch = put


class GstTdsContractLedgerListAPIView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = GstTdsContractLedgerSerializer

    def get_queryset(self):
        entity_id = _to_int(self.request.query_params.get("entity"), "entity", required=True)
        entityfinid_id = _to_int(self.request.query_params.get("entityfinid"), "entityfinid", required=False)
        subentity_id = _to_int(self.request.query_params.get("subentity"), "subentity", required=False)
        vendor_id = _to_int(self.request.query_params.get("vendor"), "vendor", required=False)
        contract_ref = str(self.request.query_params.get("contract_ref", "") or "").strip()

        entity = get_object_or_404(Entity, pk=entity_id)
        qs = GstTdsContractLedger.objects.select_related("vendor").filter(entity_id=entity_id)
        if entityfinid_id is not None:
            fy = get_object_or_404(EntityFinancialYear, pk=entityfinid_id)
            if int(getattr(fy, "entity_id", 0) or 0) != int(entity.id):
                raise ValidationError({"entityfinid": "Financial year does not belong to the selected entity."})
            qs = qs.filter(entityfinid_id=entityfinid_id)
        if subentity_id is not None:
            subentity = get_object_or_404(SubEntity, pk=subentity_id)
            if int(getattr(subentity, "entity_id", 0) or 0) != int(entity.id):
                raise ValidationError({"subentity": "Subentity does not belong to the selected entity."})
            qs = qs.filter(subentity_id=subentity_id)
        if vendor_id is not None:
            vendor = get_object_or_404(account, pk=vendor_id)
            if int(getattr(vendor, "entity_id", 0) or 0) != int(entity.id):
                raise ValidationError({"vendor": "Vendor does not belong to the selected entity."})
            qs = qs.filter(vendor_id=vendor_id)
        if contract_ref:
            qs = qs.filter(contract_ref__icontains=contract_ref)
        return qs.order_by("vendor_id", "contract_ref", "-updated_at")


class GstTdsContractLedgerSummaryAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        entity_id = _to_int(request.query_params.get("entity"), "entity", required=True)
        entityfinid_id = _to_int(request.query_params.get("entityfinid"), "entityfinid", required=False)
        subentity_id = _to_int(request.query_params.get("subentity"), "subentity", required=False)
        vendor_id = _to_int(request.query_params.get("vendor"), "vendor", required=False)
        contract_ref = str(request.query_params.get("contract_ref", "") or "").strip()

        entity = get_object_or_404(Entity, pk=entity_id)
        qs = GstTdsContractLedger.objects.filter(entity_id=entity.id)

        if entityfinid_id is not None:
            fy = get_object_or_404(EntityFinancialYear, pk=entityfinid_id)
            if int(getattr(fy, "entity_id", 0) or 0) != int(entity.id):
                raise ValidationError({"entityfinid": "Financial year does not belong to the selected entity."})
            qs = qs.filter(entityfinid_id=entityfinid_id)

        if subentity_id is not None:
            subentity = get_object_or_404(SubEntity, pk=subentity_id)
            if int(getattr(subentity, "entity_id", 0) or 0) != int(entity.id):
                raise ValidationError({"subentity": "Subentity does not belong to the selected entity."})
            qs = qs.filter(subentity_id=subentity_id)

        if vendor_id is not None:
            vendor = get_object_or_404(account, pk=vendor_id)
            if int(getattr(vendor, "entity_id", 0) or 0) != int(entity.id):
                raise ValidationError({"vendor": "Vendor does not belong to the selected entity."})
            qs = qs.filter(vendor_id=vendor_id)
        if contract_ref:
            qs = qs.filter(contract_ref__icontains=contract_ref)

        totals = qs.aggregate(
            total_taxable=Sum("cumulative_taxable"),
            total_tds=Sum("cumulative_tds"),
        )
        return Response(
            {
                "entity": entity.id,
                "entityfinid": entityfinid_id,
                "subentity": subentity_id,
                "vendor": vendor_id,
                "contract_ref": contract_ref or None,
                "total_contracts": int(qs.count()),
                "total_taxable": str(totals.get("total_taxable") or Decimal("0.00")),
                "total_tds": str(totals.get("total_tds") or Decimal("0.00")),
            },
            status=status.HTTP_200_OK,
        )
