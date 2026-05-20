from __future__ import annotations

from collections import Counter

from django.db.models import Count, Q

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

        matched_document_payload = None
        if item.linked_document_type and item.linked_document_id:
            try:
                provider = SourceDocumentProviderRegistry.get_provider(item.linked_document_type)
                document = provider.get_queryset_for_scope(
                    entity_id=item.entity_id,
                    entityfinid_id=item.entityfinid_id,
                    subentity_id=item.subentity_id,
                ).filter(pk=item.linked_document_id).first()
                if document:
                    matched_document_payload = GstSourceDocumentMetadataSerializer(provider.to_metadata(document)).data
            except ValueError:
                matched_document_payload = None

        mismatch_reasons = item.mismatch_reasons.order_by("severity", "code")
        action_logs_qs = item.action_logs.select_related("actor").order_by("-created_at", "-id")
        total_action_logs = action_logs_qs.count()
        action_logs = action_logs_qs[:100]
        return {
            "item": GstReconciliationItemGridSerializer(item).data,
            "imported_portal_row": imported_row_payload,
            "matched_source_document": matched_document_payload,
            "mismatch_reasons": GstMismatchReasonSerializer(mismatch_reasons, many=True).data,
            "action_logs": GstReconciliationActionLogSerializer(action_logs, many=True).data,
            "action_log_meta": {
                "count": total_action_logs,
                "returned_count": min(total_action_logs, 100),
                "has_more": total_action_logs > 100,
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
