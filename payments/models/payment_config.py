from __future__ import annotations

from django.db import models

from .base import TrackingModel


DEFAULT_PAYMENT_POLICY_CONTROLS = {
    "require_allocation_on_post": "hard",      # off|warn|hard
    "allow_advance_without_allocation": "on",  # on|off
    "allow_on_account_without_allocation": "on",  # on|off
    "sync_ap_settlement_on_post": "on",        # on|off
    "sync_advance_balance_on_post": "on",      # on|off
    "residual_to_advance_balance": "on",       # on|off
    "require_confirm_before_post": "on",       # on|off
    "require_submit_before_approve": "off",    # on|off
    "allow_edit_after_submit": "on",           # on|off
    "unpost_target_status": "confirmed",       # confirmed|draft
    "allocation_policy": "manual",             # manual|fifo
    "over_settlement_rule": "block",           # block|warn
    "allocation_amount_match_rule": "hard",    # off|warn|hard
    "payment_maker_checker": "off",            # off|warn|hard
    "same_user_submit_approve": "on",          # on|off
    "require_reference_number": "off",         # off|warn|hard
}


def default_payment_policy_controls():
    return dict(DEFAULT_PAYMENT_POLICY_CONTROLS)


class PaymentSettings(TrackingModel):
    class DefaultWorkflowAction(models.TextChoices):
        DRAFT = "draft", "Save as Draft"
        CONFIRM = "confirm", "Auto Confirm on Save"
        POST = "post", "Auto Post on Save"

    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, related_name="payment_settings")
    subentity = models.ForeignKey("entity.SubEntity", on_delete=models.PROTECT, null=True, blank=True, related_name="payment_settings")

    default_doc_code_payment = models.CharField(max_length=10, default="PPV")
    default_workflow_action = models.CharField(
        max_length=10,
        choices=DefaultWorkflowAction.choices,
        default=DefaultWorkflowAction.DRAFT,
        db_index=True,
    )
    policy_controls = models.JSONField(default=default_payment_policy_controls, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("entity", "subentity"), name="uq_payment_settings_entity_subentity"),
        ]
        indexes = [
            models.Index(fields=["entity"], name="ix_payment_settings_entity"),
        ]

    def __str__(self):
        return f"PaymentSettings(entity={self.entity_id}, subentity={self.subentity_id})"
