from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction

from gst_reconciliation.models import GstMismatchReason, GstReconciliationItem, GstReconciliationRun
from gst_reconciliation.services.matching.base import BaseReconciliationMatcher, MatchExecutionResult
from gst_reconciliation.services.matching.reasons import (
    StructuredMismatch,
    amount_mismatch_reason,
    field_mismatch_reason,
    missing_in_books_reason,
    multiple_candidates_reason,
)
from gst_reconciliation.services.matching.registry import MatcherRegistry
from gst_reconciliation.services.normalization import (
    decimal_abs_diff,
    normalize_gstin,
    normalize_invoice_number,
)
from gst_reconciliation.services.item_workflow_service import GstReconciliationItemWorkflowService
from purchase.models.purchase_core import PurchaseInvoiceHeader


@dataclass(frozen=True)
class Gstr2bToleranceConfig:
    amount_tolerance: Decimal = Decimal("1.00")
    taxable_tolerance: Decimal = Decimal("1.00")
    tax_component_tolerance: Decimal = Decimal("1.00")
    date_tolerance_days: int = 0
    candidate_margin_score: Decimal = Decimal("5.00")

    @classmethod
    def from_run(cls, run: GstReconciliationRun) -> "Gstr2bToleranceConfig":
        raw = run.tolerance_config_json or {}
        def q(value: object, default: str) -> Decimal:
            try:
                return Decimal(str(value if value is not None else default)).quantize(Decimal("0.01"))
            except Exception:
                return Decimal(default)
        try:
            date_days = int(raw.get("date_tolerance_days", 0) or 0)
        except (TypeError, ValueError):
            date_days = 0
        return cls(
            amount_tolerance=q(raw.get("amount_tolerance"), "1.00"),
            taxable_tolerance=q(raw.get("taxable_tolerance"), "1.00"),
            tax_component_tolerance=q(raw.get("tax_component_tolerance"), "1.00"),
            date_tolerance_days=max(date_days, 0),
            candidate_margin_score=q(raw.get("candidate_margin_score"), "5.00"),
        )


@dataclass(frozen=True)
class CandidateScore:
    candidate: PurchaseInvoiceHeader
    confidence_score: Decimal
    reasons: list[StructuredMismatch]


