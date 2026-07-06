from __future__ import annotations

from decimal import Decimal

from posting.models import Entry
from reports.gstr1.selectors.queries import apply_scope_filters, base_queryset
from reports.gstr1.services.classification import Gstr1ClassificationService
from sales.models import SalesInvoiceLine

ZERO = Decimal("0.00")
TOLERANCE = Decimal("0.05")
ADVISORY_CODES = {"INTERSTATE_DISCLOSURE", "NON_GST_ONLY"}


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
    return {
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
        "warnings": [
            {
                "code": "GST_RECON_SECTION32_ADVISORY",
                "severity": "info",
                "message": "Inter-state disclosure is advisory because GSTR-1 outward tables and GSTR-3B section 3.2 are grouped differently.",
            }
        ],
    }
