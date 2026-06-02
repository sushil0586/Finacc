from __future__ import annotations

from django.db import models

from core.models.base import EntityScopedModel


class GstReconciliationActionLog(EntityScopedModel):
    class ActionType(models.TextChoices):
        CREATED = "CREATED", "Created"
        IMPORTED = "IMPORTED", "Imported"
        MATCH_STARTED = "MATCH_STARTED", "Match Started"
        MATCH_COMPLETED = "MATCH_COMPLETED", "Match Completed"
        SUBMITTED = "SUBMITTED", "Submitted"
        REVIEW_STARTED = "REVIEW_STARTED", "Review Started"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        CLOSED = "CLOSED", "Closed"
        ITEM_RESOLVED = "ITEM_RESOLVED", "Item Resolved"
        ITEM_ASSIGNED = "ITEM_ASSIGNED", "Item Assigned"
        ITEM_MANUAL_MATCHED = "ITEM_MANUAL_MATCHED", "Item Manually Matched"
        ITEM_UNMATCHED = "ITEM_UNMATCHED", "Item Unmatched"
        ITEM_IGNORED = "ITEM_IGNORED", "Item Ignored"
        ITEM_REOPENED = "ITEM_REOPENED", "Item Reopened"
        ITEM_ACCEPTED_MISMATCH = "ITEM_ACCEPTED_MISMATCH", "Item Accepted Mismatch"
        BULK_ACTION = "BULK_ACTION", "Bulk Action"
        NOTE = "NOTE", "Note"

    run = models.ForeignKey(
        "gst_reconciliation.GstReconciliationRun",
        on_delete=models.CASCADE,
        related_name="action_logs",
    )
    item = models.ForeignKey(
        "gst_reconciliation.GstReconciliationItem",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="action_logs",
    )
    action_type = models.CharField(max_length=24, choices=ActionType.choices, db_index=True)
    actor = models.ForeignKey(
        "Authentication.User",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="gst_reconciliation_actions",
    )
    from_status = models.CharField(max_length=24, null=True, blank=True)
    to_status = models.CharField(max_length=24, null=True, blank=True)
    comment = models.TextField(null=True, blank=True)
    details_json = models.JSONField(default=dict, blank=True)

    class Meta(EntityScopedModel.Meta):
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=["entity", "entityfinid", "subentity"], name="ix_gst_log_scope"),
            models.Index(fields=["run", "action_type", "created_at"], name="ix_gst_log_run_action_created"),
            models.Index(fields=["actor", "created_at"], name="ix_gst_log_actor_created"),
            models.Index(fields=["item", "created_at"], name="ix_gst_log_item_created"),
        ]

    def __str__(self) -> str:
        return f"Run {self.run_id} {self.action_type}"
