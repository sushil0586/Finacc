from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from vouchers.models.voucher_core import VoucherHeader
from vouchers.services.voucher_settings_service import VoucherSettingsService


class VoucherSettingsAPIView(APIView):
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

    def _settings_payload(self, settings, policy):
        return {
            "entity": settings.entity_id,
            "subentity": settings.subentity_id,
            "default_doc_code_cash": settings.default_doc_code_cash,
            "default_doc_code_bank": settings.default_doc_code_bank,
            "default_doc_code_journal": settings.default_doc_code_journal,
            "default_workflow_action": settings.default_workflow_action,
            "policy_controls": policy.controls,
        }

    def get(self, request):
        entity_id = self._parse_int_param(request, "entity", required=True)
        entityfinid_id = self._parse_int_param(request, "entityfinid", required=True)
        sub_raw = request.query_params.get("subentity")
        subentity_id = None if sub_raw in (None, "", "null") else int(sub_raw)
        settings = VoucherSettingsService.get_settings(entity_id, subentity_id)
        policy = VoucherSettingsService.get_policy(entity_id, subentity_id)
        current_numbers = {
            "cash": VoucherSettingsService.current_doc_no_for_type(entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id, voucher_type=VoucherHeader.VoucherType.CASH),
            "bank": VoucherSettingsService.current_doc_no_for_type(entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id, voucher_type=VoucherHeader.VoucherType.BANK),
            "journal": VoucherSettingsService.current_doc_no_for_type(entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id, voucher_type=VoucherHeader.VoucherType.JOURNAL),
        }
        return Response({"settings": self._settings_payload(settings, policy), "current_doc_numbers": current_numbers})

    def patch(self, request):
        entity_id = self._parse_int_param(request, "entity", required=True)
        sub_raw = request.query_params.get("subentity")
        subentity_id = None if sub_raw in (None, "", "null") else int(sub_raw)
        try:
            updated = VoucherSettingsService.upsert_settings(entity_id=entity_id, subentity_id=subentity_id, updates=dict(request.data or {}))
        except ValueError as e:
            raise ValidationError({"detail": str(e)})
        policy = VoucherSettingsService.get_policy(entity_id, subentity_id)
        return Response({"message": "Voucher settings updated.", "settings": self._settings_payload(updated, policy)})


class VoucherCompiledChoicesAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            "VoucherType": [{"value": x, "label": y} for x, y in VoucherHeader.VoucherType.choices],
            "Status": [{"value": x, "label": y} for x, y in VoucherHeader.Status.choices],
            "EntryType": [
                {"value": "DR", "label": "Debit"},
                {"value": "CR", "label": "Credit"},
            ],
            "SystemLineRole": [{"value": x, "label": y} for x, y in VoucherLineRoleChoices()],
        })


def VoucherLineRoleChoices():
    from vouchers.models.voucher_core import VoucherLine
    return VoucherLine.SystemLineRole.choices
