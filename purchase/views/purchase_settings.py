from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError

from purchase.services.purchase_settings_service import PurchaseSettingsService


class PurchaseSettingsAPIView(APIView):
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

        settings = PurchaseSettingsService.get_settings(entity_id, subentity_id)
        policy = PurchaseSettingsService.get_policy(entity_id, subentity_id)
        overrides = PurchaseSettingsService.get_choice_overrides(entity_id, subentity_id)
        invoice_current = PurchaseSettingsService.get_current_doc_no(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            doc_key="PURCHASE_TAX_INVOICE",          # ✅ align with your DocumentType.doc_key
            doc_code=settings.default_doc_code_invoice,
        )

        cn_current = PurchaseSettingsService.get_current_doc_no(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            doc_key="PURCHASE_CREDIT_NOTE",          # ✅ align with your DocumentType.doc_key
            doc_code=settings.default_doc_code_cn,
        )

        dn_current = PurchaseSettingsService.get_current_doc_no(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            doc_key="PURCHASE_DEBIT_NOTE",           # ✅ align with your DocumentType.doc_key
            doc_code=settings.default_doc_code_dn,
        )

        return Response({
            "settings": {
                "entity": settings.entity_id,
                "subentity": settings.subentity_id,
                "default_doc_code_invoice": settings.default_doc_code_invoice,
                "default_doc_code_cn": settings.default_doc_code_cn,
                "default_doc_code_dn": settings.default_doc_code_dn,
                "default_workflow_action": settings.default_workflow_action,
                "auto_derive_tax_regime": settings.auto_derive_tax_regime,
                "enforce_2b_before_itc_claim": settings.enforce_2b_before_itc_claim,
                "allow_mixed_taxability_in_one_bill": settings.allow_mixed_taxability_in_one_bill,
                "round_grand_total_to": settings.round_grand_total_to,
                "enable_round_off": settings.enable_round_off,
                "post_gst_tds_on_invoice": getattr(settings, "post_gst_tds_on_invoice", False),
                "policy_controls": policy.controls,
            },
            # "choice_overrides": overrides,
            "current_doc_numbers": {
                "invoice": invoice_current,
                "credit_note": cn_current,
                "debit_note": dn_current,
            }   
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
            updated = PurchaseSettingsService.upsert_settings(
                entity_id=entity_id,
                subentity_id=subentity_id,
                updates=dict(request.data or {}),
            )
        except ValueError as e:
            raise ValidationError({"detail": str(e)})

        policy = PurchaseSettingsService.get_policy(entity_id, subentity_id)
        return Response({
            "message": "Purchase settings updated.",
            "settings": {
                "entity": updated.entity_id,
                "subentity": updated.subentity_id,
                "default_doc_code_invoice": updated.default_doc_code_invoice,
                "default_doc_code_cn": updated.default_doc_code_cn,
                "default_doc_code_dn": updated.default_doc_code_dn,
                "default_workflow_action": updated.default_workflow_action,
                "auto_derive_tax_regime": updated.auto_derive_tax_regime,
                "enforce_2b_before_itc_claim": updated.enforce_2b_before_itc_claim,
                "allow_mixed_taxability_in_one_bill": updated.allow_mixed_taxability_in_one_bill,
                "round_grand_total_to": updated.round_grand_total_to,
                "enable_round_off": updated.enable_round_off,
                "post_gst_tds_on_invoice": updated.post_gst_tds_on_invoice,
                "policy_controls": policy.controls,
            },
        })
