from __future__ import annotations

from rest_framework import generics, permissions, serializers, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from gst_reconciliation.models import GstImportedReturn, GstImportedReturnRow
from gst_reconciliation.serializers import (
    GstGstr2bExcelImportSerializer,
    GstGstr2bJsonImportSerializer,
    GstImportedReturnRowSerializer,
    GstImportedReturnSerializer,
    GstReconciliationRunSerializer,
)
from gst_reconciliation.services.access import GstReconciliationWorkflowAccess
from gst_reconciliation.services.importing import Gstr2bImportPipeline
from gst_reconciliation.services.performance import timed_call


class GstImportedReturnListAPIView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = GstImportedReturnSerializer

    def get_queryset(self):
        entity_id = self.request.query_params.get("entity")
        if not entity_id:
            raise serializers.ValidationError({"entity": ["Entity is required."]})
        GstReconciliationWorkflowAccess.assert_can_view_scope(user=self.request.user, entity_id=int(entity_id))
        queryset = GstImportedReturn.objects.all().select_related("entity", "entityfinid", "subentity", "imported_by")
        return_type = self.request.query_params.get("return_type")
        return_period = self.request.query_params.get("return_period")
        if entity_id:
            queryset = queryset.filter(entity_id=entity_id)
        if return_type:
            queryset = queryset.filter(return_type=return_type)
        if return_period:
            queryset = queryset.filter(return_period=return_period)
        return queryset.order_by("-created_at", "-id")


class GstImportedReturnDetailAPIView(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]
    queryset = GstImportedReturn.objects.all().select_related("entity", "entityfinid", "subentity", "imported_by")
    serializer_class = GstImportedReturnSerializer

    def get_object(self):
        obj = super().get_object()
        GstReconciliationWorkflowAccess.assert_can_view_scope(user=self.request.user, entity_id=obj.entity_id)
        return obj


class GstImportedReturnRowListAPIView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = GstImportedReturnRowSerializer

    def get_queryset(self):
        imported_return = GstImportedReturn.objects.select_related("entity").get(pk=self.kwargs["pk"])
        GstReconciliationWorkflowAccess.assert_can_view_scope(user=self.request.user, entity_id=imported_return.entity_id)
        return (
            GstImportedReturnRow.objects.filter(imported_return_id=self.kwargs["pk"])
            .select_related("imported_return")
            .order_by("row_no", "id")
        )


class GstGstr2bJsonImportAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [JSONParser]

    def post(self, request):
        serializer = GstGstr2bJsonImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        GstReconciliationWorkflowAccess.assert_can_manage_scope(user=request.user, entity_id=payload["entity"].id)
        timed = timed_call(
            "gstr2b_import_json",
            lambda: Gstr2bImportPipeline.import_json(
                entity_id=payload["entity"],
                entityfinid_id=payload["entityfinid"],
                subentity_id=payload.get("subentity"),
                user=request.user,
                return_period=payload["return_period"],
                payload=payload["payload"],
                gst_registration_gstin=payload.get("gst_registration_gstin"),
                reference=payload.get("reference"),
                create_run=payload.get("create_run", True),
                tolerance_config_json=payload.get("tolerance_config_json") or {},
            ),
            entity_id=payload["entity"].id,
            return_period=payload["return_period"],
        )
        imported_return, run = timed.value
        response = Response(
            {
                "imported_return": GstImportedReturnSerializer(imported_return).data,
                "run": GstReconciliationRunSerializer(run).data if run else None,
                "timing_ms": timed.duration_ms,
            },
            status=status.HTTP_201_CREATED,
        )
        response["X-GST-Recon-Timing-Ms"] = str(timed.duration_ms)
        return response


class GstGstr2bExcelImportAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = GstGstr2bExcelImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        GstReconciliationWorkflowAccess.assert_can_manage_scope(user=request.user, entity_id=payload["entity"].id)
        upload = payload["file"]
        timed = timed_call(
            "gstr2b_import_excel",
            lambda: Gstr2bImportPipeline.import_excel(
                entity_id=payload["entity"],
                entityfinid_id=payload["entityfinid"],
                subentity_id=payload.get("subentity"),
                user=request.user,
                return_period=payload["return_period"],
                filename=upload.name,
                content=upload.read(),
                gst_registration_gstin=payload.get("gst_registration_gstin"),
                create_run=payload.get("create_run", True),
                tolerance_config_json=payload.get("tolerance_config_json") or {},
            ),
            entity_id=payload["entity"].id,
            return_period=payload["return_period"],
        )
        imported_return, run = timed.value
        response = Response(
            {
                "imported_return": GstImportedReturnSerializer(imported_return).data,
                "run": GstReconciliationRunSerializer(run).data if run else None,
                "timing_ms": timed.duration_ms,
            },
            status=status.HTTP_201_CREATED,
        )
        response["X-GST-Recon-Timing-Ms"] = str(timed.duration_ms)
        return response
