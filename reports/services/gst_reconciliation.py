from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from django.db.models import Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from financial.models import Ledger
from posting.models import Entry, EntryStatus, JournalLine
from posting.services.static_accounts import StaticAccountService
from reports.gstr1.selectors.queries import apply_scope_filters, base_queryset
from reports.gstr1.services.classification import Gstr1ClassificationService
from sales.models import SalesInvoiceLine

ZERO = Decimal("0.00")
TOLERANCE = Decimal("0.05")
ADVISORY_CODES = {"INTERSTATE_DISCLOSURE", "NON_GST_ONLY"}
OUTPUT_TAX_LEDGER_CODES = (
    ("OUTPUT_CGST", "cgst", "Output CGST"),
    ("OUTPUT_SGST", "sgst", "Output SGST"),
    ("OUTPUT_IGST", "igst", "Output IGST"),
    ("OUTPUT_CESS", "cess", "Output CESS"),
)


def _q(value) -> Decimal:
    if value in (None, ""):
        return ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _section_map(gstr1_summary: dict) -> dict[str, dict]:
    return {str(row.get("section", "")).upper(): row for row in gstr1_summary.get("sections", [])}


def _nil_exempt_map(gstr1_summary: dict) -> dict[int, dict]:
    return {int(row.get("taxability")): row for row in gstr1_summary.get("nil_exempt_summary", []) if row.get("taxability") is not None}


def _bucket_from_gstr1(row: dict | None) -> dict[str, Decimal]:
    row = row or {}
    cgst = _q(row.get("cgst_amount"))
    sgst = _q(row.get("sgst_amount"))
    igst = _q(row.get("igst_amount"))
    cess = _q(row.get("cess_amount"))
    return {
        "taxable_value": _q(row.get("taxable_amount") or row.get("taxable_value")),
        "cgst": cgst,
        "sgst": sgst,
        "igst": igst,
        "cess": cess,
        "total_tax": cgst + sgst + igst + cess,
    }


def _bucket_from_gstr3b(row: dict | None) -> dict[str, Decimal]:
    row = row or {}
    cgst = _q(row.get("cgst"))
    sgst = _q(row.get("sgst"))
    igst = _q(row.get("igst"))
    cess = _q(row.get("cess"))
    return {
        "taxable_value": _q(row.get("taxable_value")),
        "cgst": cgst,
        "sgst": sgst,
        "igst": igst,
        "cess": cess,
        "total_tax": _q(row.get("total_tax")) or (cgst + sgst + igst + cess),
    }


def _add_bucket(*rows: dict[str, Decimal]) -> dict[str, Decimal]:
    out = {"taxable_value": ZERO, "cgst": ZERO, "sgst": ZERO, "igst": ZERO, "cess": ZERO, "total_tax": ZERO}
    for row in rows:
        for key in out.keys():
            out[key] += _q(row.get(key))
    return out


def _difference_row(*, code: str, label: str, gstr1_row: dict[str, Decimal], gstr3b_row: dict[str, Decimal], note: str | None = None) -> dict:
    taxable_diff = gstr1_row["taxable_value"] - gstr3b_row["taxable_value"]
    cgst_diff = gstr1_row["cgst"] - gstr3b_row["cgst"]
    sgst_diff = gstr1_row["sgst"] - gstr3b_row["sgst"]
    igst_diff = gstr1_row["igst"] - gstr3b_row["igst"]
    cess_diff = gstr1_row["cess"] - gstr3b_row["cess"]
    total_tax_diff = gstr1_row["total_tax"] - gstr3b_row["total_tax"]
    status = "matched"
    if any(abs(value) > TOLERANCE for value in [taxable_diff, cgst_diff, sgst_diff, igst_diff, cess_diff, total_tax_diff]):
        status = "mismatch"
    is_advisory = code in ADVISORY_CODES
    explanation = (
        f"GSTR-1 taxable {gstr1_row['taxable_value']} vs GSTR-3B taxable {gstr3b_row['taxable_value']}; "
        f"GSTR-1 tax {gstr1_row['total_tax']} vs GSTR-3B tax {gstr3b_row['total_tax']}."
    )
    return {
        "code": code,
        "label": label,
        "status": status,
        "is_advisory": is_advisory,
        "mismatch_kind": "advisory" if is_advisory else "actionable",
        "explanation": explanation,
        "note": note,
        "gstr1_taxable_value": gstr1_row["taxable_value"],
        "gstr1_cgst": gstr1_row["cgst"],
        "gstr1_sgst": gstr1_row["sgst"],
        "gstr1_igst": gstr1_row["igst"],
        "gstr1_cess": gstr1_row["cess"],
        "gstr1_total_tax": gstr1_row["total_tax"],
        "gstr3b_taxable_value": gstr3b_row["taxable_value"],
        "gstr3b_cgst": gstr3b_row["cgst"],
        "gstr3b_sgst": gstr3b_row["sgst"],
        "gstr3b_igst": gstr3b_row["igst"],
        "gstr3b_cess": gstr3b_row["cess"],
        "gstr3b_total_tax": gstr3b_row["total_tax"],
        "difference_taxable_value": taxable_diff,
        "difference_cgst": cgst_diff,
        "difference_sgst": sgst_diff,
        "difference_igst": igst_diff,
        "difference_cess": cess_diff,
        "difference_total_tax": total_tax_diff,
    }


