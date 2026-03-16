from __future__ import annotations

from django.utils import timezone

from entity.models import EntityFinancialYear, SubEntity

from reports.gstr1.conf import b2cl_threshold, export_pos_code, enable_gstin_checksum
from reports.gstr1.services.classification import ALL_SECTIONS
from sales.models import SalesInvoiceHeader


def build_gstr1_report_meta(*, entity_id: int, entityfinid_id: int | None = None, subentity_id: int | None = None) -> dict:
    financial_years = list(
        EntityFinancialYear.objects.filter(entity_id=entity_id, isactive=True)
        .order_by("-finstartyear")
        .values("id", "desc", "finstartyear", "finendyear")
    )
    subentities = list(
        SubEntity.objects.filter(entity_id=entity_id, isactive=True)
        .order_by("-ismainentity", "subentityname", "id")
        .values("id", "subentityname", "ismainentity")
    )
    return {
        "entity_id": entity_id,
        "entityfinid_id": entityfinid_id,
        "subentity_id": subentity_id,
        "generated_at": timezone.now().isoformat(),
        "supported_sections": [{"code": section.code, "label": section.label} for section in ALL_SECTIONS],
        "supported_exports": ["json", "csv", "xlsx"],
        "thresholds": {
            "b2cl_invoice_value": str(b2cl_threshold()),
        },
        "filters": [
            {"code": "entity", "label": "Entity", "type": "integer", "required": True},
            {"code": "entityfinid", "label": "Financial Year", "type": "integer", "required": False},
            {"code": "subentity", "label": "Subentity", "type": "integer", "required": False},
            {"code": "from_date", "label": "From Date", "type": "date", "required": False},
            {"code": "to_date", "label": "To Date", "type": "date", "required": False},
            {"code": "month", "label": "Month", "type": "integer", "required": False},
            {"code": "year", "label": "Year", "type": "integer", "required": False},
            {"code": "include_cancelled", "label": "Include Cancelled", "type": "boolean", "required": False},
            {"code": "section", "label": "Section", "type": "string", "required": False},
        ],
        "choices": {
            "taxability": [{"value": choice.value, "label": choice.label} for choice in SalesInvoiceHeader.Taxability],
            "tax_regime": [{"value": choice.value, "label": choice.label} for choice in SalesInvoiceHeader.TaxRegime],
            "supply_category": [
                {"value": choice.value, "label": choice.label} for choice in SalesInvoiceHeader.SupplyCategory
            ],
            "doc_type": [{"value": choice.value, "label": choice.label} for choice in SalesInvoiceHeader.DocType],
            "status": [{"value": choice.value, "label": choice.label} for choice in SalesInvoiceHeader.Status],
            "export": [
                {"value": "json", "label": "JSON"},
                {"value": "csv", "label": "CSV"},
                {"value": "xlsx", "label": "Excel"},
            ],
            "date_presets": [],
        },
        "financial_years": financial_years,
        "subentities": subentities,
        "endpoints": {
            "summary": "/api/reports/gstr1/summary/",
            "section": "/api/reports/gstr1/section/<section_name>/",
            "validations": "/api/reports/gstr1/validations/",
            "export": "/api/reports/gstr1/export/",
            "invoice": "/api/reports/gstr1/invoice/<id>/",
        },
        "actions": {
            "can_view": True,
            "can_export_csv": True,
            "can_export_excel": True,
        },
        "flags": {
            "supports_reverse_charge": True,
            "supports_nil_exempt_summary": True,
            "supports_exports": True,
            "supports_sez": True,
            "supports_deemed_export": True,
        },
        "config": {
            "export_pos_code": export_pos_code(),
            "gstin_checksum_enabled": enable_gstin_checksum(),
        },
    }
