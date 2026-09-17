from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db.models import Q
from django.db import transaction

from gst_reconciliation.models import GstMismatchReason, GstReconciliationItem, GstReconciliationRun
from gst_reconciliation.models.imported_returns import GstImportedReturnRow
from gst_reconciliation.services.matching.base import BaseReconciliationMatcher, MatchExecutionResult
from gst_reconciliation.services.matching.reasons import (
    StructuredMismatch,
    amount_mismatch_reason,
    field_mismatch_reason,
    missing_in_books_reason,
    missing_in_return_reason,
    multiple_candidates_reason,
    portal_context_reason,
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
    REVIEW_CONTEXT_CODES = {
        "PORTAL_ROW_AMENDED",
        "PORTAL_ROW_VENDOR_REVISED",
        "IMS_ACTION_PENDING",
        "IMS_ACTION_REJECTED",
    }

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
        missing_in_return_items = self._create_missing_in_return_items(run=run, user=user)
        mismatched += missing_in_return_items
        items_count = len(items) + missing_in_return_items
        average_confidence = (confidence_total / Decimal(len(items or [1]))).quantize(Decimal("0.01")) if items else Decimal("0.00")
        context_summary = self._portal_context_summary(run=run)
        run.summary_json = {
            **(run.summary_json or {}),
            "match_confidence_average": str(average_confidence),
            "missing_in_return_items": missing_in_return_items,
            "portal_context_summary": context_summary,
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
            processed_items=items_count,
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
        portal_context = self._portal_context_for_item(item=item)
        portal_reasons = self._portal_context_reasons(portal_context=portal_context)
        candidates = self._candidate_queryset(run=run, item=item)
        scored = [self._score_candidate(item=item, candidate=candidate, tolerance=tolerance) for candidate in candidates]
        if not scored:
            return self._apply_result(
                item=item,
                match_status=GstReconciliationItem.MatchStatus.MISSING_IN_BOOKS,
                confidence_score=Decimal("0.00"),
                reasons=[
                    missing_in_books_reason(gstin=item.counterparty_gstin or "", invoice_number=item.invoice_number or ""),
                    *portal_reasons,
                ],
                best_candidate=None,
                portal_context=portal_context,
                user=user,
            )
        scored.sort(key=lambda entry: entry.confidence_score, reverse=True)
        best = scored[0]
        best_reasons = [*portal_reasons, *best.reasons]
        if len(scored) > 1 and (best.confidence_score - scored[1].confidence_score) <= tolerance.candidate_margin_score:
            candidate_ids = [scored[0].candidate.id, scored[1].candidate.id]
            return self._apply_result(
                item=item,
                match_status=GstReconciliationItem.MatchStatus.DUPLICATE,
                confidence_score=best.confidence_score,
                reasons=[multiple_candidates_reason(candidate_ids=candidate_ids), *best_reasons],
                best_candidate=best.candidate,
                portal_context=portal_context,
                user=user,
            )
        review_required = any(reason.code in self.REVIEW_CONTEXT_CODES for reason in best_reasons)
        if best.confidence_score >= Decimal("90.00") and not any(r.severity == GstMismatchReason.Severity.ERROR for r in best_reasons) and not review_required:
            status = GstReconciliationItem.MatchStatus.MATCHED
        elif best.confidence_score >= Decimal("65.00"):
            status = GstReconciliationItem.MatchStatus.PARTIAL
        else:
            status = GstReconciliationItem.MatchStatus.MISMATCHED
        return self._apply_result(
            item=item,
            match_status=status,
            confidence_score=best.confidence_score,
            reasons=best_reasons,
            best_candidate=best.candidate,
            portal_context=portal_context,
            user=user,
        )

    def _portal_context_summary(self, *, run: GstReconciliationRun) -> dict:
        summary = {
            "amended_rows": 0,
            "vendor_revised_rows": 0,
            "ims_rows": 0,
            "ims_pending_rows": 0,
            "ims_rejected_rows": 0,
        }
        for item in run.items.filter(source_document_type="gst_imported_return_row", source_document_id__regex=r"^\d+$"):
            context = self._portal_context_for_item(item=item)
            flags = context.get("flags") or {}
            if flags.get("is_amended"):
                summary["amended_rows"] += 1
            if flags.get("is_vendor_revised"):
                summary["vendor_revised_rows"] += 1
            if flags.get("is_ims"):
                summary["ims_rows"] += 1
            if flags.get("ims_action") == "PENDING":
                summary["ims_pending_rows"] += 1
            if flags.get("ims_action") == "REJECTED":
                summary["ims_rejected_rows"] += 1
        return summary

    def _portal_context_for_item(self, *, item: GstReconciliationItem) -> dict:
        context = {
            "source_document_type": item.source_document_type,
            "source_document_id": item.source_document_id,
            "source_section": None,
            "source_row_reference": None,
            "flags": {
                "is_amended": False,
                "is_vendor_revised": False,
                "is_ims": False,
                "ims_action": None,
            },
        }
        if item.source_document_type != "gst_imported_return_row" or not str(item.source_document_id or "").isdigit():
            return context
        row = GstImportedReturnRow.objects.filter(pk=item.source_document_id).first()
        if not row:
            return context
        raw = row.raw_row_json or {}
        normalized = row.normalized_row_json or {}
        source_section = row.source_section or raw.get("source_section") or raw.get("section") or raw.get("table")
        context["source_section"] = source_section
        context["source_row_reference"] = row.source_row_reference
        tokens = " ".join(
            str(value or "")
            for value in [
                source_section,
                row.source_row_reference,
                raw.get("source"),
                raw.get("source_type"),
                raw.get("section"),
                raw.get("table"),
                raw.get("ims_status"),
                raw.get("ims_action"),
                raw.get("action"),
                raw.get("action_status"),
                raw.get("supplier_action"),
                raw.get("vendor_action"),
                raw.get("status"),
                raw.get("row_type"),
                raw.get("amendment_type"),
                normalized.get("source_section"),
            ]
        ).upper()
        is_amended = any(marker in tokens for marker in ("AMEND", "B2BA", "CDNA", "CDNRA", "REVISED"))
        is_vendor_revised = any(marker in tokens for marker in ("VENDOR_REVISED", "SUPPLIER_REVISED", "SUPPLIER REVISED", "VENDOR REVISED", "REVISED_BY_SUPPLIER"))
        is_ims = "IMS" in tokens
        ims_action = self._normalize_ims_action(raw)
        context["flags"] = {
            "is_amended": is_amended,
            "is_vendor_revised": is_vendor_revised,
            "is_ims": is_ims or ims_action is not None,
            "ims_action": ims_action,
        }
        return context

    def _normalize_ims_action(self, raw: dict) -> str | None:
        for key in ("ims_action", "ims_status", "action", "action_status", "supplier_action", "vendor_action", "status"):
            value = str(raw.get(key) or "").strip().upper().replace(" ", "_")
            if not value:
                continue
            if value in {"ACCEPT", "ACCEPTED", "A"}:
                return "ACCEPTED"
            if value in {"PENDING", "NO_ACTION", "NO_ACTION_TAKEN", "N"}:
                return "PENDING"
            if value in {"REJECT", "REJECTED", "R"}:
                return "REJECTED"
        return None

    def _portal_context_reasons(self, *, portal_context: dict) -> list[StructuredMismatch]:
        flags = portal_context.get("flags") or {}
        details = {
            "source_section": portal_context.get("source_section"),
            "source_row_reference": portal_context.get("source_row_reference"),
            **flags,
        }
        reasons: list[StructuredMismatch] = []
        if flags.get("is_amended"):
            reasons.append(
                portal_context_reason(
                    code="PORTAL_ROW_AMENDED",
                    message="Portal row is marked as amended/revised and needs reviewer confirmation before ITC treatment is finalized.",
                    details=details,
                )
            )
        if flags.get("is_vendor_revised"):
            reasons.append(
                portal_context_reason(
                    code="PORTAL_ROW_VENDOR_REVISED",
                    message="Supplier/vendor revised this portal row; verify the books document and ITC decision.",
                    details=details,
                )
            )
        ims_action = flags.get("ims_action")
        if ims_action == "PENDING":
            reasons.append(
                portal_context_reason(
                    code="IMS_ACTION_PENDING",
                    message="IMS action is pending for this inward supply.",
                    details=details,
                )
            )
        elif ims_action == "REJECTED":
            reasons.append(
                portal_context_reason(
                    code="IMS_ACTION_REJECTED",
                    message="IMS action is rejected; ITC should not auto-claim without review.",
                    details=details,
                )
            )
        elif flags.get("is_ims") and ims_action == "ACCEPTED":
            reasons.append(
                portal_context_reason(
                    code="IMS_ACTION_ACCEPTED",
                    message="IMS action is accepted for this inward supply.",
                    details=details,
                    severity=GstMismatchReason.Severity.INFO,
                )
            )
        return reasons

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
                "doc_type",
                "vendor_gstin",
                "vendor_name",
                "supplier_invoice_number",
                "supplier_invoice_date",
                "bill_date",
                "total_taxable",
                "total_cgst",
                "total_sgst",
                "total_igst",
                "total_cess",
                "grand_total",
            )[:100]
        )

    def _books_candidate_queryset(self, *, run: GstReconciliationRun):
        qs = PurchaseInvoiceHeader.objects.filter(
            entity_id=run.entity_id,
            entityfinid_id=run.entityfinid_id,
        ).exclude(
            status=PurchaseInvoiceHeader.Status.CANCELLED
        ).exclude(
            vendor_gstin__in=["", None]
        ).exclude(
            vendor__compliance_profile__gstregtype__iexact="Composition"
        ).exclude(
            supply_category__in=[
                PurchaseInvoiceHeader.SupplyCategory.IMPORT_GOODS,
                PurchaseInvoiceHeader.SupplyCategory.IMPORT_SERVICES,
            ]
        )
        if run.subentity_id is None:
            qs = qs.filter(subentity__isnull=True)
        else:
            qs = qs.filter(subentity_id=run.subentity_id)
        period_from, period_to = self._run_period_dates(run)
        if period_from and period_to:
            qs = qs.filter(
                Q(supplier_invoice_date__range=(period_from, period_to))
                | Q(supplier_invoice_date__isnull=True, bill_date__range=(period_from, period_to))
            )
        return qs.only(
            "id",
            "doc_type",
            "vendor_gstin",
            "vendor_name",
            "supplier_invoice_number",
            "supplier_invoice_date",
            "bill_date",
            "purchase_number",
            "total_taxable",
            "total_cgst",
            "total_sgst",
            "total_igst",
            "total_cess",
            "grand_total",
        )

    def _run_period_dates(self, run: GstReconciliationRun) -> tuple[date | None, date | None]:
        if run.period_from and run.period_to:
            return run.period_from, run.period_to
        try:
            year_text, month_text = str(run.return_period or "").split("-", 1)
            year = int(year_text)
            month = int(month_text)
            start = date(year, month, 1)
            end = date(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 1)
            return start, date.fromordinal(end.toordinal() - 1)
        except Exception:
            return None, None

    def _create_missing_in_return_items(self, *, run: GstReconciliationRun, user=None) -> int:
        linked_purchase_ids = set(
            run.items.filter(linked_document_type="purchase_invoice_header", linked_document_id__regex=r"^\d+$")
            .values_list("linked_document_id", flat=True)
        )
        existing_books_item_ids = set(
            run.items.filter(source_document_type="purchase_invoice_header", source_document_id__regex=r"^\d+$")
            .values_list("source_document_id", flat=True)
        )
        excluded_ids = {int(value) for value in linked_purchase_ids | existing_books_item_ids if value}
        created = 0
        for purchase in self._books_candidate_queryset(run=run).exclude(id__in=excluded_ids).order_by("supplier_invoice_date", "bill_date", "id"):
            reason = missing_in_return_reason(
                gstin=normalize_gstin(purchase.vendor_gstin) or "",
                invoice_number=purchase.supplier_invoice_number or purchase.purchase_number or "",
                purchase_invoice_id=purchase.id,
            )
            item, was_created = GstReconciliationItem.objects.update_or_create(
                run=run,
                source_document_type="purchase_invoice_header",
                source_document_id=str(purchase.id),
                defaults={
                    "entity_id": run.entity_id,
                    "entityfinid_id": run.entityfinid_id,
                    "subentity_id": run.subentity_id,
                    "item_type": self._purchase_item_type(purchase),
                    "direction": GstReconciliationItem.Direction.PURCHASE,
                    "match_key": f"BOOKS|{purchase.id}",
                    "gstin": run.gst_registration_gstin,
                    "counterparty_gstin": normalize_gstin(purchase.vendor_gstin),
                    "invoice_number": purchase.supplier_invoice_number or purchase.purchase_number,
                    "invoice_date": purchase.supplier_invoice_date or purchase.bill_date,
                    "doc_type_code": self._purchase_doc_type_code(purchase),
                    "linked_document_type": "purchase_invoice_header",
                    "linked_document_id": str(purchase.id),
                    "taxable_value_books": Decimal(purchase.total_taxable or 0).quantize(Decimal("0.01")),
                    "cgst_books": Decimal(purchase.total_cgst or 0).quantize(Decimal("0.01")),
                    "sgst_books": Decimal(purchase.total_sgst or 0).quantize(Decimal("0.01")),
                    "igst_books": Decimal(purchase.total_igst or 0).quantize(Decimal("0.01")),
                    "cess_books": Decimal(purchase.total_cess or 0).quantize(Decimal("0.01")),
                    "taxable_value_imported": Decimal("0.00"),
                    "cgst_imported": Decimal("0.00"),
                    "sgst_imported": Decimal("0.00"),
                    "igst_imported": Decimal("0.00"),
                    "cess_imported": Decimal("0.00"),
                    "match_status": GstReconciliationItem.MatchStatus.MISSING_IN_RETURN,
                    "resolution_status": GstReconciliationItem.ResolutionStatus.MISMATCH,
                    "match_confidence_score": Decimal("0.00"),
                    "mismatch_count": 1,
                    "mismatch_summary": [reason.to_summary()],
                    "updated_by_id": getattr(user, "id", None),
                },
            )
            if was_created:
                item.created_by_id = getattr(user, "id", None)
                item.save(update_fields=["created_by", "updated_at"])
                created += 1
            item.mismatch_reasons.all().delete()
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
        return created

    def _purchase_item_type(self, purchase: PurchaseInvoiceHeader) -> str:
        if purchase.doc_type == PurchaseInvoiceHeader.DocType.CREDIT_NOTE:
            return GstReconciliationItem.ItemType.CREDIT_NOTE
        if purchase.doc_type == PurchaseInvoiceHeader.DocType.DEBIT_NOTE:
            return GstReconciliationItem.ItemType.DEBIT_NOTE
        return GstReconciliationItem.ItemType.INVOICE

    def _purchase_doc_type_code(self, purchase: PurchaseInvoiceHeader) -> str:
        if purchase.doc_type == PurchaseInvoiceHeader.DocType.CREDIT_NOTE:
            return "CN"
        if purchase.doc_type == PurchaseInvoiceHeader.DocType.DEBIT_NOTE:
            return "DN"
        return "INV"

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
        portal_context: dict | None = None,
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
        metadata_json = item.metadata_json or {}
        if portal_context:
            metadata_json["portal_context"] = portal_context
        item.metadata_json = metadata_json
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
                "metadata_json",
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