def _clean_scope_params(scope_params: dict | None) -> dict:
    params = {}
    for key in ("entityfinid", "subentity", "from_date", "to_date"):
        value = (scope_params or {}).get(key)
        if value not in (None, ""):
            params[key] = value
    return params


def _build_reconciliation_drilldowns(scope_params: dict | None, code: str) -> dict:
    base_params = _clean_scope_params(scope_params)
    base_params["recon_code"] = code
    return {
        "gstr1_workspace": {
            "target": "gstr1_workspace",
            "label": "Open GSTR-1 workspace",
            "kind": "report",
            "route": "/gstreport",
            "params": dict(base_params),
        },
        "gstr3b_workspace": {
            "target": "gstr3b_workspace",
            "label": "Open GSTR-3B workspace",
            "kind": "report",
            "route": "/gstr3breport",
            "params": dict(base_params),
        },
    }


def _build_source_document_drilldown(*, invoice_id: int, has_service_lines: bool | None = None) -> dict:
    route = _resolve_source_document_route(invoice_id=invoice_id, has_service_lines=has_service_lines)
    return {
        "target": "sales_invoice_detail",
        "label": "Open source invoice",
        "kind": "document",
        "route": route,
        "params": {
            "transactionid": int(invoice_id),
        },
    }


def _resolve_source_document_route(*, invoice_id: int, has_service_lines: bool | None = None) -> str:
    if has_service_lines is None:
        has_service_lines = SalesInvoiceLine.objects.filter(header_id=invoice_id, is_service=True).exists()
    return "/saleserviceinvoice" if has_service_lines else "/saleinvoice"


def _normalize_scope_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value in (None, ""):
        return None
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def _build_posting_lookup_drilldown(*, invoice_id: int) -> dict:
    return {
        "target": "posting_detail_lookup",
        "label": "Open posted voucher",
        "kind": "posting_lookup",
        "lookup": {
            "document_type": "sales_invoice",
            "document_id": int(invoice_id),
            "source_module": "sales",
        },
    }


def _outward_taxable_filter():
    return (
        Gstr1ClassificationService.section_filter("B2B")
        | Gstr1ClassificationService.section_filter("B2CL")
        | Gstr1ClassificationService.section_filter("B2CS")
        | Gstr1ClassificationService.section_filter("CDNR")
        | Gstr1ClassificationService.section_filter("CDNUR")
    )


