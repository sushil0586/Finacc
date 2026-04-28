from __future__ import annotations

from django.conf import settings
from django.utils import timezone

from entity.models import EntityFinancialYear, SubEntity


PHASE0_TABLE_CATALOG = [
    {"code": "TABLE_4", "label": "Supplies on Which Tax is Payable"},
    {"code": "TABLE_5", "label": "Supplies on Which Tax is Not Payable"},
    {"code": "TABLE_6", "label": "Input Tax Credit Availed"},
    {"code": "TABLE_7", "label": "ITC Reversed and Ineligible"},
    {"code": "TABLE_8", "label": "ITC Reconciliation"},
    {"code": "TABLE_9", "label": "Tax Paid and Payable"},
    {"code": "TABLE_10_14", "label": "Amendments and Adjustments"},
    {"code": "TABLE_15_19", "label": "Demands, Refunds and HSN"},
]


def build_gstr9_phase0_meta(*, entity_id: int, entityfinid_id: int | None = None, subentity_id: int | None = None) -> dict:
    financial_years = list(
        EntityFinancialYear.objects.filter(entity_id=entity_id, isactive=True)
        .order_by("-finstartyear")
        .values("id", "desc", "finstartyear", "finendyear")
    )
    subentities = list(
        SubEntity.objects.filter(entity_id=entity_id, isactive=True)
        .order_by("-is_head_office", "subentityname", "id")
        .values("id", "subentityname", "is_head_office")
    )
    for row in subentities:
        row["ismainentity"] = row["is_head_office"]

    return {
        "report_code": "gstr9",
        "report_name": "GSTR-9 Annual Return",
        "phase": 0,
        "phase_name": "Scope Lock",
        "generated_at": timezone.now().isoformat(),
        "entity_id": entity_id,
        "entityfinid_id": entityfinid_id,
        "subentity_id": subentity_id,
        "supported_exports": ["json"],
        "scope": {
            "required_filters": ["entity"],
            "optional_filters": ["entityfinid", "subentity"],
            "future_filters": ["as_of_date", "include_adjustments", "include_cancelled"],
        },
        "tables": PHASE0_TABLE_CATALOG,
        "filing": {
            "status": "phase1_prepared",
            "note": "Filing prep contracts are available with freeze-version based prepare/submit/status APIs.",
            "provider": str(getattr(settings, "GSTR9_FILING_PROVIDER", "simulated") or "simulated"),
        },
        "endpoints": {
            "meta": "/api/reports/gstr9/meta/",
            "summary": "/api/reports/gstr9/summary/",
            "table": "/api/reports/gstr9/table/<table_code>/",
            "validations": "/api/reports/gstr9/validations/",
            "export": "/api/reports/gstr9/export/",
            "freeze": "/api/reports/gstr9/freeze/",
            "freeze_history": "/api/reports/gstr9/freeze/history/",
            "filing_prepare": "/api/reports/gstr9/filing/prepare/",
            "filing_submit": "/api/reports/gstr9/filing/submit/",
            "filing_status": "/api/reports/gstr9/filing/status/",
        },
        "financial_years": financial_years,
        "subentities": subentities,
    }
