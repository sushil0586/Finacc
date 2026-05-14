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

ADVISORY_RECONCILIATION_CODES = {
    "INTERSTATE_DISCLOSURE",
    "NON_GST_ONLY",
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


def _clean_scope_params(scope_params: dict | None) -> dict:
    params = {}
    for key in ("entityfinid", "subentity", "from_date", "to_date"):
        value = (scope_params or {}).get(key)
        if value not in (None, ""):
            params[key] = value
    return params


def _build_gstr1_report_drilldown(scope_params: dict | None, code: str, severity: str) -> dict:
    params = _clean_scope_params(scope_params)
    params["warning_code"] = code
    params["warning_severity"] = severity
    return {
        "target": "gstr1_readiness",
        "label": "Open GSTR-1 workspace",
        "kind": "report",
        "route": "/gstreport",
        "params": params,
    }


def _build_gstr3b_report_drilldown(scope_params: dict | None, warning: dict) -> dict:
    params = _clean_scope_params(scope_params)
    section = warning.get("drilldowns", {}).get("section_view", {}).get("params", {}).get("section")
    if section:
        params["section"] = section
    params["warning_code"] = str(warning.get("code") or "")
    return {
        "target": "gstr3b_summary",
        "label": "Open GSTR-3B workspace",
        "kind": "report",
        "route": "/gstr3breport",
        "params": params,
    }


def _build_reconciliation_report_drilldown(scope_params: dict | None, row: dict) -> dict:
    params = _clean_scope_params(scope_params)
    params["recon_code"] = row.get("code")
    return {
        "target": "gstr1_gstr3b_reconciliation",
        "label": "Open reconciliation workspace",
        "kind": "report",
        "route": "/reports/compliance/gstr1-vs-gstr3b",
        "params": params,
    }


def _is_advisory_reconciliation_row(row: dict) -> bool:
    return str(row.get("code") or "").upper() in ADVISORY_RECONCILIATION_CODES


def _same_reconciliation_signature(left: dict, right: dict) -> bool:
    comparable_fields = (
        "difference_taxable_value",
        "difference_total_tax",
        "gstr1_taxable_value",
        "gstr3b_taxable_value",
        "gstr1_total_tax",
        "gstr3b_total_tax",
    )
    return all(_safe_decimal(left.get(field)) == _safe_decimal(right.get(field)) for field in comparable_fields)


def _dedupe_actionable_reconciliation_rows(rows: list[dict]) -> list[dict]:
    actionable_rows = list(rows or [])
    outward_taxable = next((row for row in actionable_rows if str(row.get("code") or "").upper() == "OUTWARD_TAXABLE"), None)
    zero_rated = next((row for row in actionable_rows if str(row.get("code") or "").upper() == "ZERO_RATED"), None)

    deduped_rows = []
    for row in actionable_rows:
        code = str(row.get("code") or "").upper()
        if code == "TOTAL_OUTWARD_TAX" and outward_taxable and _same_reconciliation_signature(row, outward_taxable):
            if not zero_rated or str(zero_rated.get("status") or "").lower() == "matched":
                continue
        deduped_rows.append(row)
    return deduped_rows


def _build_reconciliation_explanation(row: dict) -> str:
    return (
        f"GSTR-1 taxable {row.get('gstr1_taxable_value')} vs GSTR-3B taxable {row.get('gstr3b_taxable_value')}; "
        f"GSTR-1 tax {row.get('gstr1_total_tax')} vs GSTR-3B tax {row.get('gstr3b_total_tax')}."
    )


def _gstr3b_review_playbook(warning: dict) -> dict:
    code = str(warning.get("code") or "").upper()
    if code == "GSTR3B_TAX_BREAKUP_MISSING":
        return {
            "review_title": "Complete GSTR-3B tax breakup",
            "review_steps": [
                "Open the GSTR-3B workspace section from the action button.",
                "Validate CGST, SGST, IGST, and cess totals against source invoices.",
                "Recompute or refresh section totals before filing export.",
            ],
        }
    if code in {"GSTR3B_POS_MISSING", "MISSING_PLACE_OF_SUPPLY", "INVALID_PLACE_OF_SUPPLY"}:
        return {
            "review_title": "Review place-of-supply and section mapping",
            "review_steps": [
                "Verify place-of-supply on impacted source documents.",
                "Confirm interstate/intrastate treatment aligns with tax regime.",
                "Re-run validations after corrections.",
            ],
        }
    return {
        "review_title": "Review GSTR-3B exception details",
        "review_steps": [
            "Open the linked GSTR-3B workspace for this warning.",
            "Verify section values against source postings.",
            "Resolve and rerun validations before filing.",
        ],
    }


def _reconciliation_review_playbook(row: dict) -> dict:
    code = str(row.get("code") or "").upper()
    if code == "OUTWARD_TAXABLE":
        return {
            "review_title": "Recheck GSTR-3B outward taxable bucket mapping",
            "review_steps": [
                "Open the reconciliation workspace and compare the same period scope.",
                "Verify taxable base for posted sales invoices, debit notes, and credit notes.",
                "Confirm export/zero-rated and nil/non-GST treatment is not leaking into taxable bucket.",
            ],
        }
    if code == "TOTAL_OUTWARD_TAX":
        return {
            "review_title": "Validate aggregate outward tax roll-up",
            "review_steps": [
                "This is an aggregate check, so single-row source drilldowns can be misleading.",
                "Compare total GST tax from posted outward documents against GSTR-3B 3.1 tax roll-up.",
                "Use the reconciliation workspace to inspect contributors before filing.",
            ],
        }
    if code == "ZERO_RATED":
        return {
            "review_title": "Verify zero-rated classification",
            "review_steps": [
                "Confirm only true zero-rated/export supplies are included in zero-rated base.",
                "Check that deemed export and SEZ adjustments are mapped to the intended return buckets.",
            ],
        }
    return {
        "review_title": "Review reconciliation contributors",
        "review_steps": [
            "Open reconciliation workspace to inspect the contributor rows for this check.",
            "Confirm the same date/entity/subentity scope is used in both returns.",
            "Resolve mapping or posting differences and rerun reconciliation.",
        ],
    }


def build_gst_exception_dashboard(*, gstr1_warnings: list[dict], gstr3b_warnings: list[dict], reconciliation_payload: dict, scope_params: dict | None = None) -> dict:
    gstr1_warnings = list(gstr1_warnings or [])
    gstr3b_warnings = list(gstr3b_warnings or [])
    raw_reconciliation_rows = [row for row in (reconciliation_payload.get("rows") or []) if row.get("status") == "mismatch"]
    reconciliation_warnings = list(reconciliation_payload.get("warnings") or [])
    actionable_reconciliation_rows = _dedupe_actionable_reconciliation_rows(
        [row for row in raw_reconciliation_rows if not _is_advisory_reconciliation_row(row)]
    )
    advisory_reconciliation_rows = [row for row in raw_reconciliation_rows if _is_advisory_reconciliation_row(row)]

    category_counts = Counter()
    for warning in gstr1_warnings + gstr3b_warnings:
        category_counts[_category_for_code(warning.get("code", ""))] += 1
    if actionable_reconciliation_rows:
        category_counts["Reconciliation Gaps"] += len(actionable_reconciliation_rows)
    if advisory_reconciliation_rows:
        category_counts["Reconciliation Advisories"] += len(advisory_reconciliation_rows)

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
            "total": len(actionable_reconciliation_rows),
            "errors": len(actionable_reconciliation_rows),
            "warnings": 0,
            "infos": len(reconciliation_warnings) + len(advisory_reconciliation_rows),
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
        payload = {
            "code": code,
            "severity": severity_label,
            "category": _category_for_code(code),
            "affected_rows": count,
            "sample_references": ", ".join([ref for ref in sample_refs if ref]) or "-",
            "message": rows[0].get("message") if rows else "",
            "drilldowns": {
                "report": _build_gstr1_report_drilldown(scope_params, code, severity_label),
            },
        }
        if len(rows) == 1:
            row_drilldowns = rows[0].get("drilldowns") or {}
            if row_drilldowns.get("source_document"):
                payload["drilldowns"]["source_document"] = row_drilldowns["source_document"]
            if row_drilldowns.get("posting_lookup"):
                payload["drilldowns"]["posting_lookup"] = row_drilldowns["posting_lookup"]
        gstr1_spotlight.append(payload)

    gstr3b_spotlight = [
        {
            "code": str(warning.get("code") or ""),
            "severity": str(warning.get("severity") or "info"),
            "category": _category_for_code(str(warning.get("code") or "")),
            "affected_rows": 1,
            "sample_references": "-",
            "message": str(warning.get("message") or ""),
            **_gstr3b_review_playbook(warning),
            "drilldowns": {
                "report": _build_gstr3b_report_drilldown(scope_params, warning),
            },
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
            "gstr1_taxable_value": row.get("gstr1_taxable_value"),
            "gstr3b_taxable_value": row.get("gstr3b_taxable_value"),
            "gstr1_total_tax": row.get("gstr1_total_tax"),
            "gstr3b_total_tax": row.get("gstr3b_total_tax"),
            "explanation": _build_reconciliation_explanation(row),
            **_reconciliation_review_playbook(row),
            "drilldowns": {
                "report": _build_reconciliation_report_drilldown(scope_params, row),
            },
        }
        for row in actionable_reconciliation_rows
    ]

    advisory_rows = [
        {
            "code": row.get("code"),
            "severity": "info",
            "message": f"{row.get('label')}: {_build_reconciliation_explanation(row)}",
        }
        for row in advisory_reconciliation_rows
    ]

    category_spotlight = [
        {"category": category, "count": count}
        for category, count in category_counts.most_common()
    ]

    blocking_count = (
        sum(1 for warning in gstr1_warnings if _severity_rank(str(warning.get("severity") or "")) >= 2)
        + sum(1 for warning in gstr3b_warnings if _severity_rank(str(warning.get("severity") or "")) >= 2)
        + len(actionable_reconciliation_rows)
    )

    return {
        "overview": {
            "total_exception_count": len(gstr1_warnings) + len(gstr3b_warnings) + len(actionable_reconciliation_rows),
            "blocking_exception_count": blocking_count,
            "gstr1_warning_count": len(gstr1_warnings),
            "gstr3b_warning_count": len(gstr3b_warnings),
            "reconciliation_mismatch_count": len(actionable_reconciliation_rows),
            "reconciliation_advisory_count": len(advisory_reconciliation_rows),
            "max_reconciliation_tax_gap": max((abs(_safe_decimal(row.get("difference_total_tax"))) for row in actionable_reconciliation_rows), default=Decimal("0.00")),
        },
        "source_summary": source_summary,
        "category_spotlight": category_spotlight,
        "gstr1_exception_rows": gstr1_spotlight,
        "gstr3b_exception_rows": gstr3b_spotlight,
        "reconciliation_rows": mismatch_rows,
        "warnings": reconciliation_warnings + advisory_rows,
    }
