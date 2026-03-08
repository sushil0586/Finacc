from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from receipts.services.receipt_settings_service import ReceiptSettingsService


class ReceiptSettingsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @staticmethod
    def _parse_int_param(request, key: str, required: bool = True):
        raw = request.query_params.get(key)
        if raw in (None, ""):
            if required:
                raise ValidationError({key: f"{key} query param is required."})
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            raise ValidationError({key: f"{key} must be an integer."})

    def get(self, request):
        entity_id = self._parse_int_param(request, "entity", required=True)
        entityfinid_id = self._parse_int_param(request, "entityfinid", required=True)
        subentity_raw = request.query_params.get("subentity")
        if subentity_raw in (None, "", "null"):
            subentity_id = None
        else:
            try:
                subentity_id = int(subentity_raw)
            except (TypeError, ValueError):
                raise ValidationError({"subentity": "subentity must be an integer."})

        settings = ReceiptSettingsService.get_settings(entity_id, subentity_id)
        policy = ReceiptSettingsService.get_policy(entity_id, subentity_id)
        receipt_current = ReceiptSettingsService.get_current_doc_no(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            doc_key="RECEIPT_VOUCHER",
            doc_code=settings.default_doc_code_receipt,
        )

        return Response({
            "settings": {
                "entity": settings.entity_id,
                "subentity": settings.subentity_id,
                "default_doc_code_receipt": settings.default_doc_code_receipt,
                "default_workflow_action": settings.default_workflow_action,
                "policy_controls": policy.controls,
            },
            "current_doc_numbers": {
                "receipt_voucher": receipt_current,
            },
        })

    def patch(self, request):
        entity_id = self._parse_int_param(request, "entity", required=True)
        subentity_raw = request.query_params.get("subentity")
        if subentity_raw in (None, "", "null"):
            subentity_id = None
        else:
            try:
                subentity_id = int(subentity_raw)
            except (TypeError, ValueError):
                raise ValidationError({"subentity": "subentity must be an integer."})

        try:
            updated = ReceiptSettingsService.upsert_settings(
                entity_id=entity_id,
                subentity_id=subentity_id,
                updates=dict(request.data or {}),
            )
        except ValueError as e:
            raise ValidationError({"detail": str(e)})

        policy = ReceiptSettingsService.get_policy(entity_id, subentity_id)
        return Response({
            "message": "Receipt settings updated.",
            "settings": {
                "entity": updated.entity_id,
                "subentity": updated.subentity_id,
                "default_doc_code_receipt": updated.default_doc_code_receipt,
                "default_workflow_action": updated.default_workflow_action,
                "policy_controls": policy.controls,
            },
        })
