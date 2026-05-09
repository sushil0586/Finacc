from __future__ import annotations

from collections import Counter
from decimal import Decimal


MASTER_DATA_CODES = {
    "INVALID_GSTIN",
    "INVALID_SELLER_GSTIN",
    "B2B_GSTIN_REQUIRED",
    "MISSING_HSN",
}

POS_REGIME_CODES = {
    "MISSING_PLACE_OF_SUPPLY",
    "INVALID_PLACE_OF_SUPPLY",
    "POS_TAX_REGIME_MISMATCH",
    "EXPORT_POS_INVALID",
}

TAX_CALCULATION_CODES = {
    "NIL_EXEMPT_TAX_PRESENT",
    "IGST_ON_INTRASTATE",
    "CGST_SGST_ON_INTERSTATE",
    "INVOICE_TOTAL_MISMATCH",
    "NON_POSITIVE_TAXABLE",
    "NON_POSITIVE_TOTAL",
    "CANCELLED_HAS_AMOUNTS",
    "TAXABLE_MISMATCH",
    "CGST_MISMATCH",
    "SGST_MISMATCH",
    "IGST_MISMATCH",
    "CESS_MISMATCH",
    "GSTR3B_TAX_BREAKUP_MISSING",
}

DOCUMENT_LINKAGE_CODES = {
    "DUPLICATE_INVOICE",
    "TABLE11_ORPHAN_ADJUSTMENT",
    "TABLE11_ADJUSTMENT_EXCEEDS_SOURCE",
    "TABLE11_DUPLICATE_ADJUSTMENT",
    "NOTE_LINK_MISSING",
    "NOTE_LINK_INVALID",
    "NOTE_LINK_SCOPE_MISMATCH",
    "NOTE_LINK_DOC_TYPE",
}

READINESS_CODES = {
    "GSTR3B_POS_MISSING",
    "GSTR3B_CASH_TAX_SOURCE_PENDING",
}


def _category_for_code(code: str) -> str:
    code = str(code or "").upper()
    if code in MASTER_DATA_CODES:
        return "Master Data & Registration"
    if code in POS_REGIME_CODES:
        return "Place of Supply & Tax Regime"
    if code in TAX_CALCULATION_CODES:
        return "Tax Calculation & Totals"
    if code in DOCUMENT_LINKAGE_CODES:
        return "Document Linkage & Adjustments"
    if code in READINESS_CODES:
        return "Return Readiness"
    return "Other Compliance Checks"


def _severity_rank(severity: str) -> int:
    severity = str(severity or "").lower()
    return {"error": 3, "warning": 2, "info": 1}.get(severity, 0)


def _safe_decimal(value) -> Decimal:
    if value in (None, ""):
        return Decimal("0.00")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def build_gst_exception_dashboard(*, gstr1_warnings: list[dict], gstr3b_warnings: list[dict], reconciliation_payload: dict) -> dict:
    gstr1_warnings = list(gstr1_warnings or [])
    gstr3b_warnings = list(gstr3b_warnings or [])
    reconciliation_rows = [row for row in (reconciliation_payload.get("rows") or []) if row.get("status") == "mismatch"]
    reconciliation_warnings = list(reconciliation_payload.get("warnings") or [])

    category_counts = Counter()
    for warning in gstr1_warnings + gstr3b_warnings:
        category_counts[_category_for_code(warning.get("code", ""))] += 1
    if reconciliation_rows:
        category_counts["Reconciliation Gaps"] += len(reconciliation_rows)

    source_summary = [
        {
            "source": "GSTR-1",
            "total": len(gstr1_warnings),
            "errors": sum(1 for warning in gstr1_warnings if str(warning.get("severity")).lower() == "error"),
            "warnings": sum(1 for warning in gstr1_warnings if str(warning.get("severity")).lower() == "warning"),
            "infos": sum(1 for warning in gstr1_warnings if str(warning.get("severity")).lower() == "info"),
        },
        {
            "source": "GSTR-3B",
            "total": len(gstr3b_warnings),
            "errors": sum(1 for warning in gstr3b_warnings if str(warning.get("severity")).lower() == "error"),
            "warnings": sum(1 for warning in gstr3b_warnings if str(warning.get("severity")).lower() == "warning"),
            "infos": sum(1 for warning in gstr3b_warnings if str(warning.get("severity")).lower() == "info"),
        },
        {
            "source": "Reconciliation",
            "total": len(reconciliation_rows),
            "errors": len(reconciliation_rows),
            "warnings": 0,
            "infos": len(reconciliation_warnings),
        },
    ]

    gstr1_code_counter = Counter(str(warning.get("code") or "") for warning in gstr1_warnings)
    gstr1_spotlight = []
    for code, count in gstr1_code_counter.most_common():
        rows = [warning for warning in gstr1_warnings if str(warning.get("code") or "") == code]
        highest_severity = max((_severity_rank(str(row.get("severity") or "")) for row in rows), default=0)
        severity_label = next((label for label, rank in [("error", 3), ("warning", 2), ("info", 1)] if rank == highest_severity), "info")
        sample_refs = [
            str(row.get("invoice_number") or row.get("invoice_id") or "").strip()
            for row in rows
            if row.get("invoice_number") or row.get("invoice_id")
        ][:3]
        gstr1_spotlight.append(
            {
                "code": code,
                "severity": severity_label,
                "category": _category_for_code(code),
                "affected_rows": count,
                "sample_references": ", ".join([ref for ref in sample_refs if ref]) or "-",
                "message": rows[0].get("message") if rows else "",
            }
        )

    gstr3b_spotlight = [
        {
            "code": str(warning.get("code") or ""),
            "severity": str(warning.get("severity") or "info"),
            "category": _category_for_code(str(warning.get("code") or "")),
            "affected_rows": 1,
            "sample_references": "-",
            "message": str(warning.get("message") or ""),
        }
        for warning in gstr3b_warnings
    ]

    mismatch_rows = [
        {
            "code": row.get("code"),
            "label": row.get("label"),
            "difference_taxable_value": row.get("difference_taxable_value"),
            "difference_total_tax": row.get("difference_total_tax"),
            "note": row.get("note") or "",
        }
        for row in reconciliation_rows
    ]

    category_spotlight = [
        {"category": category, "count": count}
        for category, count in category_counts.most_common()
    ]

    blocking_count = (
        sum(1 for warning in gstr1_warnings if _severity_rank(str(warning.get("severity") or "")) >= 2)
        + sum(1 for warning in gstr3b_warnings if _severity_rank(str(warning.get("severity") or "")) >= 2)
        + len(reconciliation_rows)
    )

    return {
        "overview": {
            "total_exception_count": len(gstr1_warnings) + len(gstr3b_warnings) + len(reconciliation_rows),
            "blocking_exception_count": blocking_count,
            "gstr1_warning_count": len(gstr1_warnings),
            "gstr3b_warning_count": len(gstr3b_warnings),
            "reconciliation_mismatch_count": len(reconciliation_rows),
            "max_reconciliation_tax_gap": max((abs(_safe_decimal(row.get("difference_total_tax"))) for row in reconciliation_rows), default=Decimal("0.00")),
        },
        "source_summary": source_summary,
        "category_spotlight": category_spotlight,
        "gstr1_exception_rows": gstr1_spotlight,
        "gstr3b_exception_rows": gstr3b_spotlight,
        "reconciliation_rows": mismatch_rows,
        "warnings": reconciliation_warnings,
    }