class PortalGstr2bPurchaseMatcher(BaseReconciliationMatcher):
    code = "gstr2b_purchase_portal"

    def supports(self, run: GstReconciliationRun) -> bool:
        return run.reconciliation_type == GstReconciliationRun.ReconciliationType.GSTR2B_PURCHASE

    @transaction.atomic
    def execute(self, run: GstReconciliationRun, *, user=None) -> MatchExecutionResult:
        tolerance = Gstr2bToleranceConfig.from_run(run)
        items = list(run.items.select_related("run").all().order_by("id"))
        matched = partial = mismatched = ignored = 0
        confidence_total = Decimal("0.00")
        for item in items:
            score = self._match_item(run=run, item=item, tolerance=tolerance, user=user)
            confidence_total += score
            if item.match_status == GstReconciliationItem.MatchStatus.MATCHED:
                matched += 1
            elif item.match_status == GstReconciliationItem.MatchStatus.PARTIAL:
                partial += 1
            elif item.match_status == GstReconciliationItem.MatchStatus.IGNORED:
                ignored += 1
            else:
                mismatched += 1
        average_confidence = (confidence_total / Decimal(len(items or [1]))).quantize(Decimal("0.01")) if items else Decimal("0.00")
        run.summary_json = {
            **(run.summary_json or {}),
            "match_confidence_average": str(average_confidence),
            "tolerance_config": {
                "amount_tolerance": str(tolerance.amount_tolerance),
                "taxable_tolerance": str(tolerance.taxable_tolerance),
                "tax_component_tolerance": str(tolerance.tax_component_tolerance),
                "date_tolerance_days": tolerance.date_tolerance_days,
            },
        }
        run.save(update_fields=["summary_json", "updated_at"])
        return MatchExecutionResult(
            run=run,
            processed_items=len(items),
            matched_items=matched,
            partial_items=partial,
            mismatched_items=mismatched,
            ignored_items=ignored,
        )

    def _match_item(
        self,
        *,
        run: GstReconciliationRun,
        item: GstReconciliationItem,
        tolerance: Gstr2bToleranceConfig,
        user=None,
    ) -> Decimal:
        candidates = self._candidate_queryset(run=run, item=item)
        scored = [self._score_candidate(item=item, candidate=candidate, tolerance=tolerance) for candidate in candidates]
        if not scored:
            return self._apply_result(
                item=item,
                match_status=GstReconciliationItem.MatchStatus.MISSING_IN_BOOKS,
                confidence_score=Decimal("0.00"),
                reasons=[missing_in_books_reason(gstin=item.counterparty_gstin or "", invoice_number=item.invoice_number or "")],
                best_candidate=None,
                user=user,
            )
        scored.sort(key=lambda entry: entry.confidence_score, reverse=True)
        best = scored[0]
        if len(scored) > 1 and (best.confidence_score - scored[1].confidence_score) <= tolerance.candidate_margin_score:
            candidate_ids = [scored[0].candidate.id, scored[1].candidate.id]
            return self._apply_result(
                item=item,
                match_status=GstReconciliationItem.MatchStatus.DUPLICATE,
                confidence_score=best.confidence_score,
                reasons=[multiple_candidates_reason(candidate_ids=candidate_ids), *best.reasons],
                best_candidate=best.candidate,
                user=user,
            )
        if best.confidence_score >= Decimal("90.00") and not any(r.severity == GstMismatchReason.Severity.ERROR for r in best.reasons):
            status = GstReconciliationItem.MatchStatus.MATCHED
        elif best.confidence_score >= Decimal("65.00"):
            status = GstReconciliationItem.MatchStatus.PARTIAL
        else:
            status = GstReconciliationItem.MatchStatus.MISMATCHED
        return self._apply_result(
            item=item,
            match_status=status,
            confidence_score=best.confidence_score,
            reasons=best.reasons,
            best_candidate=best.candidate,
            user=user,
        )

    def _candidate_queryset(self, *, run: GstReconciliationRun, item: GstReconciliationItem):
        qs = PurchaseInvoiceHeader.objects.filter(
            entity_id=run.entity_id,
            entityfinid_id=run.entityfinid_id,
        ).exclude(status=PurchaseInvoiceHeader.Status.CANCELLED)
        if run.subentity_id is None:
            qs = qs.filter(subentity__isnull=True)
        else:
            qs = qs.filter(subentity_id=run.subentity_id)
        gstin = normalize_gstin(item.counterparty_gstin)
        if gstin:
            qs = qs.filter(vendor_gstin__iexact=gstin)
        return list(
            qs.only(
                "id",
                "vendor_gstin",
                "supplier_invoice_number",
                "supplier_invoice_date",
                "total_taxable",
                "total_cgst",
                "total_sgst",
                "total_igst",
                "total_cess",
            )[:100]
        )

    def _score_candidate(
        self,
        *,
        item: GstReconciliationItem,
        candidate: PurchaseInvoiceHeader,
        tolerance: Gstr2bToleranceConfig,
    ) -> CandidateScore:
        score = Decimal("0.00")
        reasons: list[StructuredMismatch] = []

        item_gstin = normalize_gstin(item.counterparty_gstin)
        cand_gstin = normalize_gstin(candidate.vendor_gstin)
        if item_gstin and item_gstin == cand_gstin:
            score += Decimal("35.00")
        else:
            reasons.append(
                field_mismatch_reason(
                    code="GSTIN_MISMATCH",
                    message="Supplier GSTIN does not match purchase invoice vendor GSTIN.",
                    expected=item_gstin,
                    actual=cand_gstin,
                    severity=GstMismatchReason.Severity.ERROR,
                )
            )

        item_inv = normalize_invoice_number(item.invoice_number)
        cand_inv = normalize_invoice_number(candidate.supplier_invoice_number)
        if item_inv and item_inv == cand_inv:
            score += Decimal("35.00")
        else:
            reasons.append(
                field_mismatch_reason(
                    code="INVOICE_NUMBER_MISMATCH",
                    message="Supplier invoice number does not match.",
                    expected=item_inv,
                    actual=cand_inv,
                )
            )

        if item.invoice_date and candidate.supplier_invoice_date:
            day_diff = abs((item.invoice_date - candidate.supplier_invoice_date).days)
            if day_diff == 0:
                score += Decimal("10.00")
            elif day_diff <= tolerance.date_tolerance_days:
                score += Decimal("5.00")
                reasons.append(
                    field_mismatch_reason(
                        code="INVOICE_DATE_TOLERANCE",
                        message="Invoice date matched within configured tolerance.",
                        expected=item.invoice_date,
                        actual=candidate.supplier_invoice_date,
                        severity=GstMismatchReason.Severity.INFO,
                    )
                )
            else:
                reasons.append(
                    field_mismatch_reason(
                        code="INVOICE_DATE_MISMATCH",
                        message="Invoice date differs beyond configured tolerance.",
                        expected=item.invoice_date,
                        actual=candidate.supplier_invoice_date,
                    )
                )

        books_total = (
            Decimal(candidate.total_taxable or 0)
            + Decimal(candidate.total_cgst or 0)
            + Decimal(candidate.total_sgst or 0)
            + Decimal(candidate.total_igst or 0)
            + Decimal(candidate.total_cess or 0)
        ).quantize(Decimal("0.01"))
        imported_total = (
            Decimal(item.taxable_value_imported or 0)
            + Decimal(item.cgst_imported or 0)
            + Decimal(item.sgst_imported or 0)
            + Decimal(item.igst_imported or 0)
            + Decimal(item.cess_imported or 0)
        ).quantize(Decimal("0.01"))
        if decimal_abs_diff(books_total, imported_total) <= tolerance.amount_tolerance:
            score += Decimal("10.00")
        else:
            reasons.append(
                amount_mismatch_reason(
                    code="TOTAL_AMOUNT_MISMATCH",
                    message="Imported total differs from purchase invoice total.",
                    expected=imported_total,
                    actual=books_total,
                    tolerance=tolerance.amount_tolerance,
                )
            )

        if decimal_abs_diff(Decimal(candidate.total_taxable or 0), Decimal(item.taxable_value_imported or 0)) <= tolerance.taxable_tolerance:
            score += Decimal("5.00")
        else:
            reasons.append(
                amount_mismatch_reason(
                    code="TAXABLE_VALUE_MISMATCH",
                    message="Imported taxable value differs from purchase invoice taxable value.",
                    expected=Decimal(item.taxable_value_imported or 0).quantize(Decimal("0.01")),
                    actual=Decimal(candidate.total_taxable or 0).quantize(Decimal("0.01")),
                    tolerance=tolerance.taxable_tolerance,
                )
            )

        component_pairs = [
            ("CGST", Decimal(item.cgst_imported or 0), Decimal(candidate.total_cgst or 0)),
            ("SGST", Decimal(item.sgst_imported or 0), Decimal(candidate.total_sgst or 0)),
            ("IGST", Decimal(item.igst_imported or 0), Decimal(candidate.total_igst or 0)),
            ("CESS", Decimal(item.cess_imported or 0), Decimal(candidate.total_cess or 0)),
        ]
        if all(decimal_abs_diff(expected, actual) <= tolerance.tax_component_tolerance for _, expected, actual in component_pairs):
            score += Decimal("5.00")
        else:
            for label, expected, actual in component_pairs:
                if decimal_abs_diff(expected, actual) > tolerance.tax_component_tolerance:
                    reasons.append(
                        amount_mismatch_reason(
                            code=f"{label}_MISMATCH",
                            message=f"Imported {label} differs from purchase invoice {label}.",
                            expected=expected.quantize(Decimal("0.01")),
                            actual=actual.quantize(Decimal("0.01")),
                            tolerance=tolerance.tax_component_tolerance,
                        )
                    )
        return CandidateScore(candidate=candidate, confidence_score=score.quantize(Decimal("0.01")), reasons=reasons)

    def _apply_result(
        self,
        *,
        item: GstReconciliationItem,
        match_status: str,
        confidence_score: Decimal,
        reasons: list[StructuredMismatch],
        best_candidate: PurchaseInvoiceHeader | None,
        user=None,
    ) -> Decimal:
        item.match_status = match_status
        item.resolution_status = GstReconciliationItemWorkflowService.operational_status_for_match_status(match_status)
        item.match_confidence_score = confidence_score.quantize(Decimal("0.01"))
        item.linked_document_type = "purchase_invoice_header" if best_candidate else None
        item.linked_document_id = str(best_candidate.id) if best_candidate else None
        item.taxable_value_books = Decimal(getattr(best_candidate, "total_taxable", 0) or 0).quantize(Decimal("0.01")) if best_candidate else Decimal("0.00")
        item.cgst_books = Decimal(getattr(best_candidate, "total_cgst", 0) or 0).quantize(Decimal("0.01")) if best_candidate else Decimal("0.00")
        item.sgst_books = Decimal(getattr(best_candidate, "total_sgst", 0) or 0).quantize(Decimal("0.01")) if best_candidate else Decimal("0.00")
        item.igst_books = Decimal(getattr(best_candidate, "total_igst", 0) or 0).quantize(Decimal("0.01")) if best_candidate else Decimal("0.00")
        item.cess_books = Decimal(getattr(best_candidate, "total_cess", 0) or 0).quantize(Decimal("0.01")) if best_candidate else Decimal("0.00")
        item.mismatch_count = len(reasons)
        item.mismatch_summary = [reason.to_summary() for reason in reasons]
        item.updated_by_id = getattr(user, "id", None)
        item.save(
            update_fields=[
                "match_status",
                "resolution_status",
                "match_confidence_score",
                "linked_document_type",
                "linked_document_id",
                "taxable_value_books",
                "cgst_books",
                "sgst_books",
                "igst_books",
                "cess_books",
                "mismatch_count",
                "mismatch_summary",
                "updated_by",
                "updated_at",
            ]
        )
        item.mismatch_reasons.all().delete()
        for reason in reasons:
            GstMismatchReason.objects.create(
                item=item,
                code=reason.code,
                category=reason.category,
                severity=reason.severity,
                message=reason.message,
                details_json=reason.details_json,
                created_by_id=getattr(user, "id", None),
                updated_by_id=getattr(user, "id", None),
            )
        return item.match_confidence_score


MatcherRegistry.register(PortalGstr2bPurchaseMatcher())
