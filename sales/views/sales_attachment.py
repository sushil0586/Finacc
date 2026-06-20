from __future__ import annotations

import mimetypes

from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from helpers.utils.attachment_validation import validate_attachment_uploads
from sales.models import SalesAttachment, SalesInvoiceHeader
from sales.serializers.sales_attachment import SalesAttachmentSerializer


class SalesAttachmentBaseAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def _scope_ids(self, request):
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

    def _scoped_header(self, request, pk: int) -> SalesInvoiceHeader:
        entity_id, entityfinid_id, subentity_id = self._scope_ids(request)
        qs = SalesInvoiceHeader.objects.filter(entity_id=entity_id, entityfinid_id=entityfinid_id)
        if subentity_id is not None:
            qs = qs.filter(subentity_id=subentity_id)
        return get_object_or_404(qs, pk=pk)


class SalesInvoiceAttachmentListCreateAPIView(SalesAttachmentBaseAPIView):
    def get(self, request, pk: int):
        header = self._scoped_header(request, pk)
        rows = header.attachments.order_by("-created_at", "-id")
        return Response(SalesAttachmentSerializer(rows, many=True).data)

    def post(self, request, pk: int):
        header = self._scoped_header(request, pk)
        files = request.FILES.getlist("attachments") or request.FILES.getlist("file")
        if not files:
            raise ValidationError({"detail": "At least one attachment file is required."})
        validate_attachment_uploads(files)
        created = []
        for file_obj in files:
            created.append(
                SalesAttachment.objects.create(
                    header=header,
                    file=file_obj,
                    original_name=getattr(file_obj, "name", "")[:255] or None,
                    content_type=(getattr(file_obj, "content_type", "") or "")[:100] or None,
                    uploaded_by=request.user,
                )
            )
        payload = SalesAttachmentSerializer(created, many=True).data
        return Response({"message": "Attachments uploaded.", "data": payload}, status=status.HTTP_201_CREATED)


class SalesInvoiceAttachmentDeleteAPIView(SalesAttachmentBaseAPIView):
    def delete(self, request, pk: int, attachment_id: int):
        header = self._scoped_header(request, pk)
        attachment = get_object_or_404(SalesAttachment.objects.filter(header=header), pk=attachment_id)
        try:
            attachment.file.delete(save=False)
        except Exception:
            pass
        attachment.delete()
        return Response({"message": "Attachment deleted."}, status=status.HTTP_200_OK)


class SalesInvoiceAttachmentDownloadAPIView(SalesAttachmentBaseAPIView):
    parser_classes = []

    def get(self, request, pk: int, attachment_id: int):
        header = self._scoped_header(request, pk)
        attachment = get_object_or_404(SalesAttachment.objects.filter(header=header), pk=attachment_id)
        if not attachment.file:
            raise ValidationError({"detail": "Attachment file is missing."})
        filename = attachment.original_name or attachment.file.name.split("/")[-1]
        content_type = attachment.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        response = FileResponse(attachment.file.open("rb"), content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
