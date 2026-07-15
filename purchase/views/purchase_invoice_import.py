from __future__ import annotations

from rest_framework import permissions
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from helpers.utils.attachment_validation import validate_attachment_uploads
from purchase.services.purchase_invoice_import_service import (
    PurchaseInvoiceImportContext,
    PurchaseInvoiceImportService,
)


class PurchaseInvoiceImportDraftAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        entity = request.query_params.get("entity")
        entityfinid = request.query_params.get("entityfinid")
        subentity = request.query_params.get("subentity")
        line_mode = (request.query_params.get("line_mode") or "goods").strip().lower()

        if not entity or not entityfinid:
            raise ValidationError({"detail": "entity and entityfinid query params are required."})

        try:
            entity_id = int(entity)
            entityfinid_id = int(entityfinid)
            subentity_id = int(subentity) if subentity not in (None, "", "null") else None
        except (TypeError, ValueError):
            raise ValidationError({"detail": "entity/entityfinid/subentity must be integers."})

        upload = request.FILES.get("file")
        if not upload:
            raise ValidationError({"detail": "Invoice file is required."})

        validate_attachment_uploads([upload])
        context = PurchaseInvoiceImportContext(
            entity_id=entity_id,
            entityfinid=entityfinid_id,
            subentity_id=subentity_id,
            line_mode="service" if line_mode == "service" else "goods",
        )
        payload = PurchaseInvoiceImportService.build_import_draft(uploaded_file=upload, context=context)
        return Response(payload)