def _build_outward_taxable_contributors(scope) -> list[dict]:
    if not scope:
        return []
    if not hasattr(scope, "entity_id") or not hasattr(scope, "include_cancelled"):
        return []
    queryset = apply_scope_filters(base_queryset(), scope).filter(_outward_taxable_filter())
    invoices = list(
        queryset.order_by("-total_taxable_value", "-id")[:5]
    )
    if not invoices:
        return []

    txn_ids = [int(invoice.id) for invoice in invoices]
    service_invoice_ids = set(
        SalesInvoiceLine.objects.filter(header_id__in=txn_ids, is_service=True)
        .values_list("header_id", flat=True)
        .distinct()
    )
    entry_filters = {
        "entity_id": scope.entity_id,
        "txn_id__in": txn_ids,
    }
    if scope.entityfinid_id:
        entry_filters["entityfin_id"] = scope.entityfinid_id
    if scope.subentity_id is not None:
        entry_filters["subentity_id"] = scope.subentity_id
    entries = Entry.objects.filter(**entry_filters).order_by("-id")
    latest_entry_by_txn = {}
    for entry in entries:
        txn_id = int(entry.txn_id or 0)
        if txn_id and txn_id not in latest_entry_by_txn:
            latest_entry_by_txn[txn_id] = entry

    contributors = []
    for invoice in invoices:
        invoice_id = int(invoice.id)
        has_service_lines = invoice_id in service_invoice_ids
        entry = latest_entry_by_txn.get(invoice_id)
        posting_lookup = (
            {
                "entry_id": int(entry.id),
                "txn_id": int(entry.txn_id),
                "txn_type": entry.txn_type,
                "voucher_number": entry.voucher_no,
                "posting_date": entry.posting_date,
                "voucher_date": entry.voucher_date,
                "status": entry.status,
                "status_name": entry.get_status_display(),
                "source_module": "sales",
                "document_type": "sales_invoice",
                "document_id": invoice_id,
            }
            if entry
            else None
        )
        contributors.append(
            {
                "invoice_id": invoice_id,
                "invoice_number": invoice.invoice_number or f"Invoice-{invoice_id}",
                "bill_date": invoice.bill_date,
                "taxable_value": _q(invoice.total_taxable_value),
                "total_tax": _q(invoice.total_cgst) + _q(invoice.total_sgst) + _q(invoice.total_igst) + _q(invoice.total_cess),
                "grand_total": _q(invoice.grand_total),
                "is_posted": bool(entry),
                "posting_status_label": "Posted" if entry else "Not posted",
                "drilldowns": (
                    {
                        "source_document": _build_source_document_drilldown(
                            invoice_id=invoice_id,
                            has_service_lines=has_service_lines,
                        ),
                        "posting_lookup": _build_posting_lookup_drilldown(invoice_id=invoice_id),
                    }
                    if entry
                    else {
                        "source_document": _build_source_document_drilldown(
                            invoice_id=invoice_id,
                            has_service_lines=has_service_lines,
                        ),
                    }
                ),
                "posting_lookup": posting_lookup,
            }
        )
    return contributors


def _output_tax_return_bucket(gstr3b_summary: dict) -> dict[str, Decimal]:
    section_31 = gstr3b_summary.get("section_3_1", {})
    return _add_bucket(
        _bucket_from_gstr3b(section_31.get("outward_taxable_supplies")),
        _bucket_from_gstr3b(section_31.get("outward_zero_rated_supplies")),
    )


