from __future__ import annotations

from collections import OrderedDict


READINESS_GROUPS = OrderedDict(
    [
        (
            "master_data",
            {
                "label": "Master Data",
                "description": "Customer, seller, GSTIN, and HSN details that must be reliable before filing.",
                "action_label": "Fix party and item masters",
                "action_description": "Update GSTIN, place of supply, or HSN master data on the affected invoices.",
            },
        ),
        (
            "filing_rules",
            {
                "label": "Filing Rules",
                "description": "Invoice attributes that can block accurate GST filing output.",
                "action_label": "Correct filing fields",
                "action_description": "Correct duplicate numbers, export POS, note linkage, and core filing attributes before export.",
            },
        ),
        (
            "tax_reconciliation",
            {
                "label": "Tax Reconciliation",
                "description": "Tax totals and regime checks that should be reviewed before the final export.",
                "action_label": "Review tax math",
                "action_description": "Compare header totals, tax summaries, and interstate or intrastate tax splits.",
            },
        ),
        (
            "advance_adjustments",
            {
                "label": "Advance Adjustments",
                "description": "Table 11 advance rows that should reconcile before filing.",
                "action_label": "Review Table 11 adjustments",
                "action_description": "Confirm advance receipts, linked invoices, and adjustment amounts for Table 11A and 11B.",
            },
        ),
    ]
)


WARNING_RULES = {
    "INVALID_GSTIN": {
        "group_code": "master_data",
        "impact": "blocked",
        "action_label": "Fix customer GSTIN",
        "action_description": "Update the customer GSTIN or move the invoice to the correct B2C treatment.",
    },
    "INVALID_SELLER_GSTIN": {
        "group_code": "master_data",
        "impact": "blocked",
        "action_label": "Fix seller GSTIN",
        "action_description": "Correct the seller GSTIN used on the invoice before filing.",
    },
    "B2B_GSTIN_REQUIRED": {
        "group_code": "master_data",
        "impact": "blocked",
        "action_label": "Add buyer GSTIN",
        "action_description": "Add a valid buyer GSTIN for B2B, SEZ, or deemed export invoices.",
    },
    "MISSING_PLACE_OF_SUPPLY": {
        "group_code": "master_data",
        "impact": "blocked",
        "action_label": "Set place of supply",
        "action_description": "Update the place of supply state code on the invoice.",
    },
    "INVALID_PLACE_OF_SUPPLY": {
        "group_code": "master_data",
        "impact": "blocked",
        "action_label": "Correct place of supply",
        "action_description": "Use a valid 2-digit GST state code for place of supply.",
    },
    "MISSING_HSN": {
        "group_code": "master_data",
        "impact": "blocked",
        "action_label": "Fill HSN or SAC",
        "action_description": "Update taxable invoice lines with the correct HSN or SAC code.",
    },
    "DUPLICATE_INVOICE": {
        "group_code": "filing_rules",
        "impact": "blocked",
        "action_label": "Resolve duplicate invoice number",
        "action_description": "Use a unique invoice number for the same seller GSTIN and document type.",
    },
    "EXPORT_POS_INVALID": {
        "group_code": "filing_rules",
        "impact": "blocked",
        "action_label": "Fix export POS code",
        "action_description": "Use the export place-of-supply code required for export invoices.",
    },
    "NOTE_LINK_MISSING": {
        "group_code": "filing_rules",
        "impact": "blocked",
        "action_label": "Link the note to its invoice",
        "action_description": "Attach the credit or debit note to the original tax invoice.",
    },
    "NOTE_LINK_INVALID": {
        "group_code": "filing_rules",
        "impact": "blocked",
        "action_label": "Repair note linkage",
        "action_description": "Ensure the original invoice still exists and is available in the selected scope.",
    },
    "NOTE_LINK_SCOPE_MISMATCH": {
        "group_code": "filing_rules",
        "impact": "blocked",
        "action_label": "Align note scope",
        "action_description": "Make sure the note and original invoice belong to the same entity, FY, and subentity scope.",
    },
    "NOTE_LINK_DOC_TYPE": {
        "group_code": "filing_rules",
        "impact": "blocked",
        "action_label": "Fix original document type",
        "action_description": "Point the note to a tax invoice instead of another document type.",
    },
    "NON_POSITIVE_TAXABLE": {
        "group_code": "filing_rules",
        "impact": "blocked",
        "action_label": "Correct taxable value",
        "action_description": "Taxable invoices should not carry zero or negative taxable value.",
    },
    "NON_POSITIVE_TOTAL": {
        "group_code": "filing_rules",
        "impact": "blocked",
        "action_label": "Correct invoice total",
        "action_description": "Tax invoices should not carry zero or negative grand total.",
    },
    "POS_TAX_REGIME_MISMATCH": {
        "group_code": "tax_reconciliation",
        "impact": "review",
        "action_label": "Review tax regime",
        "action_description": "Check whether interstate or intrastate treatment matches the place of supply.",
    },
    "NIL_EXEMPT_TAX_PRESENT": {
        "group_code": "tax_reconciliation",
        "impact": "review",
        "action_label": "Review nil or exempt tax rows",
        "action_description": "Nil, exempt, and non-GST invoices should not carry tax amounts.",
    },
    "TAXABLE_MISMATCH": {
        "group_code": "tax_reconciliation",
        "impact": "review",
        "action_label": "Review taxable total",
        "action_description": "Compare invoice header taxable value with the tax summary lines.",
    },
    "CGST_MISMATCH": {
        "group_code": "tax_reconciliation",
        "impact": "review",
        "action_label": "Review CGST total",
        "action_description": "Compare invoice header CGST with the tax summary lines.",
    },
    "SGST_MISMATCH": {
        "group_code": "tax_reconciliation",
        "impact": "review",
        "action_label": "Review SGST total",
        "action_description": "Compare invoice header SGST with the tax summary lines.",
    },
    "IGST_MISMATCH": {
        "group_code": "tax_reconciliation",
        "impact": "review",
        "action_label": "Review IGST total",
        "action_description": "Compare invoice header IGST with the tax summary lines.",
    },
    "CESS_MISMATCH": {
        "group_code": "tax_reconciliation",
        "impact": "review",
        "action_label": "Review cess total",
        "action_description": "Compare invoice header cess with the tax summary lines.",
    },
    "IGST_ON_INTRASTATE": {
        "group_code": "tax_reconciliation",
        "impact": "review",
        "action_label": "Review intrastate tax split",
        "action_description": "Intrastate invoices should not carry IGST unless the source treatment is intentionally exceptional.",
    },
    "CGST_SGST_ON_INTERSTATE": {
        "group_code": "tax_reconciliation",
        "impact": "review",
        "action_label": "Review interstate tax split",
        "action_description": "Interstate invoices should not carry CGST or SGST in a normal filing scenario.",
    },
    "INVOICE_TOTAL_MISMATCH": {
        "group_code": "tax_reconciliation",
        "impact": "review",
        "action_label": "Review grand total",
        "action_description": "Compare invoice grand total with invoice lines, additional charges, and round-off.",
    },
    "CANCELLED_HAS_AMOUNTS": {
        "group_code": "tax_reconciliation",
        "impact": "review",
        "action_label": "Review cancelled invoice amounts",
        "action_description": "Cancelled invoices should normally net to zero before filing.",
    },
    "TABLE11_ORPHAN_ADJUSTMENT": {
        "group_code": "advance_adjustments",
        "impact": "review",
        "action_label": "Review orphan adjustment",
        "action_description": "Match the Table 11B adjustment to its source advance receipt row.",
    },
    "TABLE11_ADJUSTMENT_EXCEEDS_SOURCE": {
        "group_code": "advance_adjustments",
        "impact": "review",
        "action_label": "Review adjustment amount",
        "action_description": "Table 11B adjustments should not exceed the source advance amount.",
    },
    "TABLE11_DUPLICATE_ADJUSTMENT": {
        "group_code": "advance_adjustments",
        "impact": "review",
        "action_label": "Review duplicate adjustment",
        "action_description": "Remove duplicate active Table 11B rows for the same voucher and linked invoice.",
    },
}


