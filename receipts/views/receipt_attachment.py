from __future__ import annotations

import mimetypes
from typing import List

from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from receipts.models import ReceiptVoucherAttachment, ReceiptVoucherHeader
from receipts.serializers.receipt_attachment import ReceiptVoucherAttachmentSerializer


class ReceiptVoucherAttachmentBaseAPIView(APIView):
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

    def _scoped_header(self, request, pk: int) -> ReceiptVoucherHeader:
        entity_id, entityfinid_id, subentity_id = self._scope_ids(request)
        qs = ReceiptVoucherHeader.objects.filter(entity_id=entity_id, entityfinid_id=entityfinid_id)
        if subentity_id is None:
            qs = qs.filter(subentity__isnull=True)
        else:
            qs = qs.filter(subentity_id=subentity_id)
        return get_object_or_404(qs, pk=pk)

    def _validate_files(self, files: List) -> None:
        max_size = 15 * 1024 * 1024
        allowed_prefixes = ("application/pdf", "image/", "text/")
        allowed_suffixes = (".pdf", ".png", ".jpg", ".jpeg", ".webp", ".txt", ".csv", ".xls", ".xlsx")
        for file_obj in files:
            if not file_obj:
                continue
            if getattr(file_obj, "size", 0) > max_size:
                raise ValidationError({"detail": f"{file_obj.name} exceeds the 15 MB attachment limit."})
            content_type = str(getattr(file_obj, "content_type", "") or "").lower()
            name = str(getattr(file_obj, "name", "") or "").lower()
            if content_type:
                if not any(content_type.startswith(prefix) for prefix in allowed_prefixes):
                    raise ValidationError({"detail": f"{file_obj.name} has unsupported content type {content_type}."})
            elif not name.endswith(allowed_suffixes):
                raise ValidationError({"detail": f"{file_obj.name} has unsupported file type."})


class ReceiptVoucherAttachmentListCreateAPIView(ReceiptVoucherAttachmentBaseAPIView):
    def get(self, request, pk: int):
        header = self._scoped_header(request, pk)
        rows = header.attachments.order_by("-created_at", "-id")
        return Response(ReceiptVoucherAttachmentSerializer(rows, many=True).data)

    def post(self, request, pk: int):
        header = self._scoped_header(request, pk)
        files = request.FILES.getlist("attachments") or request.FILES.getlist("file")
        if not files:
            raise ValidationError({"detail": "At least one attachment file is required."})
        self._validate_files(files)
        created = []
        for file_obj in files:
            created.append(
                ReceiptVoucherAttachment.objects.create(
                    receipt_voucher=header,
                    file=file_obj,
                    original_name=getattr(file_obj, "name", "")[:255] or None,
                    content_type=(getattr(file_obj, "content_type", "") or "")[:100] or None,
                    uploaded_by=request.user,
                )
            )
        return Response(
            {
                "message": "Attachments uploaded.",
                "data": ReceiptVoucherAttachmentSerializer(created, many=True).data,
            },
            status=status.HTTP_201_CREATED,
        )


class ReceiptVoucherAttachmentDeleteAPIView(ReceiptVoucherAttachmentBaseAPIView):
    def delete(self, request, pk: int, attachment_id: int):
        header = self._scoped_header(request, pk)
        attachment = get_object_or_404(ReceiptVoucherAttachment.objects.filter(receipt_voucher=header), pk=attachment_id)
        try:
            attachment.file.delete(save=False)
        except Exception:
            pass
        attachment.delete()
        return Response({"message": "Attachment deleted."}, status=status.HTTP_200_OK)


class ReceiptVoucherAttachmentDownloadAPIView(ReceiptVoucherAttachmentBaseAPIView):
    parser_classes = []

    def get(self, request, pk: int, attachment_id: int):
        header = self._scoped_header(request, pk)
        attachment = get_object_or_404(ReceiptVoucherAttachment.objects.filter(receipt_voucher=header), pk=attachment_id)
        if not attachment.file:
            raise ValidationError({"detail": "Attachment file is missing."})
        filename = attachment.original_name or attachment.file.name.split("/")[-1]
        content_type = attachment.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        response = FileResponse(attachment.file.open("rb"), content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