def _output_tax_ledger_amounts(scope) -> tuple[dict[str, Decimal], dict[str, int | None], list[dict]]:
    ledger_amounts = {component: ZERO for _, component, _ in OUTPUT_TAX_LEDGER_CODES}
    ledger_ids = {component: None for _, component, _ in OUTPUT_TAX_LEDGER_CODES}
    warnings = []
    if not scope or not getattr(scope, "entity_id", None):
        warnings.append(
            {
                "code": "GST_OUTPUT_LEDGER_SCOPE_MISSING",
                "severity": "warning",
                "message": "Output GST ledger comparison could not run because entity scope is missing.",
            }
        )
        return ledger_amounts, ledger_ids, warnings

    for static_code, component, label in OUTPUT_TAX_LEDGER_CODES:
        ledger_id = StaticAccountService.get_ledger_id(scope.entity_id, static_code, required=False)
        ledger_ids[component] = ledger_id
        if not ledger_id:
            warnings.append(
                {
                    "code": "GST_OUTPUT_LEDGER_MAPPING_MISSING",
                    "severity": "warning",
                    "message": f"{label} static ledger mapping is missing; books comparison for this tax component is unavailable.",
                    "static_account_code": static_code,
                    "component": component,
                }
            )

    configured_ledger_ids = [ledger_id for ledger_id in ledger_ids.values() if ledger_id]
    if not configured_ledger_ids:
        return ledger_amounts, ledger_ids, warnings

    filters = {
        "entity_id": scope.entity_id,
        "ledger_id__in": configured_ledger_ids,
        "entry__status": EntryStatus.POSTED,
    }
    if getattr(scope, "entityfinid_id", None):
        filters["entityfin_id"] = scope.entityfinid_id
    if getattr(scope, "subentity_id", None) is not None:
        filters["subentity_id"] = scope.subentity_id
    from_date = _normalize_scope_date(getattr(scope, "from_date", None))
    to_date = _normalize_scope_date(getattr(scope, "to_date", None))
    if from_date:
        filters["posting_date__gte"] = from_date
    if to_date:
        filters["posting_date__lte"] = to_date

    aggregates = (
        JournalLine.objects.filter(**filters)
        .values("ledger_id")
        .annotate(
            debit=Coalesce(Sum("amount", filter=Q(drcr=True)), Value(ZERO)),
            credit=Coalesce(Sum("amount", filter=Q(drcr=False)), Value(ZERO)),
        )
    )
    net_credit_by_ledger = {int(row["ledger_id"]): _q(row["credit"]) - _q(row["debit"]) for row in aggregates}
    for _, component, _ in OUTPUT_TAX_LEDGER_CODES:
        ledger_id = ledger_ids.get(component)
        if ledger_id:
            ledger_amounts[component] = net_credit_by_ledger.get(int(ledger_id), ZERO)
    return ledger_amounts, ledger_ids, warnings


def _build_output_tax_ledger_reconciliation(*, gstr3b_summary: dict, scope) -> dict:
    return_bucket = _output_tax_return_bucket(gstr3b_summary)
    ledger_amounts, ledger_ids, warnings = _output_tax_ledger_amounts(scope)
    ledger_names = {
        row["id"]: row["name"]
        for row in Ledger.objects.filter(id__in=[ledger_id for ledger_id in ledger_ids.values() if ledger_id]).values("id", "name")
    }
    rows = []
    for static_code, component, label in OUTPUT_TAX_LEDGER_CODES:
        return_tax = _q(return_bucket.get(component))
        ledger_tax = _q(ledger_amounts.get(component))
        difference = return_tax - ledger_tax
        ledger_id = ledger_ids.get(component)
        rows.append(
            {
                "code": static_code,
                "component": component,
                "label": label,
                "status": "matched" if ledger_id and abs(difference) <= TOLERANCE else "mismatch",
                "mapping_status": "configured" if ledger_id else "missing_mapping",
                "return_tax": return_tax,
                "ledger_tax": ledger_tax,
                "difference": difference,
                "ledger_id": ledger_id,
                "ledger_name": ledger_names.get(ledger_id),
                "drilldowns": (
                    {
                        "ledger_book": {
                            "target": "ledger_book",
                            "label": "Open ledger book",
                            "kind": "report",
                            "route": "/reports/financial/ledger-book",
                            "params": {
                                "ledger": ledger_id,
                                "ledger_id": ledger_id,
                                "entityfinid": getattr(scope, "entityfinid_id", None),
                                "subentity": getattr(scope, "subentity_id", None),
                                "from_date": getattr(scope, "from_date", None),
                                "to_date": getattr(scope, "to_date", None),
                            },
                        }
                    }
                    if ledger_id
                    else {}
                ),
            }
        )
    return {
        "rows": rows,
        "summary": {
            "comparison_count": len(rows),
            "matched_count": len([row for row in rows if row["status"] == "matched"]),
            "mismatch_count": len([row for row in rows if row["status"] == "mismatch"]),
            "return_total_tax": sum((_q(row["return_tax"]) for row in rows), ZERO),
            "ledger_total_tax": sum((_q(row["ledger_tax"]) for row in rows), ZERO),
            "difference_total_tax": sum((_q(row["difference"]) for row in rows), ZERO),
        },
        "warnings": warnings,
    }


def _same_reconciliation_signature(left: dict, right: dict) -> bool:
    comparable_fields = (
        "difference_taxable_value",
        "difference_total_tax",
        "gstr1_taxable_value",
        "gstr3b_taxable_value",
        "gstr1_total_tax",
        "gstr3b_total_tax",
    )
    return all(_q(left.get(field)) == _q(right.get(field)) for field in comparable_fields)