class Gstr1ReadinessService:
    def build(self, *, warnings: list[dict], summary: dict) -> dict:
        enriched = [self._enrich_warning(item) for item in warnings]
        groups = self._group_warnings(enriched)
        status = self._derive_status(groups)
        counts = self._build_counts(groups)
        return {
            "status": status,
            "counts": counts,
            "summary_cards": self._build_summary_cards(summary=summary, counts=counts, status=status),
            "validation_groups": groups,
            "next_steps": self._build_next_steps(status=status, counts=counts),
            "export_flow": self._build_export_flow(status=status, counts=counts),
            "warnings": enriched,
        }

    def _enrich_warning(self, warning: dict) -> dict:
        payload = dict(warning)
        rule = WARNING_RULES.get(payload.get("code"), {})
        group_code = rule.get("group_code", "tax_reconciliation")
        group = READINESS_GROUPS.get(group_code, READINESS_GROUPS["tax_reconciliation"])
        payload["impact"] = rule.get("impact", "review")
        payload["group_code"] = group_code
        payload["group_label"] = group["label"]
        payload["action_label"] = rule.get("action_label", group["action_label"])
        payload["action_description"] = rule.get("action_description", group["action_description"])
        invoice_id = payload.get("invoice_id")
        if invoice_id:
            payload["invoice_detail_url"] = f"/api/reports/gstr1/invoice/{invoice_id}/"
            payload["drilldowns"] = {
                "source_document": self._build_source_document_drilldown(invoice_id=invoice_id),
                "posting_lookup": self._build_posting_lookup_drilldown(invoice_id=invoice_id),
            }
        return payload

    def _build_source_document_drilldown(self, *, invoice_id: int) -> dict:
        return {
            "target": "sales_invoice_detail",
            "label": "Open source invoice",
            "kind": "document",
            "route": "/saleinvoice",
            "params": {
                "transactionid": int(invoice_id),
            },
        }

    def _build_posting_lookup_drilldown(self, *, invoice_id: int) -> dict:
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

    def _group_warnings(self, warnings: list[dict]) -> list[dict]:
        buckets: OrderedDict[str, list[dict]] = OrderedDict((code, []) for code in READINESS_GROUPS)
        for warning in warnings:
            buckets.setdefault(warning["group_code"], []).append(warning)

        groups = []
        for group_code, items in buckets.items():
            if not items:
                continue
            group = READINESS_GROUPS.get(group_code, READINESS_GROUPS["tax_reconciliation"])
            status_code = "blocked" if any(item.get("impact") == "blocked" for item in items) else "review"
            groups.append(
                {
                    "code": group_code,
                    "label": group["label"],
                    "description": group["description"],
                    "status": status_code,
                    "status_label": "Blocked" if status_code == "blocked" else "Review",
                    "warning_count": len(items),
                    "blocked_count": sum(1 for item in items if item.get("impact") == "blocked"),
                    "review_count": sum(1 for item in items if item.get("impact") == "review"),
                    "action_label": group["action_label"],
                    "action_description": group["action_description"],
                    "warnings": items,
                }
            )
        return groups

    def _derive_status(self, groups: list[dict]) -> dict:
        blocked_count = sum(group["blocked_count"] for group in groups)
        warning_count = sum(group["warning_count"] for group in groups)
        if blocked_count:
            return {
                "code": "blocked",
                "label": "Blocked",
                "tone": "blocked",
                "message": "Resolve filing blockers before generating the final filing export.",
            }
        if warning_count:
            return {
                "code": "review",
                "label": "Review",
                "tone": "warning",
                "message": "Filing can proceed after review, but warning items should be checked first.",
            }
        return {
            "code": "ready_to_file",
            "label": "Ready To File",
            "tone": "success",
            "message": "No filing blockers or review warnings were found in the selected scope.",
        }

    def _build_counts(self, groups: list[dict]) -> dict:
        blocked_count = sum(group["blocked_count"] for group in groups)
        review_count = sum(group["review_count"] for group in groups)
        return {
            "total_warnings": blocked_count + review_count,
            "blocked_warnings": blocked_count,
            "review_warnings": review_count,
            "groups": len(groups),
        }

    def _build_summary_cards(self, *, summary: dict, counts: dict, status: dict) -> list[dict]:
        total_documents = sum(int(row.get("document_count") or 0) for row in summary.get("sections", []))
        return [
            {
                "code": "documents_in_scope",
                "label": "Documents In Scope",
                "value": total_documents,
                "tone": "neutral",
            },
            {
                "code": "blocked_warnings",
                "label": "Blocked Items",
                "value": counts["blocked_warnings"],
                "tone": "blocked" if counts["blocked_warnings"] else "success",
            },
            {
                "code": "review_warnings",
                "label": "Review Items",
                "value": counts["review_warnings"],
                "tone": "warning" if counts["review_warnings"] else "success",
            },
            {
                "code": "filing_status",
                "label": "Filing Status",
                "value": status["label"],
                "tone": status["tone"],
            },
        ]

    def _build_next_steps(self, *, status: dict, counts: dict) -> list[str]:
        if status["code"] == "blocked":
            return [
                "Resolve blocked items before generating GSTN JSON.",
                "Use invoice drilldowns to correct source data on the affected documents.",
                "Re-run readiness after master and filing rule fixes.",
            ]
        if status["code"] == "review":
            return [
                "Review warning groups before generating GSTN JSON.",
                "Use Excel export for reconciliation if tax totals need side-by-side review.",
                "Proceed to filing export after finance signoff on the review items.",
            ]
        return [
            "Generate GSTN JSON or Excel from the same validated scope.",
            "Retain the readiness snapshot as part of filing review evidence.",
            "Use section and invoice drilldowns only if a final spot check is needed.",
        ]

    def _build_export_flow(self, *, status: dict, counts: dict) -> dict:
        primary_format = "xlsx" if counts["blocked_warnings"] else "gstn_json"
        return {
            "primary_format": primary_format,
            "secondary_formats": ["xlsx", "csv", "json"] if primary_format == "gstn_json" else ["csv", "json", "gstn_json"],
            "recommended_step": (
                "Clear blocked items before filing export."
                if status["code"] == "blocked"
                else "Review warnings, then generate the filing export."
                if status["code"] == "review"
                else "Generate the filing export from this validated scope."
            ),
        }
