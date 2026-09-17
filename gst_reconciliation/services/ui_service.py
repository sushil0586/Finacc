from __future__ import annotations

from collections import Counter

from django.db.models import Count, Q
from posting.models import Entry, EntryStatus, JournalLine, TxnType

from gst_reconciliation.models import (
    GstImportedReturnRow,
    GstReconciliationActionLog,
    GstReconciliationItem,
    GstReconciliationRun,
)
from gst_reconciliation.serializers import (
    GstImportedReturnRowSerializer,
    GstMismatchReasonSerializer,
    GstReconciliationActionLogSerializer,
    GstReconciliationItemGridSerializer,
    GstSourceDocumentMetadataSerializer,
)
from gst_reconciliation.services.source_documents import SourceDocumentProviderRegistry


class GstReconciliationUiService:
    POSTING_TXN_TYPES_BY_SOURCE = {
        "purchase_invoice_header": (
            TxnType.PURCHASE,
            TxnType.PURCHASE_CREDIT_NOTE,
            TxnType.PURCHASE_DEBIT_NOTE,
            TxnType.PURCHASE_RETURN,
        ),
        "sales_invoice_header": (
            TxnType.SALES,
            TxnType.SALES_CREDIT_NOTE,
            TxnType.SALES_DEBIT_NOTE,
            TxnType.SALES_RETURN,
        ),
        "voucher_header": (
            TxnType.JOURNAL,
            TxnType.JOURNAL_CASH,
            TxnType.JOURNAL_BANK,
        ),
    }

    @staticmethod
    def build_item_detail(*, item: GstReconciliationItem) -> dict:
        imported_row_payload = None
        if item.source_document_type == "gst_imported_return_row" and item.source_document_id:
            imported_row = (
                GstImportedReturnRow.objects.select_related("imported_return")
                .filter(pk=item.source_document_id)
                .first()
            )
            if imported_row:
                imported_row_payload = GstImportedReturnRowSerializer(imported_row).data

        source_document_payload = GstReconciliationUiService._build_source_document_metadata(
            source_document_type=item.source_document_type,
            source_document_id=item.source_document_id,
            item=item,
        )
        matched_document_payload = GstReconciliationUiService._build_source_document_metadata(
            source_document_type=item.linked_document_type,
            source_document_id=item.linked_document_id,
            item=item,
        )
        ledger_source_type, ledger_source_id = GstReconciliationUiService._resolve_ledger_source(item=item)
        ledger_impact = GstReconciliationUiService._build_ledger_impact(
            item=item,
            source_document_type=ledger_source_type,
            source_document_id=ledger_source_id,
        )

        mismatch_reasons = item.mismatch_reasons.order_by("severity", "code")
        action_logs_qs = item.action_logs.select_related("actor").order_by("-created_at", "-id")
        total_action_logs = action_logs_qs.count()
        action_logs = action_logs_qs[:100]
        return {
            "item": GstReconciliationItemGridSerializer(item).data,
            "imported_portal_row": imported_row_payload,
            "source_document_evidence": {
                "source_document": source_document_payload,
                "linked_document": matched_document_payload,
                "link_status": GstReconciliationUiService._source_link_status(
                    source_document_payload=source_document_payload,
                    matched_document_payload=matched_document_payload,
                ),
            },
            "matched_source_document": matched_document_payload,
            "ledger_impact": ledger_impact,
            "mismatch_reasons": GstMismatchReasonSerializer(mismatch_reasons, many=True).data,
            "action_logs": GstReconciliationActionLogSerializer(action_logs, many=True).data,
            "action_log_meta": {
                "count": total_action_logs,
                "returned_count": min(total_action_logs, 100),
                "has_more": total_action_logs > 100,
            },
        }

    @staticmethod
    def _build_source_document_metadata(*, source_document_type: str | None, source_document_id: str | None, item: GstReconciliationItem) -> dict | None:
        if not source_document_type or not source_document_id:
            return None
        try:
            provider = SourceDocumentProviderRegistry.get_provider(source_document_type)
            document = provider.get_queryset_for_scope(
                entity_id=item.entity_id,
                entityfinid_id=item.entityfinid_id,
                subentity_id=item.subentity_id,
            ).filter(pk=source_document_id).first()
            if document:
                return GstSourceDocumentMetadataSerializer(provider.to_metadata(document)).data
        except (ValueError, TypeError):
            return None
        return None

    @staticmethod
    def _source_link_status(*, source_document_payload: dict | None, matched_document_payload: dict | None) -> str:
        if source_document_payload and matched_document_payload:
            if (
                source_document_payload.get("source_document_type") == matched_document_payload.get("source_document_type")
                and source_document_payload.get("source_document_id") == matched_document_payload.get("source_document_id")
            ):
                return "same_source_and_linked_document"
            return "source_and_linked_document_available"
        if matched_document_payload:
            return "linked_document_available"
        if source_document_payload:
            return "source_document_available"
        return "no_books_document"

    @staticmethod
    def _resolve_ledger_source(*, item: GstReconciliationItem) -> tuple[str | None, str | None]:
        if item.linked_document_type in GstReconciliationUiService.POSTING_TXN_TYPES_BY_SOURCE and item.linked_document_id:
            return item.linked_document_type, item.linked_document_id
        if item.source_document_type in GstReconciliationUiService.POSTING_TXN_TYPES_BY_SOURCE and item.source_document_id:
            return item.source_document_type, item.source_document_id
        return None, None

    @staticmethod
    def _build_ledger_impact(*, item: GstReconciliationItem, source_document_type: str | None, source_document_id: str | None) -> dict:
        if not source_document_type or not source_document_id:
            return {
                "status": "not_applicable",
                "source_document_type": source_document_type,
                "source_document_id": source_document_id,
                "entries": [],
                "journal_lines": [],
                "totals": {"debit": "0.00", "credit": "0.00", "balanced": True},
            }
        try:
            source_id = int(source_document_id)
        except (TypeError, ValueError):
            return {
                "status": "invalid_source_id",
                "source_document_type": source_document_type,
                "source_document_id": source_document_id,
                "entries": [],
                "journal_lines": [],
                "totals": {"debit": "0.00", "credit": "0.00", "balanced": True},
            }
        txn_types = GstReconciliationUiService.POSTING_TXN_TYPES_BY_SOURCE.get(source_document_type, ())
        lines_qs = (
            JournalLine.objects.select_related("entry", "ledger", "account", "accounthead")
            .filter(
                entity_id=item.entity_id,
                entityfin_id=item.entityfinid_id,
                subentity_id=item.subentity_id,
                txn_id=source_id,
                txn_type__in=txn_types,
            )
            .order_by("entry_id", "id")
        )
        journal_lines = []
        debit_total = 0
        credit_total = 0
        entry_ids = set()
        for line in lines_qs:
            amount = line.amount or 0
            if line.drcr:
                debit_total += amount
            else:
                credit_total += amount
            entry_ids.add(line.entry_id)
            journal_lines.append(
                {
                    "id": line.id,
                    "entry_id": line.entry_id,
                    "txn_type": line.txn_type,
                    "txn_id": line.txn_id,
                    "voucher_no": line.voucher_no,
                    "posting_date": line.posting_date.isoformat() if line.posting_date else None,
                    "side": "DR" if line.drcr else "CR",
                    "amount": str(amount),
                    "ledger_id": line.ledger_id,
                    "ledger_name": getattr(line.ledger, "name", None),
                    "account_id": line.account_id,
                    "account_name": getattr(line.account, "accountname", None),
                    "accounthead_id": line.accounthead_id,
                    "accounthead_name": str(line.accounthead) if line.accounthead_id else None,
                    "description": line.description,
                }
            )
        entries = [
            {
                "id": entry.id,
                "txn_type": entry.txn_type,
                "txn_id": entry.txn_id,
                "voucher_no": entry.voucher_no,
                "voucher_date": entry.voucher_date.isoformat() if entry.voucher_date else None,
                "posting_date": entry.posting_date.isoformat() if entry.posting_date else None,
                "status": EntryStatus(entry.status).label if entry.status in EntryStatus.values else str(entry.status),
                "narration": entry.narration,
            }
            for entry in Entry.objects.filter(pk__in=entry_ids).order_by("posting_date", "id")
        ]
        return {
            "status": "posted" if journal_lines else "no_posting_found",
            "source_document_type": source_document_type,
            "source_document_id": source_document_id,
            "entries": entries,
            "journal_lines": journal_lines,
            "totals": {
                "debit": str(debit_total),
                "credit": str(credit_total),
                "balanced": debit_total == credit_total,
            },
        }

    @staticmethod
    def build_run_list_summary_queryset(queryset):
        return queryset.annotate(
            total_items=Count("items", distinct=True),
            matched_count=Count(
                "items",
                filter=Q(
                    items__resolution_status__in=[
                        GstReconciliationItem.ResolutionStatus.AUTO_MATCHED,
                        GstReconciliationItem.ResolutionStatus.MANUAL_MATCHED,
                    ]
                ),
                distinct=True,
            ),
            pending_review_count=Count(
                "items",
                filter=Q(
                    items__resolution_status__in=[
                        GstReconciliationItem.ResolutionStatus.PENDING_REVIEW,
                        GstReconciliationItem.ResolutionStatus.ASSIGNED,
                        GstReconciliationItem.ResolutionStatus.REOPENED,
                    ]
                ),
                distinct=True,
            ),
            resolved_count=Count(
                "items",
                filter=Q(
                    items__resolution_status__in=[
                        GstReconciliationItem.ResolutionStatus.RESOLVED,
                        GstReconciliationItem.ResolutionStatus.AUTO_MATCHED,
                        GstReconciliationItem.ResolutionStatus.MANUAL_MATCHED,
                        GstReconciliationItem.ResolutionStatus.ACCEPTED_MISMATCH,
                    ]
                ),
                distinct=True,
            ),
            mismatch_count=Count("items", filter=Q(items__resolution_status=GstReconciliationItem.ResolutionStatus.MISMATCH), distinct=True),
            accepted_mismatch_count=Count(
                "items",
                filter=Q(items__resolution_status=GstReconciliationItem.ResolutionStatus.ACCEPTED_MISMATCH),
                distinct=True,
            ),
            ignored_count=Count(
                "items",
                filter=Q(items__resolution_status=GstReconciliationItem.ResolutionStatus.IGNORED),
                distinct=True,
            ),
        )

    @staticmethod
    def build_run_list_row(run: GstReconciliationRun) -> dict:
        total_items = getattr(run, "total_items", 0) or 0
        matched_count = getattr(run, "matched_count", 0) or 0
        pending_review_count = getattr(run, "pending_review_count", 0) or 0
        resolved_count = getattr(run, "resolved_count", 0) or 0
        return {
            "id": run.id,
            "reconciliation_type": run.reconciliation_type,
            "return_period": run.return_period,
            "status": run.status,
            "gst_registration_gstin": run.gst_registration_gstin,
            "entity_id": run.entity_id,
            "entityfinid_id": run.entityfinid_id,
            "subentity_id": run.subentity_id,
            "source_mode": run.source_mode,
            "imported_return_id": run.imported_return_id,
            "total_items": total_items,
            "matched_count": matched_count,
            "pending_review_count": pending_review_count,
            "resolved_count": resolved_count,
            "mismatch_count": getattr(run, "mismatch_count", 0) or 0,
            "accepted_mismatch_count": getattr(run, "accepted_mismatch_count", 0) or 0,
            "ignored_count": getattr(run, "ignored_count", 0) or 0,
            "match_percentage": round((matched_count / total_items) * 100, 2) if total_items else 0.0,
            "run_health": {
                "progress_percentage": round((resolved_count / total_items) * 100, 2) if total_items else 0.0,
                "has_unresolved": pending_review_count > 0,
                "status_tone": "healthy" if pending_review_count == 0 else "attention",
            },
            "created_at": run.created_at,
            "updated_at": run.updated_at,
        }

    @staticmethod
    def build_reviewer_queue_summary(*, queryset) -> dict:
        totals = queryset.aggregate(
            total_rows=Count("id"),
            assigned_rows=Count("id", filter=Q(assigned_reviewer__isnull=False)),
            unassigned_rows=Count("id", filter=Q(assigned_reviewer__isnull=True)),
        )
        by_reviewer = queryset.filter(assigned_reviewer__isnull=False).values("assigned_reviewer_id").annotate(item_count=Count("id")).order_by("-item_count", "assigned_reviewer_id")
        return {
            "total_rows": totals["total_rows"] or 0,
            "assigned_rows": totals["assigned_rows"] or 0,
            "unassigned_rows": totals["unassigned_rows"] or 0,
            "reviewer_counts": [
                {"reviewer_id": row["assigned_reviewer_id"], "item_count": row["item_count"]}
                for row in by_reviewer
            ],
        }
