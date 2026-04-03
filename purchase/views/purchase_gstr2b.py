from __future__ import annotations

from rest_framework import permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from purchase.models.gstr2b_models import Gstr2bImportBatch, Gstr2bImportRow
from purchase.serializers.purchase_gstr2b import (
    Gstr2bImportBatchCreateSerializer,
    Gstr2bImportBatchSerializer,
    Gstr2bImportRowSerializer,
)
from purchase.services.purchase_gstr2b_service import PurchaseGstr2bService


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
    except (TypeError, ValueError):
        raise ValidationError({"detail": "entity/entityfinid/subentity must be integers."})
    return entity_id, entityfinid_id, subentity_id


class PurchaseGstr2bImportBatchListCreateAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        entity_id, entityfinid_id, subentity_id = _parse_scope(request)
        qs = Gstr2bImportBatch.objects.filter(entity_id=entity_id, entityfinid_id=entityfinid_id)
        if subentity_id is None:
            qs = qs.filter(subentity__isnull=True)
        else:
            qs = qs.filter(subentity_id=subentity_id)
        data = Gstr2bImportBatchSerializer(qs.order_by("-id"), many=True).data
        return Response({"count": len(data), "results": data})

    def post(self, request):
        ser = Gstr2bImportBatchCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        batch = PurchaseGstr2bService.create_batch(
            entity_id=v["entity"],
            entityfinid_id=v["entityfinid"],
            subentity_id=v.get("subentity"),
            period=v["period"],
            source=v.get("source") or "gstr2b",
            reference=v.get("reference"),
            rows=v["rows"],
            imported_by_id=request.user.id,
        )
        return Response(
            {
                "message": "GSTR-2B batch imported.",
                "data": Gstr2bImportBatchSerializer(batch).data,
                "row_count": len(v["rows"]),
            },
            status=status.HTTP_201_CREATED,
        )


class PurchaseGstr2bImportBatchRowsAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk: int):
        entity_id, entityfinid_id, subentity_id = _parse_scope(request)
        batch = Gstr2bImportBatch.objects.filter(
            pk=pk,
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
        ).first()
        if not batch:
            raise ValidationError({"detail": "Batch not found for scope."})
        if subentity_id is not None and batch.subentity_id != subentity_id:
            raise ValidationError({"detail": "Batch subentity mismatch."})
        rows = Gstr2bImportRow.objects.filter(batch_id=batch.id).order_by("id")
        data = Gstr2bImportRowSerializer(rows, many=True).data
        return Response({"batch_id": batch.id, "count": len(data), "results": data})


class PurchaseGstr2bImportBatchMatchAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        result = PurchaseGstr2bService.auto_match_batch(batch_id=pk)
        return Response(
            {
                "message": "GSTR-2B auto-match completed.",
                "batch_id": result.batch.id,
                "summary": {
                    "total_rows": result.total_rows,
                    "matched": result.matched,
                    "partial": result.partial,
                    "multiple": result.multiple,
                    "not_matched": result.not_matched,
                },
            }
        )

