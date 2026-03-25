from __future__ import annotations

from django.db import models
from django.db.models import Q

from .base import TrackingModel


DEFAULT_RECEIPT_POLICY_CONTROLS = {
    "require_allocation_on_post": "hard",      # off|warn|hard
    "allow_advance_without_allocation": "on",  # on|off
    "allow_on_account_without_allocation": "on",  # on|off
    "sync_ar_settlement_on_post": "on",        # on|off
    "sync_advance_balance_on_post": "on",      # on|off
    "residual_to_advance_balance": "on",       # on|off
    "require_confirm_before_post": "on",       # on|off
    "require_submit_before_approve": "off",    # on|off
    "allow_edit_after_submit": "on",           # on|off
    "unpost_target_status": "confirmed",       # confirmed|draft
    "allocation_policy": "manual",             # manual|fifo
    "over_settlement_rule": "block",           # block|warn
    "allocation_amount_match_rule": "hard",    # off|warn|hard
    "receipt_maker_checker": "off",            # off|warn|hard
    "same_user_submit_approve": "on",          # on|off
    "require_reference_number": "off",         # off|warn|hard
    "credit_note_consumption_mode": "reference_then_fifo",  # off|fifo|reference_only|reference_then_fifo
    "sync_gstr1_table11_on_post": "on",  # on|off
    "table11_amendment_mode": "snapshot",  # snapshot|off
}


def default_receipt_policy_controls():
    return dict(DEFAULT_RECEIPT_POLICY_CONTROLS)


class ReceiptSettings(TrackingModel):
    class DefaultWorkflowAction(models.TextChoices):
        DRAFT = "draft", "Save as Draft"
        CONFIRM = "confirm", "Auto Confirm on Save"
        POST = "post", "Auto Post on Save"

    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, related_name="receipt_settings")
    subentity = models.ForeignKey("entity.SubEntity", on_delete=models.PROTECT, null=True, blank=True, related_name="receipt_settings")

    default_doc_code_receipt = models.CharField(max_length=10, default="RV")
    default_workflow_action = models.CharField(
        max_length=10,
        choices=DefaultWorkflowAction.choices,
        default=DefaultWorkflowAction.DRAFT,
        db_index=True,
    )
    policy_controls = models.JSONField(default=default_receipt_policy_controls, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("entity", "subentity"), name="uq_receipt_settings_entity_subentity"),
        ]
        indexes = [
            models.Index(fields=["entity"], name="ix_receipt_settings_entity"),
        ]

    def __str__(self):
        return f"ReceiptSettings(entity={self.entity_id}, subentity={self.subentity_id})"


class ReceiptLockPeriod(TrackingModel):
    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT)
    subentity = models.ForeignKey("entity.SubEntity", on_delete=models.PROTECT, null=True, blank=True)
    lock_date = models.DateField()
    reason = models.CharField(max_length=200, null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["entity", "subentity", "lock_date"], name="ix_receipt_lock_period"),
        ]

    def __str__(self):
        return f"Lock({self.entity_id}, {self.subentity_id}, {self.lock_date})"


class ReceiptChoiceOverride(TrackingModel):
    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT)
    subentity = models.ForeignKey("entity.SubEntity", on_delete=models.PROTECT, null=True, blank=True)

    choice_group = models.CharField(max_length=50)
    choice_key = models.CharField(max_length=50)
    is_enabled = models.BooleanField(default=True)
    override_label = models.CharField(max_length=200, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("entity", "subentity", "choice_group", "choice_key"),
                name="uq_receipt_choice_override_scope",
            ),
            models.CheckConstraint(
                name="ck_receipt_choice_override_group_key_nn",
                check=Q(choice_group__isnull=False) & Q(choice_key__isnull=False),
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "subentity", "choice_group"], name="ix_rec_choice_override_scope"),
        ]

    def __str__(self):
        return f"{self.choice_group}:{self.choice_key} ({'on' if self.is_enabled else 'off'})"
