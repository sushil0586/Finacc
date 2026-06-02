from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from gst_reconciliation.models import GstReconciliationItem
from gst_reconciliation.serializers import GstSourceDocumentMetadataSerializer, GstSourceDocumentSearchSerializer
from gst_reconciliation.services.access import GstReconciliationWorkflowAccess
from gst_reconciliation.services.source_documents import SourceDocumentProviderRegistry


class GstSourceDocumentSearchAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = GstSourceDocumentSearchSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        item = None
        if serializer.validated_data.get("item_id"):
            item = get_object_or_404(
                GstReconciliationItem.objects.select_related("run"),
                pk=serializer.validated_data["item_id"],
            )
            GstReconciliationWorkflowAccess.assert_can_review_item(user=request.user, item=item)
        if item:
            entity_id = item.entity_id
            entityfinid_id = item.entityfinid_id
            subentity_id = item.subentity_id
            source_document_type = serializer.validated_data.get("source_document_type")
            if source_document_type:
                try:
                    provider = SourceDocumentProviderRegistry.get_provider(source_document_type)
                except ValueError as exc:
                    return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
                if not provider.supports_run_type(item.run.reconciliation_type):
                    return Response({"results": []}, status=status.HTTP_200_OK)
        else:
            if request.query_params.get("entity") in (None, "") or request.query_params.get("entityfinid") in (None, ""):
                raise serializers.ValidationError("entity and entityfinid are required when item_id is not provided.")
            entity_id = int(request.query_params.get("entity"))
            entityfinid_id = int(request.query_params.get("entityfinid"))
            subentity_raw = request.query_params.get("subentity")
            subentity_id = int(subentity_raw) if subentity_raw not in (None, "") else None
            GstReconciliationWorkflowAccess.assert_can_view_scope(user=request.user, entity_id=entity_id)
        try:
            results = SourceDocumentProviderRegistry.search(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                subentity_id=subentity_id,
                source_document_type=serializer.validated_data.get("source_document_type"),
                reconciliation_type=item.run.reconciliation_type if item else None,
                query=serializer.validated_data.get("query"),
                gstin=serializer.validated_data.get("gstin"),
                limit=serializer.validated_data.get("limit", 20),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "count": len(results),
                "results": GstSourceDocumentMetadataSerializer(results, many=True).data,
            },
            status=status.HTTP_200_OK,
        )


class GstSourceDocumentDetailAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, source_document_type: str, document_id: str):
        try:
            provider = SourceDocumentProviderRegistry.get_provider(source_document_type)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        if request.query_params.get("entity") in (None, "") or request.query_params.get("entityfinid") in (None, ""):
            raise serializers.ValidationError("entity and entityfinid are required.")
        entity_id = int(request.query_params.get("entity"))
        entityfinid_id = int(request.query_params.get("entityfinid"))
        subentity_raw = request.query_params.get("subentity")
        subentity_id = int(subentity_raw) if subentity_raw not in (None, "") else None
        GstReconciliationWorkflowAccess.assert_can_view_scope(user=request.user, entity_id=entity_id)
        document = provider.get_queryset_for_scope(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
        ).filter(pk=document_id).first()
        if not document:
            return Response({"detail": "Source document not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(GstSourceDocumentMetadataSerializer(provider.to_metadata(document)).data, status=status.HTTP_200_OK)