def _normalize_rollup_duplicate(rows: list[dict]) -> list[dict]:
    outward_taxable = next((row for row in rows if row.get("code") == "OUTWARD_TAXABLE"), None)
    zero_rated = next((row for row in rows if row.get("code") == "ZERO_RATED"), None)
    total_outward = next((row for row in rows if row.get("code") == "TOTAL_OUTWARD_TAX"), None)
    if not outward_taxable or not total_outward:
        return rows
    if str(total_outward.get("status") or "").lower() != "mismatch":
        return rows
    if str(outward_taxable.get("status") or "").lower() != "mismatch":
        return rows
    if zero_rated and str(zero_rated.get("status") or "").lower() != "matched":
        return rows
    if not _same_reconciliation_signature(total_outward, outward_taxable):
        return rows

    # Avoid double counting the same variance in the roll-up when zero-rated side is matched.
    total_outward["status"] = "matched"
    total_outward["is_advisory"] = True
    total_outward["mismatch_kind"] = "advisory"
    total_outward["note"] = (
        "Roll-up mirrors Outward Taxable Supplies variance and is shown as informational to avoid duplicate mismatch counting."
    )
    return rows


def _status_for_filing_pack(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") or {}
    ledger_summary = (payload.get("output_tax_ledger_reconciliation") or {}).get("summary") or {}
    warnings = payload.get("warnings") or []
    actionable_mismatch_count = int(summary.get("actionable_mismatch_count") or 0)
    ledger_mismatch_count = int(ledger_summary.get("mismatch_count") or 0)
    blocking_warning_count = len(
        [
            warning
            for warning in warnings
            if str(warning.get("severity") or "").lower() in {"error", "critical", "blocked"}
        ]
    )
    if actionable_mismatch_count or ledger_mismatch_count or blocking_warning_count:
        return "needs_review"
    if warnings:
        return "ready_with_advisories"
    return "ready"


def _filing_evidence_checklist(payload: dict[str, Any]) -> list[dict[str, Any]]:
    summary = payload.get("summary") or {}
    ledger_summary = (payload.get("output_tax_ledger_reconciliation") or {}).get("summary") or {}
    warnings = payload.get("warnings") or []
    actionable_mismatch_count = int(summary.get("actionable_mismatch_count") or 0)
    advisory_mismatch_count = int(summary.get("advisory_mismatch_count") or 0)
    ledger_mismatch_count = int(ledger_summary.get("mismatch_count") or 0)
    warning_count = len(warnings)
    return [
        {
            "code": "RETURN_RECONCILIATION",
            "label": "GSTR-1 and GSTR-3B return comparison",
            "status": "passed" if actionable_mismatch_count == 0 else "needs_review",
            "message": (
                "No actionable return mismatch found."
                if actionable_mismatch_count == 0
                else f"{actionable_mismatch_count} actionable mismatch item requires review."
            ),
        },
        {
            "code": "ADVISORY_DISCLOSURES",
            "label": "Advisory disclosure review",
            "status": "informational" if advisory_mismatch_count else "passed",
            "message": (
                f"{advisory_mismatch_count} advisory mismatch item is informational."
                if advisory_mismatch_count
                else "No advisory mismatch found."
            ),
        },
        {
            "code": "OUTPUT_TAX_LEDGER",
            "label": "Output GST ledger tie-out",
            "status": "passed" if ledger_mismatch_count == 0 else "needs_review",
            "message": (
                "Output GST ledgers match the return tax liability."
                if ledger_mismatch_count == 0
                else f"{ledger_mismatch_count} output-tax ledger component requires review or static mapping."
            ),
        },
        {
            "code": "EVIDENCE_WARNINGS",
            "label": "Evidence pack warnings",
            "status": "passed" if warning_count == 0 else "informational",
            "message": (
                "No evidence warnings generated."
                if warning_count == 0
                else f"{warning_count} warning/advisory item included in the evidence pack."
            ),
        },
    ]


def build_gstr1_vs_gstr3b_evidence_pack(*, reconciliation_payload: dict[str, Any], scope_params: dict | None = None) -> dict[str, Any]:
    cleaned_scope = _clean_scope_params(scope_params)
    status = _status_for_filing_pack(reconciliation_payload)
    checklist = _filing_evidence_checklist(reconciliation_payload)
    return {
        "pack_code": "gstr1-vs-gstr3b-filing-evidence",
        "pack_name": "GSTR-1 vs GSTR-3B Filing Evidence Pack",
        "generated_at": timezone.now().isoformat(),
        "status": status,
        "scope": cleaned_scope,
        "summary": reconciliation_payload.get("summary") or {},
        "output_tax_ledger_summary": (
            reconciliation_payload.get("output_tax_ledger_reconciliation") or {}
        ).get("summary")
        or {},
        "checklist": checklist,
        "included_sections": [
            {
                "code": "comparison_grid",
                "label": "Return comparison grid",
                "row_count": len(reconciliation_payload.get("rows") or []),
            },
            {
                "code": "output_tax_ledger",
                "label": "Output GST ledger tie-out",
                "row_count": len((reconciliation_payload.get("output_tax_ledger_reconciliation") or {}).get("rows") or []),
            },
            {
                "code": "warnings",
                "label": "Warnings and advisories",
                "row_count": len(reconciliation_payload.get("warnings") or []),
            },
        ],
        "rows": reconciliation_payload.get("rows") or [],
        "output_tax_ledger_reconciliation": reconciliation_payload.get("output_tax_ledger_reconciliation") or {},
        "warnings": reconciliation_payload.get("warnings") or [],
    }


def build_gstr1_vs_gstr3b_reconciliation(
    *,
    gstr1_summary: dict,
    gstr3b_summary: dict,
    scope_params: dict | None = None,
    gstr1_scope=None,
    include_contributors: bool = True,
) -> dict:
    sections = _section_map(gstr1_summary)
    nil_rows = _nil_exempt_map(gstr1_summary)

    b2b = _bucket_from_gstr1(sections.get("B2B"))
    b2cl = _bucket_from_gstr1(sections.get("B2CL"))
    b2cs = _bucket_from_gstr1(sections.get("B2CS"))
    cdnr = _bucket_from_gstr1(sections.get("CDNR"))
    cdnur = _bucket_from_gstr1(sections.get("CDNUR"))
    exp = _bucket_from_gstr1(sections.get("EXP"))

    outward_taxable_gstr1 = _add_bucket(b2b, b2cl, b2cs, cdnr, cdnur)
    zero_rated_gstr1 = exp
    nil_exempt_non_gst_gstr1 = _add_bucket(*[_bucket_from_gstr1(row) for row in nil_rows.values()])
    non_gst_gstr1 = _bucket_from_gstr1(nil_rows.get(4))
    interstate_disclosure_gstr1 = _add_bucket(b2cl, b2cs, cdnur)
    total_outward_gstr1 = _add_bucket(outward_taxable_gstr1, zero_rated_gstr1)

    section_31 = gstr3b_summary.get("section_3_1", {})
    section_32 = gstr3b_summary.get("section_3_2", {})
    outward_taxable_gstr3b = _bucket_from_gstr3b(section_31.get("outward_taxable_supplies"))
    zero_rated_gstr3b = _bucket_from_gstr3b(section_31.get("outward_zero_rated_supplies"))
    nil_exempt_non_gst_gstr3b = _bucket_from_gstr3b(section_31.get("outward_nil_exempt_non_gst"))
    non_gst_gstr3b = _bucket_from_gstr3b(section_31.get("non_gst_outward_supplies"))
    interstate_disclosure_gstr3b = _add_bucket(
        _bucket_from_gstr3b(section_32.get("interstate_supplies_to_unregistered")),
        _bucket_from_gstr3b(section_32.get("interstate_supplies_to_composition")),
        _bucket_from_gstr3b(section_32.get("interstate_supplies_to_uin_holders")),
    )
    total_outward_gstr3b = _add_bucket(outward_taxable_gstr3b, zero_rated_gstr3b)

    rows = [
        _difference_row(
            code="OUTWARD_TAXABLE",
            label="Outward Taxable Supplies",
            gstr1_row=outward_taxable_gstr1,
            gstr3b_row=outward_taxable_gstr3b,
        ),
        _difference_row(
            code="ZERO_RATED",
            label="Zero Rated / Export Supplies",
            gstr1_row=zero_rated_gstr1,
            gstr3b_row=zero_rated_gstr3b,
        ),
        _difference_row(
            code="NIL_EXEMPT_NON_GST",
            label="Nil / Exempt / Non-GST Outward Supplies",
            gstr1_row=nil_exempt_non_gst_gstr1,
            gstr3b_row=nil_exempt_non_gst_gstr3b,
        ),
        _difference_row(
            code="NON_GST_ONLY",
            label="Non-GST Outward Supplies",
            gstr1_row=non_gst_gstr1,
            gstr3b_row=non_gst_gstr3b,
            note="Advisory sub-check inside Nil / Exempt / Non-GST outward supplies.",
        ),
        _difference_row(
            code="INTERSTATE_DISCLOSURE",
            label="Inter-State Disclosure (Consumer / Other Non-Regular)",
            gstr1_row=interstate_disclosure_gstr1,
            gstr3b_row=interstate_disclosure_gstr3b,
            note="Advisory disclosure comparison between GSTR-1 section buckets and GSTR-3B section 3.2.",
        ),
        _difference_row(
            code="TOTAL_OUTWARD_TAX",
            label="Total Outward Taxable + Zero Rated",
            gstr1_row=total_outward_gstr1,
            gstr3b_row=total_outward_gstr3b,
        ),
    ]

    rows = _normalize_rollup_duplicate(rows)
    outward_contributors = _build_outward_taxable_contributors(gstr1_scope) if include_contributors else []
    for row in rows:
        row["drilldowns"] = _build_reconciliation_drilldowns(scope_params, str(row.get("code") or ""))
        if include_contributors and str(row.get("code") or "").upper() == "OUTWARD_TAXABLE":
            row["contributors"] = outward_contributors
            row["contributors_count"] = len(outward_contributors)
            if outward_contributors:
                row["note"] = row.get("note") or "Review contributors for invoice-level source and posting actions."

    matched_count = len([row for row in rows if row["status"] == "matched"])
    mismatch_count = len(rows) - matched_count
    advisory_mismatch_count = len([row for row in rows if row["status"] == "mismatch" and row["is_advisory"]])
    actionable_mismatch_count = len([row for row in rows if row["status"] == "mismatch" and not row["is_advisory"]])
    max_taxable_difference = max((abs(_q(row["difference_taxable_value"])) for row in rows), default=ZERO)
    max_total_tax_difference = max((abs(_q(row["difference_total_tax"])) for row in rows), default=ZERO)
    output_tax_ledger_reconciliation = _build_output_tax_ledger_reconciliation(
        gstr3b_summary=gstr3b_summary,
        scope=gstr1_scope,
    )
    payload = {
        "rows": rows,
        "summary": {
            "comparison_count": len(rows),
            "matched_count": matched_count,
            "mismatch_count": mismatch_count,
            "actionable_mismatch_count": actionable_mismatch_count,
            "advisory_mismatch_count": advisory_mismatch_count,
            "max_taxable_difference": max_taxable_difference,
            "max_total_tax_difference": max_total_tax_difference,
            "gstr1_total_taxable": total_outward_gstr1["taxable_value"],
            "gstr3b_total_taxable": total_outward_gstr3b["taxable_value"],
            "gstr1_total_tax": total_outward_gstr1["total_tax"],
            "gstr3b_total_tax": total_outward_gstr3b["total_tax"],
        },
        "output_tax_ledger_reconciliation": output_tax_ledger_reconciliation,
        "warnings": [
            {
                "code": "GST_RECON_SECTION32_ADVISORY",
                "severity": "info",
                "message": "Inter-state disclosure is advisory because GSTR-1 outward tables and GSTR-3B section 3.2 are grouped differently.",
            }
        ]
        + output_tax_ledger_reconciliation["warnings"],
    }
    payload["filing_evidence_pack"] = build_gstr1_vs_gstr3b_evidence_pack(
        reconciliation_payload=payload,
        scope_params=scope_params,
    )
    return payload
