from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from payments.services.payment_settings_service import PaymentSettingsService


class PaymentSettingsAPIView(APIView):
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

        settings = PaymentSettingsService.get_settings(entity_id, subentity_id)
        policy = PaymentSettingsService.get_policy(entity_id, subentity_id)
        payment_current = PaymentSettingsService.get_current_doc_no(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            doc_key="PAYMENT_VOUCHER",
            doc_code=settings.default_doc_code_payment,
        )

        return Response({
            "settings": {
                "entity": settings.entity_id,
                "subentity": settings.subentity_id,
                "default_doc_code_payment": settings.default_doc_code_payment,
                "default_workflow_action": settings.default_workflow_action,
                "policy_controls": policy.controls,
            },
            "current_doc_numbers": {
                "payment_voucher": payment_current,
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
            updated = PaymentSettingsService.upsert_settings(
                entity_id=entity_id,
                subentity_id=subentity_id,
                updates=dict(request.data or {}),
            )
        except ValueError as e:
            raise ValidationError({"detail": str(e)})

        policy = PaymentSettingsService.get_policy(entity_id, subentity_id)
        return Response({
            "message": "Payment settings updated.",
            "settings": {
                "entity": updated.entity_id,
                "subentity": updated.subentity_id,
                "default_doc_code_payment": updated.default_doc_code_payment,
                "default_workflow_action": updated.default_workflow_action,
                "policy_controls": policy.controls,
            },
        })
