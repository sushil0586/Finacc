from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from purchase.services.purchase_settings_service import PurchaseSettingsService


class PurchaseSettingsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        entity_id = int(request.query_params.get("entity"))
        subentity_id = request.query_params.get("subentity")
        subentity_id = int(subentity_id) if subentity_id not in (None, "", "null") else None
        entityfinid_id = int(request.query_params.get("entityfinid"))

        settings = PurchaseSettingsService.get_settings(entity_id, subentity_id)
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
            },
            # "choice_overrides": overrides,
            "current_doc_numbers": {
                "invoice": invoice_current,
                "credit_note": cn_current,
                "debit_note": dn_current,
            }   
        })
