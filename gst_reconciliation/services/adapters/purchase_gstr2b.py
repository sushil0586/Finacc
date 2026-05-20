from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from gst_reconciliation.models import (
    GstImportedReturn,
    GstMismatchReason,
    GstReconciliationActionLog,
    GstReconciliationItem,
    GstReconciliationRun,
)
from gst_reconciliation.services.matching.base import BaseReconciliationMatcher, MatchExecutionResult
from gst_reconciliation.services.matching.registry import MatcherRegistry
from gst_reconciliation.services.normalization import normalize_doc_type, normalize_gstin, normalize_invoice_number
from gst_reconciliation.services.item_workflow_service import GstReconciliationItemWorkflowService
from purchase.models.gstr2b_models import Gstr2bImportBatch, Gstr2bImportRow
from purchase.services.purchase_gstr2b_service import PurchaseGstr2bService


STATUS_MAP = {
    "NOT_CHECKED": GstReconciliationItem.MatchStatus.NOT_CHECKED,
    "MATCHED": GstReconciliationItem.MatchStatus.MATCHED,
    "PARTIAL": GstReconciliationItem.MatchStatus.PARTIAL,
    "MULTIPLE": GstReconciliationItem.MatchStatus.DUPLICATE,
    "NOT_MATCHED": GstReconciliationItem.MatchStatus.MISSING_IN_BOOKS,
    "REVIEWED": GstReconciliationItem.MatchStatus.MANUALLY_RESOLVED,
}


@dataclass(frozen=True)
class PurchaseGstr2bBatchAdapterResult:
    run: GstReconciliationRun
    imported_return: GstImportedReturn
    created: bool


