from __future__ import annotations
from django.db import models
from django.db.models import Q
from .base import TrackingModel
from purchase.models.purchase_core import PurchaseInvoiceHeader
from decimal import Decimal

ZERO2 = Decimal("0.00")
ZERO4 = Decimal("0.0000")


class PurchaseSettings(TrackingModel):
    """
    One row per entity + (optional subentity).
    Controls default workflow + governance policies.
    """
    class DefaultWorkflowAction(models.TextChoices):
        DRAFT = "draft", "Save as Draft"
        CONFIRM = "confirm", "Auto Confirm on Save"
        POST = "post", "Auto Post on Save"

    entity = models.ForeignKey(
        "entity.Entity",
        on_delete=models.PROTECT,
        related_name="purchase_purchase_settings",
    )
    subentity = models.ForeignKey(
        "entity.subentity",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="purchase_purchase_settings_fy",
    )

    # defaults doc codes used by your invoice creation
    default_doc_code_invoice = models.CharField(max_length=10, default="PINV")
    default_doc_code_cn = models.CharField(max_length=10, default="PCN")
    default_doc_code_dn = models.CharField(max_length=10, default="PDN")

    # ✅ new: default workflow behavior on create
    default_workflow_action = models.CharField(
        max_length=10,
        choices=DefaultWorkflowAction.choices,
        default=DefaultWorkflowAction.DRAFT,
        db_index=True,
    )

    # policies
    auto_derive_tax_regime = models.BooleanField(default=True)
    enforce_2b_before_itc_claim = models.BooleanField(default=False)
    allow_mixed_taxability_in_one_bill = models.BooleanField(default=True)

    # rounding configuration
    round_grand_total_to = models.PositiveSmallIntegerField(default=2)  # decimals
    enable_round_off = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("entity", "subentity"),
                name="uq_purchase_settings_entity_subentity",
            ),
        ]
        indexes = [
            models.Index(fields=["entity"], name="ix_purchase_settings_entity"),
        ]

    def __str__(self):
        return f"PurchaseSettings(entity={self.entity_id}, subentity={self.subentity_id})"
    


class PurchaseLockPeriod(TrackingModel):
    """
    Prevent edits/posting before lock_date (per entity or entity+subentity).
    Typical for accountants after period closing.
    """
    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT)
    subentity = models.ForeignKey("entity.subentity", on_delete=models.PROTECT, null=True, blank=True)

    lock_date = models.DateField()  # all bills <= lock_date are locked
    reason = models.CharField(max_length=200, null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["entity", "subentity", "lock_date"], name="ix_purchase_lock_period"),
        ]

    def __str__(self):
        return f"Lock({self.entity_id}, {self.subentity_id}, {self.lock_date})"
    


class PurchaseChoiceOverride(TrackingModel):
    """
    SaaS choice governance:
      - enable/disable an enum value per entity/subentity
      - override labels without code changes

    Example:
      choice_group="SupplyCategory"
      choice_key="SEZ"
      is_enabled=False
    """
    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT)
    subentity = models.ForeignKey("entity.subentity", on_delete=models.PROTECT, null=True, blank=True)

    choice_group = models.CharField(max_length=50)  # e.g. "SupplyCategory"
    choice_key = models.CharField(max_length=50)    # e.g. "SEZ"
    is_enabled = models.BooleanField(default=True)
    override_label = models.CharField(max_length=200, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("entity", "subentity", "choice_group", "choice_key"),
                name="uq_purchase_choice_override_scope",
            ),
            models.CheckConstraint(
                name="ck_purchase_choice_override_group_key_nn",
                check=Q(choice_group__isnull=False) & Q(choice_key__isnull=False),
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "subentity", "choice_group"], name="ix_pur_choice_override_scope"),
        ]

    def __str__(self):
        return f"{self.choice_group}:{self.choice_key} ({'on' if self.is_enabled else 'off'})"



