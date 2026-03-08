from __future__ import annotations

from django.db import models

from .base import TrackingModel


DEFAULT_VOUCHER_POLICY_CONTROLS = {
    "require_confirm_before_post": "on",
    "require_submit_before_approve": "off",
    "allow_edit_after_submit": "on",
    "unpost_target_status": "confirmed",
    "voucher_maker_checker": "off",
    "same_user_submit_approve": "on",
    "require_reference_number": "off",
    "allow_control_account_lines": "on",
    "require_cash_bank_account_for_cash_bank": "on",
    "cash_bank_mixed_entry_rule": "off",  # off|hard
}


def default_voucher_policy_controls():
    return dict(DEFAULT_VOUCHER_POLICY_CONTROLS)


class VoucherSettings(TrackingModel):
    class DefaultWorkflowAction(models.TextChoices):
        DRAFT = "draft", "Save as Draft"
        CONFIRM = "confirm", "Auto Confirm on Save"
        POST = "post", "Auto Post on Save"

    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, related_name="voucher_settings")
    subentity = models.ForeignKey("entity.SubEntity", on_delete=models.PROTECT, null=True, blank=True, related_name="voucher_settings")

    default_doc_code_cash = models.CharField(max_length=10, default="CV")
    default_doc_code_bank = models.CharField(max_length=10, default="BV")
    default_doc_code_journal = models.CharField(max_length=10, default="JV")
    default_workflow_action = models.CharField(
        max_length=10,
        choices=DefaultWorkflowAction.choices,
        default=DefaultWorkflowAction.DRAFT,
        db_index=True,
    )
    policy_controls = models.JSONField(default=default_voucher_policy_controls, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("entity", "subentity"), name="uq_voucher_settings_entity_subentity"),
        ]
        indexes = [
            models.Index(fields=["entity"], name="ix_voucher_settings_entity"),
        ]

    def __str__(self):
        return f"VoucherSettings(entity={self.entity_id}, subentity={self.subentity_id})"