class PurchaseGstr2bBatchAdapter:
    adapter_code = "purchase_gstr2b_batch"

    @staticmethod
    def _summary_for_batch(batch: Gstr2bImportBatch) -> dict:
        total_rows = batch.rows.count()
        return {
            "source": "purchase_gstr2b_batch",
            "batch_id": batch.id,
            "total_rows": total_rows,
        }

    @staticmethod
    def _reason_payload_for_row(row: Gstr2bImportRow) -> tuple[list[dict], int]:
        reasons: list[dict] = []
        count = 0
        if row.match_status == "PARTIAL":
            reasons.append(
                {
                    "code": "PARTIAL_MATCH",
                    "category": "matching",
                    "severity": GstMismatchReason.Severity.WARNING,
                    "message": "Existing purchase GSTR-2B match is partial and needs review.",
                }
            )
            count += 1
        elif row.match_status == "MULTIPLE":
            reasons.append(
                {
                    "code": "MULTIPLE_CANDIDATES",
                    "category": "matching",
                    "severity": GstMismatchReason.Severity.ERROR,
                    "message": "Multiple purchase invoices matched this imported row.",
                }
            )
            count += 1
        elif row.match_status == "NOT_MATCHED":
            reasons.append(
                {
                    "code": "MISSING_IN_BOOKS",
                    "category": "matching",
                    "severity": GstMismatchReason.Severity.ERROR,
                    "message": "Imported GSTR-2B row is missing in books.",
                }
            )
            count += 1
        return reasons, count

    @classmethod
    @transaction.atomic
    def build_run_from_batch(
        cls,
        *,
        batch_id: int,
        user=None,
        match_strategy_code: str = "purchase_gstr2b_existing",
        notes: str | None = None,
    ) -> PurchaseGstr2bBatchAdapterResult:
        batch = (
            Gstr2bImportBatch.objects.select_related("entity", "entityfinid", "subentity")
            .prefetch_related("rows")
            .get(pk=batch_id)
        )
        source_reference = f"purchase.gstr2b.batch:{batch.id}"
        imported_return, _ = GstImportedReturn.objects.get_or_create(
            entity_id=batch.entity_id,
            entityfinid_id=batch.entityfinid_id,
            subentity_id=batch.subentity_id,
            return_type=GstImportedReturn.ReturnType.GSTR2B,
            return_period=batch.period,
            source=GstImportedReturn.Source.ADAPTER,
            source_reference=source_reference,
            defaults={
                "gst_registration_gstin": None,
                "reference": batch.reference or source_reference,
                "status": GstImportedReturn.Status.CONSUMED,
                "normalized_payload_json": cls._summary_for_batch(batch),
                "validation_summary_json": {"adapter_code": cls.adapter_code},
                "imported_by_id": getattr(user, "id", None) or batch.imported_by_id,
                "imported_at": timezone.now(),
                "created_by_id": getattr(user, "id", None),
                "updated_by_id": getattr(user, "id", None),
            },
        )
        run, created = GstReconciliationRun.objects.get_or_create(
            entity_id=batch.entity_id,
            entityfinid_id=batch.entityfinid_id,
            subentity_id=batch.subentity_id,
            gst_registration_gstin=None,
            reconciliation_type=GstReconciliationRun.ReconciliationType.GSTR2B_PURCHASE,
            return_period=batch.period,
            revision_no=1,
            is_active=True,
            defaults={
                "period_type": GstReconciliationRun.PeriodType.MONTHLY,
                "source_mode": GstReconciliationRun.SourceMode.BOOKS_VS_IMPORTED,
                "status": GstReconciliationRun.Status.IMPORTED,
                "match_strategy_code": match_strategy_code or "purchase_gstr2b_existing",
                "imported_return": imported_return,
                "source_reference": source_reference,
                "summary_json": cls._summary_for_batch(batch),
                "notes": notes or "",
                "created_by_id": getattr(user, "id", None),
                "updated_by_id": getattr(user, "id", None),
            },
        )
        if not created:
            run.imported_return = imported_return
            run.match_strategy_code = match_strategy_code or run.match_strategy_code
            run.summary_json = cls._summary_for_batch(batch)
            if notes is not None:
                run.notes = notes
            run.updated_by_id = getattr(user, "id", None)
            run.save(update_fields=["imported_return", "match_strategy_code", "summary_json", "notes", "updated_by", "updated_at"])

        cls._sync_items_from_batch(run=run, batch=batch, user=user)
        GstReconciliationActionLog.objects.create(
            entity_id=run.entity_id,
            entityfinid_id=run.entityfinid_id,
            subentity_id=run.subentity_id,
            run=run,
            action_type=GstReconciliationActionLog.ActionType.IMPORTED,
            actor=user,
            to_status=run.status,
            comment="Run initialized from existing purchase GSTR-2B batch.",
            details_json={"batch_id": batch.id, "created": created, "adapter_code": cls.adapter_code},
            created_by_id=getattr(user, "id", None),
            updated_by_id=getattr(user, "id", None),
        )
        return PurchaseGstr2bBatchAdapterResult(run=run, imported_return=imported_return, created=created)

    @classmethod
    def _sync_items_from_batch(cls, *, run: GstReconciliationRun, batch: Gstr2bImportBatch, user=None) -> None:
        existing_ids = set()
        rows = list(batch.rows.all().order_by("id"))
        for row in rows:
            item, _ = GstReconciliationItem.objects.update_or_create(
                run=run,
                source_document_type="purchase_gstr2b_row",
                source_document_id=str(row.id),
                defaults={
                    "entity_id": run.entity_id,
                    "entityfinid_id": run.entityfinid_id,
                    "subentity_id": run.subentity_id,
                    "item_type": cls._item_type_for_row(row),
                    "direction": GstReconciliationItem.Direction.PURCHASE,
                    "match_key": cls._match_key_for_row(row),
                    "linked_document_type": "purchase_invoice_header" if row.matched_purchase_id else None,
                    "linked_document_id": str(row.matched_purchase_id) if row.matched_purchase_id else None,
                    "gstin": run.gst_registration_gstin,
                    "counterparty_gstin": row.supplier_gstin,
                    "invoice_number": row.supplier_invoice_number,
                    "invoice_date": row.supplier_invoice_date,
                    "doc_type_code": row.doc_type,
                    "taxable_value_imported": row.taxable_value,
                    "cgst_imported": row.cgst,
                    "sgst_imported": row.sgst,
                    "igst_imported": row.igst,
                    "cess_imported": row.cess,
                    "match_status": STATUS_MAP.get(row.match_status, GstReconciliationItem.MatchStatus.NOT_CHECKED),
                    "resolution_status": GstReconciliationItemWorkflowService.operational_status_for_match_status(
                        STATUS_MAP.get(row.match_status, GstReconciliationItem.MatchStatus.NOT_CHECKED)
                    ),
                    "mismatch_summary": [],
                    "mismatch_count": 0,
                    "metadata_json": {
                        "batch_id": batch.id,
                        "row_match_status": row.match_status,
                        "matched_purchase_id": row.matched_purchase_id,
                    },
                    "created_by_id": getattr(user, "id", None),
                    "updated_by_id": getattr(user, "id", None),
                },
            )
            reasons, count = cls._reason_payload_for_row(row)
            item.mismatch_summary = reasons
            item.mismatch_count = count
            item.save(update_fields=["mismatch_summary", "mismatch_count", "updated_at"])
            item.mismatch_reasons.all().delete()
            for reason in reasons:
                GstMismatchReason.objects.create(
                    item=item,
                    code=reason["code"],
                    category=reason["category"],
                    severity=reason["severity"],
                    message=reason["message"],
                    details_json={},
                    created_by_id=getattr(user, "id", None),
                    updated_by_id=getattr(user, "id", None),
                )
            existing_ids.add(item.id)

        if existing_ids:
            run.items.exclude(id__in=existing_ids).delete()
        else:
            run.items.all().delete()
        run.summary_json = cls._build_run_summary(run)
        run.updated_by_id = getattr(user, "id", None)
        run.save(update_fields=["summary_json", "updated_by", "updated_at"])

    @staticmethod
    def _item_type_for_row(row: Gstr2bImportRow) -> str:
        doc_type = normalize_doc_type(row.doc_type)
        if doc_type == "CN":
            return GstReconciliationItem.ItemType.CREDIT_NOTE
        if doc_type == "DN":
            return GstReconciliationItem.ItemType.DEBIT_NOTE
        return GstReconciliationItem.ItemType.INVOICE

    @staticmethod
    def _match_key_for_row(row: Gstr2bImportRow) -> str:
        invoice_no = normalize_invoice_number(row.supplier_invoice_number)
        gstin = normalize_gstin(row.supplier_gstin)
        return f"{gstin}|{invoice_no}"

    @staticmethod
    def _build_run_summary(run: GstReconciliationRun) -> dict:
        qs = run.items.all()
        return {
            "total_items": qs.count(),
            "matched_items": qs.filter(match_status=GstReconciliationItem.MatchStatus.MATCHED).count(),
            "partial_items": qs.filter(match_status=GstReconciliationItem.MatchStatus.PARTIAL).count(),
            "mismatched_items": qs.exclude(
                match_status__in=[
                    GstReconciliationItem.MatchStatus.MATCHED,
                    GstReconciliationItem.MatchStatus.NOT_CHECKED,
                ]
            ).count(),
            "source_reference": run.source_reference,
        }


