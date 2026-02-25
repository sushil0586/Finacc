from __future__ import annotations

from rest_framework.views import APIView
from rest_framework.response import Response

from sales.models import SalesSettings
from sales.services.sales_invoice_service import SalesInvoiceService

# Adjust to your actual service path
from sales.services.sales_settings_service import SalesSettingsService




class SalesSettingsAPIView(APIView):
    def get(self, request):
        entity_id = int(request.query_params.get("entity_id"))
        subentity_id = request.query_params.get("subentity_id")
        subentity_id = int(subentity_id) if subentity_id else None
        entityfinid_id = int(request.query_params.get("entityfinid"))

        settings_obj = SalesInvoiceService.get_settings(entity_id, subentity_id)

        # preview doc numbers (same idea as Purchase)
        # doc_key examples depend on your DocumentType lookup; keep consistent with Purchase pattern.
        current_doc_numbers = {
        "invoice": SalesSettingsService.get_current_doc_no(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            doc_key="sales_invoice",      # must match DocumentType.doc_key
            doc_code=settings_obj.default_doc_code_invoice,
        ),
        "credit_note": SalesSettingsService.get_current_doc_no(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            doc_key="sales_credit_note",
            doc_code=settings_obj.default_doc_code_cn,
        ),
        "debit_note": SalesSettingsService.get_current_doc_no(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            doc_key="sales_debit_note",
            doc_code=settings_obj.default_doc_code_dn,
        ),
        }

        payload = {
            "settings": {
                "default_doc_code_invoice": settings_obj.default_doc_code_invoice,
                "default_doc_code_cn": settings_obj.default_doc_code_cn,
                "default_doc_code_dn": settings_obj.default_doc_code_dn,
                "default_workflow_action": settings_obj.default_workflow_action,
                "auto_derive_tax_regime": settings_obj.auto_derive_tax_regime,
                "allow_mixed_taxability_in_one_invoice": settings_obj.allow_mixed_taxability_in_one_invoice,
                "enable_einvoice": settings_obj.enable_einvoice,
                "enable_eway": settings_obj.enable_eway,
                "auto_generate_einvoice_on_confirm": settings_obj.auto_generate_einvoice_on_confirm,
                "auto_generate_einvoice_on_post": settings_obj.auto_generate_einvoice_on_post,
                "auto_generate_eway_on_confirm": settings_obj.auto_generate_eway_on_confirm,
                "auto_generate_eway_on_post": settings_obj.auto_generate_eway_on_post,
                "prefer_irp_generate_einvoice_and_eway_together": settings_obj.prefer_irp_generate_einvoice_and_eway_together,
                "enable_round_off": settings_obj.enable_round_off,
                "round_grand_total_to": settings_obj.round_grand_total_to,
            },
            "current_doc_numbers": current_doc_numbers,
        }
        return Response(payload)
