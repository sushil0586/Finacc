from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.db import transaction
from django.utils.module_loading import import_string
from django.utils import timezone

from gst_reconciliation.models import GstReconciliationActionLog, GstReconciliationRun
from gst_reconciliation.services.access import GstReconciliationWorkflowAccess
from gst_reconciliation.services.matching import gstr2b_purchase as _gstr2b_purchase_matcher  # noqa: F401
from gst_reconciliation.services.matching.registry import MatcherRegistry
from gst_reconciliation.services.performance import optional_async_matching_enabled, timed_call


@dataclass(frozen=True)
class RunTransitionResult:
    run: GstReconciliationRun
    action: str


class GstReconciliationRunLifecycleService:
    STATUS_TRANSITIONS = {
        GstReconciliationRun.Status.DRAFT: {
            GstReconciliationRun.Status.IMPORTED,
            GstReconciliationRun.Status.MATCHING,
            GstReconciliationRun.Status.FAILED,
        },
        GstReconciliationRun.Status.IMPORTED: {
            GstReconciliationRun.Status.MATCHING,
            GstReconciliationRun.Status.READY_FOR_REVIEW,
            GstReconciliationRun.Status.FAILED,
        },
        GstReconciliationRun.Status.MATCHING: {
            GstReconciliationRun.Status.READY_FOR_REVIEW,
            GstReconciliationRun.Status.FAILED,
        },
        GstReconciliationRun.Status.READY_FOR_REVIEW: {
            GstReconciliationRun.Status.IN_REVIEW,
            GstReconciliationRun.Status.REJECTED,
        },
        GstReconciliationRun.Status.IN_REVIEW: {
            GstReconciliationRun.Status.APPROVED,
            GstReconciliationRun.Status.REJECTED,
        },
        GstReconciliationRun.Status.APPROVED: {
            GstReconciliationRun.Status.CLOSED,
        },
        GstReconciliationRun.Status.REJECTED: {
            GstReconciliationRun.Status.IN_REVIEW,
            GstReconciliationRun.Status.CLOSED,
        },
        GstReconciliationRun.Status.FAILED: {
            GstReconciliationRun.Status.MATCHING,
            GstReconciliationRun.Status.CLOSED,
        },
        GstReconciliationRun.Status.CLOSED: set(),
    }

    @classmethod
    @transaction.atomic
    def create_run(cls, *, serializer, user) -> GstReconciliationRun:
        run = serializer.save(created_by=user, updated_by=user)
        cls._log(run=run, action_type=GstReconciliationActionLog.ActionType.CREATED, actor=user, to_status=run.status)
        return run

    @classmethod
    @transaction.atomic
    def submit_run(cls, *, run: GstReconciliationRun, user, comment: str | None = None) -> RunTransitionResult:
        cls._transition(
            run=run,
            to_status=GstReconciliationRun.Status.READY_FOR_REVIEW,
            user=user,
            action_type=GstReconciliationActionLog.ActionType.SUBMITTED,
            comment=comment,
            set_submitted=True,
        )
        return RunTransitionResult(run=run, action="submitted")

    @classmethod
    @transaction.atomic
    def start_review(cls, *, run: GstReconciliationRun, user, comment: str | None = None) -> RunTransitionResult:
        cls._transition(
            run=run,
            to_status=GstReconciliationRun.Status.IN_REVIEW,
            user=user,
            action_type=GstReconciliationActionLog.ActionType.REVIEW_STARTED,
            comment=comment,
            set_reviewed=True,
        )
        return RunTransitionResult(run=run, action="review_started")

    @classmethod
    @transaction.atomic
    def approve_run(cls, *, run: GstReconciliationRun, user, comment: str | None = None) -> RunTransitionResult:
        cls._transition(
            run=run,
            to_status=GstReconciliationRun.Status.APPROVED,
            user=user,
            action_type=GstReconciliationActionLog.ActionType.APPROVED,
            comment=comment,
            set_approved=True,
        )
        return RunTransitionResult(run=run, action="approved")

    @classmethod
    @transaction.atomic
    def reject_run(cls, *, run: GstReconciliationRun, user, comment: str | None = None) -> RunTransitionResult:
        cls._transition(
            run=run,
            to_status=GstReconciliationRun.Status.REJECTED,
            user=user,
            action_type=GstReconciliationActionLog.ActionType.REJECTED,
            comment=comment,
        )
        return RunTransitionResult(run=run, action="rejected")

    @classmethod
    @transaction.atomic
    def close_run(cls, *, run: GstReconciliationRun, user, comment: str | None = None) -> RunTransitionResult:
        GstReconciliationWorkflowAccess.assert_can_close_run(user=user, run=run)
        cls._transition(
            run=run,
            to_status=GstReconciliationRun.Status.CLOSED,
            user=user,
            action_type=GstReconciliationActionLog.ActionType.CLOSED,
            comment=comment,
            set_closed=True,
        )
        return RunTransitionResult(run=run, action="closed")

    @classmethod
    @transaction.atomic
    def execute_matching(cls, *, run: GstReconciliationRun, user, prefer_async: bool = False) -> RunTransitionResult:
        cls._transition(
            run=run,
            to_status=GstReconciliationRun.Status.MATCHING,
            user=user,
            action_type=GstReconciliationActionLog.ActionType.MATCH_STARTED,
            comment="Matching execution started.",
            save_after=False,
        )
        if prefer_async and cls._dispatch_matching_async(run=run, user=user):
            run.updated_by = user
            run.save(update_fields=["status", "updated_by", "updated_at"])
            return RunTransitionResult(run=run, action="queued")
        matcher = MatcherRegistry.get_for_run(run)
        timed = timed_call("run_match_execute", lambda: matcher.execute(run, user=user), run_id=run.id, reconciliation_type=run.reconciliation_type)
        result = timed.value
        run.status = GstReconciliationRun.Status.READY_FOR_REVIEW
        run.summary_json = {
            **(run.summary_json or {}),
            "processed_items": result.processed_items,
            "matched_items": result.matched_items,
            "partial_items": result.partial_items,
            "mismatched_items": result.mismatched_items,
            "ignored_items": result.ignored_items,
            "match_duration_ms": timed.duration_ms,
        }
        run.updated_by = user
        run.save(update_fields=["status", "summary_json", "updated_by", "updated_at"])
        cls._log(
            run=run,
            action_type=GstReconciliationActionLog.ActionType.MATCH_COMPLETED,
            actor=user,
            from_status=GstReconciliationRun.Status.MATCHING,
            to_status=run.status,
            comment="Matching execution completed.",
            details_json=run.summary_json,
        )
        return RunTransitionResult(run=run, action="matched")

    @classmethod
    def _dispatch_matching_async(cls, *, run: GstReconciliationRun, user) -> bool:
        if not optional_async_matching_enabled():
            return False
        handler_path = getattr(settings, "GST_RECON_ASYNC_MATCH_HANDLER", "")
        if not handler_path:
            return False
        handler = import_string(handler_path)
        handler(run_id=run.id, user_id=getattr(user, "id", None))
        return True

    @classmethod
    def _transition(
        cls,
        *,
        run: GstReconciliationRun,
        to_status: str,
        user,
        action_type: str,
        comment: str | None = None,
        set_submitted: bool = False,
        set_reviewed: bool = False,
        set_approved: bool = False,
        set_closed: bool = False,
        save_after: bool = True,
    ) -> None:
        from_status = run.status
        allowed = cls.STATUS_TRANSITIONS.get(from_status, set())
        if to_status not in allowed:
            raise ValueError(f"Cannot transition GST reconciliation run from {from_status} to {to_status}.")
        run.status = to_status
        run.updated_by = user
        now = timezone.now()
        if set_submitted:
            run.submitted_by = user
            run.submitted_at = now
            run.review_comment = comment or run.review_comment
        if set_reviewed:
            run.reviewed_by = user
            run.reviewed_at = now
            run.review_comment = comment or run.review_comment
        if set_approved:
            run.approved_by = user
            run.approved_at = now
            run.approval_comment = comment or run.approval_comment
        if set_closed:
            run.closed_by = user
            run.closed_at = now
            run.close_comment = comment or run.close_comment
        if action_type == GstReconciliationActionLog.ActionType.REJECTED:
            run.review_comment = comment or run.review_comment
        if save_after:
            run.save()
        cls._log(
            run=run,
            action_type=action_type,
            actor=user,
            from_status=from_status,
            to_status=to_status,
            comment=comment,
        )

    @staticmethod
    def _log(
        *,
        run: GstReconciliationRun,
        action_type: str,
        actor,
        from_status: str | None = None,
        to_status: str | None = None,
        comment: str | None = None,
        details_json: dict | None = None,
    ) -> None:
        GstReconciliationActionLog.objects.create(
            entity_id=run.entity_id,
            entityfinid_id=run.entityfinid_id,
            subentity_id=run.subentity_id,
            run=run,
            action_type=action_type,
            actor=actor,
            from_status=from_status,
            to_status=to_status,
            comment=comment,
            details_json=details_json or {},
            created_by_id=getattr(actor, "id", None),
            updated_by_id=getattr(actor, "id", None),
        )