class PurchaseGstr2bMatcher(BaseReconciliationMatcher):
    code = "purchase_gstr2b_existing"

    def supports(self, run: GstReconciliationRun) -> bool:
        return run.reconciliation_type == GstReconciliationRun.ReconciliationType.GSTR2B_PURCHASE

    @transaction.atomic
    def execute(self, run: GstReconciliationRun, *, user=None) -> MatchExecutionResult:
        if not run.source_reference or not run.source_reference.startswith("purchase.gstr2b.batch:"):
            raise ValueError("This run is not linked to a purchase GSTR-2B batch.")
        batch_id = int(run.source_reference.split(":")[-1])
        PurchaseGstr2bService.auto_match_batch(batch_id=batch_id)
        batch = Gstr2bImportBatch.objects.prefetch_related("rows").get(pk=batch_id)
        PurchaseGstr2bBatchAdapter._sync_items_from_batch(run=run, batch=batch, user=user)
        items = list(run.items.all())
        matched_items = sum(1 for item in items if item.match_status == GstReconciliationItem.MatchStatus.MATCHED)
        partial_items = sum(1 for item in items if item.match_status == GstReconciliationItem.MatchStatus.PARTIAL)
        mismatched_items = sum(
            1
            for item in items
            if item.match_status
            in {
                GstReconciliationItem.MatchStatus.DUPLICATE,
                GstReconciliationItem.MatchStatus.MISMATCHED,
                GstReconciliationItem.MatchStatus.MISSING_IN_BOOKS,
            }
        )
        return MatchExecutionResult(
            run=run,
            processed_items=len(items),
            matched_items=matched_items,
            partial_items=partial_items,
            mismatched_items=mismatched_items,
        )


MatcherRegistry.register(PurchaseGstr2bMatcher())
