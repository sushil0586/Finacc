from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from django.db import transaction
from django.utils import timezone

from gst_reconciliation.models import (
    GstMismatchReason,
    GstReconciliationActionLog,
    GstReconciliationItem,
    GstReconciliationRun,
)
from gst_reconciliation.services.access import GstReconciliationWorkflowAccess
from gst_reconciliation.services.performance import timed_call
from gst_reconciliation.services.source_documents import SourceDocumentProviderRegistry


@dataclass(frozen=True)
class BulkActionResult:
    action: str
    processed_item_ids: list[int]


class GstReconciliationItemWorkflowService:
    MUTABLE_RUN_STATUSES = {
        GstReconciliationRun.Status.DRAFT,
        GstReconciliationRun.Status.IMPORTED,
        GstReconciliationRun.Status.MATCHING,
        GstReconciliationRun.Status.READY_FOR_REVIEW,
        GstReconciliationRun.Status.IN_REVIEW,
        GstReconciliationRun.Status.APPROVED,
        GstReconciliationRun.Status.REJECTED,
        GstReconciliationRun.Status.FAILED,
    }

    @classmethod
    def _assert_run_is_mutable(cls, *, item: GstReconciliationItem) -> None:
        if item.run.status not in cls.MUTABLE_RUN_STATUSES:
            raise ValueError("Closed GST reconciliation runs cannot be modified.")

    @staticmethod
    def operational_status_for_match_status(match_status: str) -> str:
        mapping = {
            GstReconciliationItem.MatchStatus.MATCHED: GstReconciliationItem.ResolutionStatus.AUTO_MATCHED,
            GstReconciliationItem.MatchStatus.MANUALLY_RESOLVED: GstReconciliationItem.ResolutionStatus.MANUAL_MATCHED,
            GstReconciliationItem.MatchStatus.PARTIAL: GstReconciliationItem.ResolutionStatus.PARTIAL_MATCH,
            GstReconciliationItem.MatchStatus.MISMATCHED: GstReconciliationItem.ResolutionStatus.MISMATCH,
            GstReconciliationItem.MatchStatus.MISSING_IN_BOOKS: GstReconciliationItem.ResolutionStatus.MISMATCH,
            GstReconciliationItem.MatchStatus.MISSING_IN_RETURN: GstReconciliationItem.ResolutionStatus.MISMATCH,
            GstReconciliationItem.MatchStatus.DUPLICATE: GstReconciliationItem.ResolutionStatus.MISMATCH,
            GstReconciliationItem.MatchStatus.IGNORED: GstReconciliationItem.ResolutionStatus.IGNORED,
        }
        return mapping.get(match_status, GstReconciliationItem.ResolutionStatus.PENDING_REVIEW)

    @staticmethod
    def _log(
        *,
        item: GstReconciliationItem,
        user,
        action_type: str,
        comment: str | None = None,
        from_status: str | None = None,
        to_status: str | None = None,
        details_json: dict | None = None,
    ) -> None:
        GstReconciliationActionLog.objects.create(
            entity_id=item.entity_id,
            entityfinid_id=item.entityfinid_id,
            subentity_id=item.subentity_id,
            run=item.run,
            item=item,
            action_type=action_type,
            actor=user,
            from_status=from_status,
            to_status=to_status,
            comment=comment,
            details_json=details_json or {},
            created_by_id=getattr(user, "id", None),
            updated_by_id=getattr(user, "id", None),
        )

    @staticmethod
    def _touch_run(*, item: GstReconciliationItem, user) -> None:
        GstReconciliationRun.objects.filter(pk=item.run_id).update(updated_by=user, updated_at=timezone.now())

    @classmethod
    @transaction.atomic
    def assign_reviewer(cls, *, item: GstReconciliationItem, reviewer, user, note: str | None = None) -> GstReconciliationItem:
        cls._assert_run_is_mutable(item=item)
        GstReconciliationWorkflowAccess.assert_can_assign_item(user=user, item=item)
        old_status = item.resolution_status
        item.assigned_reviewer = reviewer
        item.assigned_by = user
        item.assigned_at = timezone.now()
        item.reviewer_note = note or item.reviewer_note
        item.resolution_status = GstReconciliationItem.ResolutionStatus.ASSIGNED
        item.updated_by = user
        item.save(update_fields=["assigned_reviewer", "assigned_by", "assigned_at", "reviewer_note", "resolution_status", "updated_by", "updated_at"])
        cls._log(
            item=item,
            user=user,
            action_type=GstReconciliationActionLog.ActionType.ITEM_ASSIGNED,
            comment=note,
            from_status=old_status,
            to_status=item.resolution_status,
            details_json={
                "assigned_reviewer_id": reviewer.id if reviewer else None,
                "assigned_by_id": getattr(user, "id", None),
            },
        )
        cls._touch_run(item=item, user=user)
        return item

    @classmethod
    @transaction.atomic
    def manual_match_source_document(
        cls,
        *,
        item: GstReconciliationItem,
        source_document_type: str,
        source_document_id: str,
        user,
        note: str | None = None,
    ) -> GstReconciliationItem:
        cls._assert_run_is_mutable(item=item)
        GstReconciliationWorkflowAccess.assert_can_manual_match(user=user, item=item)
        provider = SourceDocumentProviderRegistry.get_provider(source_document_type)
        document = provider.get_document_for_item(item=item, document_id=source_document_id)
        metadata = provider.to_metadata(document)
        old_match = item.match_status
        old_resolution = item.resolution_status
        old_link = item.linked_document_id
        item.linked_document_type = metadata.source_document_type
        item.linked_document_id = metadata.source_document_id
        item.match_status = GstReconciliationItem.MatchStatus.MANUALLY_RESOLVED
        item.resolution_status = GstReconciliationItem.ResolutionStatus.MANUAL_MATCHED
        item.match_confidence_score = Decimal("100.00")
        item.reviewer_note = note or item.reviewer_note
        item.resolution_note = note or item.resolution_note
        item.reviewed_by = user
        item.reviewed_at = timezone.now()
        item.resolved_by = user
        item.resolved_at = timezone.now()
        item.updated_by = user
        item.save(
            update_fields=[
                "linked_document_type",
                "linked_document_id",
                "match_status",
                "resolution_status",
                "match_confidence_score",
                "reviewer_note",
                "resolution_note",
                "reviewed_by",
                "reviewed_at",
                "resolved_by",
                "resolved_at",
                "updated_by",
                "updated_at",
            ]
        )
        cls._log(
            item=item,
            user=user,
            action_type=GstReconciliationActionLog.ActionType.ITEM_MANUAL_MATCHED,
            comment=note,
            from_status=old_resolution,
            to_status=item.resolution_status,
            details_json={
                "provider_code": metadata.provider_code,
                "source_document_type": metadata.source_document_type,
                "old_linked_document_id": old_link,
                "new_linked_document_id": item.linked_document_id,
                "old_match_status": old_match,
                "new_match_status": item.match_status,
                "normalized_comparison_payload": metadata.normalized_comparison_payload,
            },
        )
        cls._touch_run(item=item, user=user)
        return item

    @classmethod
    @transaction.atomic
    def manual_unmatch(cls, *, item: GstReconciliationItem, user, note: str | None = None) -> GstReconciliationItem:
        cls._assert_run_is_mutable(item=item)
        GstReconciliationWorkflowAccess.assert_can_review_item(user=user, item=item)
        old_match = item.match_status
        old_resolution = item.resolution_status
        old_link_type = item.linked_document_type
        old_link = item.linked_document_id
        item.linked_document_type = None
        item.linked_document_id = None
        item.match_status = GstReconciliationItem.MatchStatus.NOT_CHECKED
        item.resolution_status = GstReconciliationItem.ResolutionStatus.PENDING_REVIEW
        item.match_confidence_score = Decimal("0.00")
        item.reviewer_note = note or item.reviewer_note
        item.reviewed_by = None
        item.reviewed_at = None
        item.resolved_by = None
        item.resolved_at = None
        item.updated_by = user
        item.save(
            update_fields=[
                "linked_document_type",
                "linked_document_id",
                "match_status",
                "resolution_status",
                "match_confidence_score",
                "reviewer_note",
                "reviewed_by",
                "reviewed_at",
                "resolved_by",
                "resolved_at",
                "updated_by",
                "updated_at",
            ]
        )
        cls._log(
            item=item,
            user=user,
            action_type=GstReconciliationActionLog.ActionType.ITEM_UNMATCHED,
            comment=note,
            from_status=old_resolution,
            to_status=item.resolution_status,
            details_json={
                "old_linked_document_type": old_link_type,
                "old_linked_document_id": old_link,
                "old_match_status": old_match,
                "new_match_status": item.match_status,
            },
        )
        cls._touch_run(item=item, user=user)
        return item

    @classmethod
    @transaction.atomic
    def ignore_item(cls, *, item: GstReconciliationItem, user, note: str | None = None) -> GstReconciliationItem:
        cls._assert_run_is_mutable(item=item)
        GstReconciliationWorkflowAccess.assert_can_review_item(user=user, item=item)
        if not (note or "").strip():
            raise ValueError("Ignore note is required.")
        old_resolution = item.resolution_status
        old_match = item.match_status
        item.resolution_status = GstReconciliationItem.ResolutionStatus.IGNORED
        item.match_status = GstReconciliationItem.MatchStatus.IGNORED
        item.reviewer_note = note or item.reviewer_note
        item.resolution_note = note or item.resolution_note
        item.reviewed_by = user
        item.reviewed_at = timezone.now()
        item.updated_by = user
        item.save(update_fields=["resolution_status", "match_status", "reviewer_note", "resolution_note", "reviewed_by", "reviewed_at", "updated_by", "updated_at"])
        cls._log(
            item=item,
            user=user,
            action_type=GstReconciliationActionLog.ActionType.ITEM_IGNORED,
            comment=note,
            from_status=old_resolution,
            to_status=item.resolution_status,
            details_json={"old_match_status": old_match, "new_match_status": item.match_status},
        )
        cls._touch_run(item=item, user=user)
        return item

    @classmethod
    @transaction.atomic
    def reopen_item(cls, *, item: GstReconciliationItem, user, note: str | None = None) -> GstReconciliationItem:
        cls._assert_run_is_mutable(item=item)
        GstReconciliationWorkflowAccess.assert_can_review_item(user=user, item=item)
        old_resolution = item.resolution_status
        item.resolution_status = GstReconciliationItem.ResolutionStatus.REOPENED
        item.reviewer_note = note or item.reviewer_note
        item.reviewed_by = None
        item.reviewed_at = None
        item.resolved_by = None
        item.resolved_at = None
        item.updated_by = user
        item.save(update_fields=["resolution_status", "reviewer_note", "reviewed_by", "reviewed_at", "resolved_by", "resolved_at", "updated_by", "updated_at"])
        cls._log(
            item=item,
            user=user,
            action_type=GstReconciliationActionLog.ActionType.ITEM_REOPENED,
            comment=note,
            from_status=old_resolution,
            to_status=item.resolution_status,
        )
        cls._touch_run(item=item, user=user)
        return item

    @classmethod
    @transaction.atomic
    def accept_mismatch(cls, *, item: GstReconciliationItem, user, note: str | None = None) -> GstReconciliationItem:
        cls._assert_run_is_mutable(item=item)
        GstReconciliationWorkflowAccess.assert_can_review_item(user=user, item=item)
        old_resolution = item.resolution_status
        if not (note or "").strip():
            raise ValueError("Accepted mismatch note is required.")
        item.resolution_status = GstReconciliationItem.ResolutionStatus.ACCEPTED_MISMATCH
        item.reviewer_note = note or item.reviewer_note
        item.resolution_note = note or item.resolution_note
        item.accepted_mismatch_by = user
        item.accepted_mismatch_at = timezone.now()
        item.reviewed_by = user
        item.reviewed_at = timezone.now()
        item.resolved_by = user
        item.resolved_at = timezone.now()
        item.updated_by = user
        item.save(
            update_fields=[
                "resolution_status",
                "reviewer_note",
                "resolution_note",
                "accepted_mismatch_by",
                "accepted_mismatch_at",
                "reviewed_by",
                "reviewed_at",
                "resolved_by",
                "resolved_at",
                "updated_by",
                "updated_at",
            ]
        )
        cls._log(
            item=item,
            user=user,
            action_type=GstReconciliationActionLog.ActionType.ITEM_ACCEPTED_MISMATCH,
            comment=note,
            from_status=old_resolution,
            to_status=item.resolution_status,
            details_json={"current_match_status": item.match_status},
        )
        cls._touch_run(item=item, user=user)
        return item

    @classmethod
    @transaction.atomic
    def update_notes(
        cls,
        *,
        item: GstReconciliationItem,
        user,
        reviewer_notes: str | None = None,
        resolution_notes: str | None = None,
    ) -> GstReconciliationItem:
        cls._assert_run_is_mutable(item=item)
        GstReconciliationWorkflowAccess.assert_can_review_item(user=user, item=item)
        item.reviewer_note = reviewer_notes if reviewer_notes is not None else item.reviewer_note
        item.resolution_note = resolution_notes if resolution_notes is not None else item.resolution_note
        item.updated_by = user
        item.save(update_fields=["reviewer_note", "resolution_note", "updated_by", "updated_at"])
        cls._log(
            item=item,
            user=user,
            action_type=GstReconciliationActionLog.ActionType.NOTE,
            comment=reviewer_notes or resolution_notes,
            from_status=item.resolution_status,
            to_status=item.resolution_status,
            details_json={"reviewer_notes": item.reviewer_note, "resolution_notes": item.resolution_note},
        )
        cls._touch_run(item=item, user=user)
        return item

    @classmethod
    @transaction.atomic
    def mark_reviewed(cls, *, item: GstReconciliationItem, user, note: str | None = None) -> GstReconciliationItem:
        cls._assert_run_is_mutable(item=item)
        GstReconciliationWorkflowAccess.assert_can_review_item(user=user, item=item)
        old_resolution = item.resolution_status
        item.reviewed_by = user
        item.reviewed_at = timezone.now()
        if item.match_status == GstReconciliationItem.MatchStatus.MATCHED:
            item.resolution_status = GstReconciliationItem.ResolutionStatus.AUTO_MATCHED
        elif item.match_status == GstReconciliationItem.MatchStatus.MANUALLY_RESOLVED:
            item.resolution_status = GstReconciliationItem.ResolutionStatus.MANUAL_MATCHED
        elif item.match_status == GstReconciliationItem.MatchStatus.PARTIAL:
            item.resolution_status = GstReconciliationItem.ResolutionStatus.PARTIAL_MATCH
        elif item.match_status in {
            GstReconciliationItem.MatchStatus.MISMATCHED,
            GstReconciliationItem.MatchStatus.MISSING_IN_BOOKS,
            GstReconciliationItem.MatchStatus.MISSING_IN_RETURN,
            GstReconciliationItem.MatchStatus.DUPLICATE,
        }:
            item.resolution_status = GstReconciliationItem.ResolutionStatus.MISMATCH
        else:
            item.resolution_status = GstReconciliationItem.ResolutionStatus.RESOLVED
        item.reviewer_note = note or item.reviewer_note
        item.updated_by = user
        item.save(update_fields=["reviewed_by", "reviewed_at", "resolution_status", "reviewer_note", "updated_by", "updated_at"])
        cls._log(
            item=item,
            user=user,
            action_type=GstReconciliationActionLog.ActionType.ITEM_RESOLVED,
            comment=note,
            from_status=old_resolution,
            to_status=item.resolution_status,
            details_json={"match_status": item.match_status},
        )
        cls._touch_run(item=item, user=user)
        return item

    @classmethod
    @transaction.atomic
    def bulk_action(
        cls,
        *,
        items: Iterable[GstReconciliationItem],
        action: str,
        user,
        note: str | None = None,
        reviewer=None,
    ) -> tuple[BulkActionResult, list[dict]]:
        items = list(items)
        processed_ids: list[int] = []
        errors: list[dict] = []
        if not items:
            return BulkActionResult(action=action, processed_item_ids=processed_ids), errors
        GstReconciliationWorkflowAccess.assert_can_bulk_review(user=user, run=items[0].run)
        def _process_items():
            for item in items:
                try:
                    cls._assert_run_is_mutable(item=item)
                    if action == "assign":
                        if reviewer is None:
                            raise ValueError("reviewer is required for bulk assign.")
                        cls.assign_reviewer(item=item, reviewer=reviewer, user=user, note=note)
                    elif action == "ignore":
                        cls.ignore_item(item=item, user=user, note=note)
                    elif action == "reopen":
                        cls.reopen_item(item=item, user=user, note=note)
                    elif action == "accept_mismatch":
                        cls.accept_mismatch(item=item, user=user, note=note)
                    elif action == "mark_reviewed":
                        cls.mark_reviewed(item=item, user=user, note=note)
                    elif action == "unmatch":
                        cls.manual_unmatch(item=item, user=user, note=note)
                    else:
                        raise ValueError("Unsupported bulk reconciliation action.")
                    processed_ids.append(item.id)
                except Exception as exc:
                    errors.append({"item_id": item.id, "error": str(exc)})

        timed = timed_call(
            "bulk_action",
            _process_items,
            run_id=items[0].run_id,
            action=action,
            item_count=len(items),
        )
        GstReconciliationActionLog.objects.create(
            entity_id=items[0].entity_id,
            entityfinid_id=items[0].entityfinid_id,
            subentity_id=items[0].subentity_id,
            run=items[0].run,
            action_type=GstReconciliationActionLog.ActionType.BULK_ACTION,
            actor=user,
            comment=note,
            details_json={
                "action": action,
                "item_ids_sample": processed_ids[:50],
                "reviewer_id": getattr(reviewer, "id", None),
                "processed_count": len(processed_ids),
                "failed_count": len(errors),
                "duration_ms": timed.duration_ms,
            },
            created_by_id=getattr(user, "id", None),
            updated_by_id=getattr(user, "id", None),
        )
        return BulkActionResult(action=action, processed_item_ids=processed_ids), errors
