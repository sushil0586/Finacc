from __future__ import annotations

from decimal import Decimal

from django.db import models
from django.db.models import Q

from core.models.base import EntityScopedModel,TrackingModel
from sales.models.sales_core import SalesInvoiceHeader  # adjust path if needed

ZERO2 = Decimal("0.00")
ZERO4 = Decimal("0.0000")


class SalesSettings(EntityScopedModel):
    """
    One row per entity + (optional subentity).
    Controls default workflow + governance policies for Sales.
    """

    class DefaultWorkflowAction(models.TextChoices):
        DRAFT = "draft", "Save as Draft"
        CONFIRM = "confirm", "Auto Confirm on Save"
        POST = "post", "Auto Post on Save"

    entity = models.ForeignKey(
        "entity.Entity",
        on_delete=models.PROTECT,
        related_name="sales_sales_settings",
    )
    subentity = models.ForeignKey(
        "entity.SubEntity",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sales_sales_settings_scope",
    )

    # default doc codes used by your invoice creation
    default_doc_code_invoice = models.CharField(max_length=10, default="SINV")
    default_doc_code_cn = models.CharField(max_length=10, default="SCN")
    default_doc_code_dn = models.CharField(max_length=10, default="SDN")

    # ✅ default workflow behavior on create
    default_workflow_action = models.CharField(
        max_length=10,
        choices=DefaultWorkflowAction.choices,
        default=DefaultWorkflowAction.DRAFT,
        db_index=True,
    )

    # -------------------------
    # Policies / governance
    # -------------------------
    auto_derive_tax_regime = models.BooleanField(default=True)  # POS vs seller_state
    allow_mixed_taxability_in_one_invoice = models.BooleanField(default=True)

    # E-Invoice / E-Way governance
    # (actual applicability is derived in service, but these flags let SaaS tenants enforce policies)
    enable_einvoice = models.BooleanField(default=True)
    enable_eway = models.BooleanField(default=True)

    # e-invoice policy (when to attempt generation)
    auto_generate_einvoice_on_confirm = models.BooleanField(default=False)
    auto_generate_einvoice_on_post = models.BooleanField(default=False)

    # e-way policy (when to attempt generation)
    auto_generate_eway_on_confirm = models.BooleanField(default=False)
    auto_generate_eway_on_post = models.BooleanField(default=False)

    # optional: use combined IRP flow when both are needed (generate IRN + EWB together if supported)
    prefer_irp_generate_einvoice_and_eway_together = models.BooleanField(default=True)

    # -------------------------
    # Rounding configuration
    # -------------------------
    round_grand_total_to = models.PositiveSmallIntegerField(default=2)  # decimals
    enable_round_off = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("entity", "subentity"),
                name="uq_sales_settings_entity_subentity",
            ),
        ]
        indexes = [
            models.Index(fields=["entity"], name="ix_sales_settings_entity"),
            models.Index(fields=["entity", "subentity"], name="ix_sales_settings_scope"),
        ]

    def __str__(self) -> str:
        return f"SalesSettings(entity={self.entity_id}, subentity={self.subentity_id})"


class SalesLockPeriod(EntityScopedModel):
    """
    Prevent edits/posting before lock_date (per entity or entity+subentity).
    Typical for accountants after period closing.
    """

    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT)
    subentity = models.ForeignKey("entity.SubEntity", on_delete=models.PROTECT, null=True, blank=True)

    lock_date = models.DateField()  # all invoices <= lock_date are locked
    reason = models.CharField(max_length=200, null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["entity", "subentity", "lock_date"], name="ix_sales_lock_period"),
        ]

    def __str__(self) -> str:
        return f"Lock({self.entity_id}, {self.subentity_id}, {self.lock_date})"


class SalesChoiceOverride(TrackingModel):
    """
    SaaS choice governance:
      - enable/disable an enum value per entity/subentity
      - override labels without code changes

    Example:
      choice_group="SupplyCategory"
      choice_key="EXPORT_WITHOUT_IGST"
      is_enabled=False
    """

    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT)
    subentity = models.ForeignKey("entity.SubEntity", on_delete=models.PROTECT, null=True, blank=True)

    choice_group = models.CharField(max_length=50)  # e.g. "SupplyCategory", "Taxability", "DocType"
    choice_key = models.CharField(max_length=50)    # e.g. "SEZ_WITHOUT_IGST"
    is_enabled = models.BooleanField(default=True)
    override_label = models.CharField(max_length=200, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("entity", "subentity", "choice_group", "choice_key"),
                name="uq_sales_choice_override_scope",
            ),
            models.CheckConstraint(
                name="ck_sales_choice_override_group_key_nn",
                check=Q(choice_group__isnull=False) & Q(choice_key__isnull=False),
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "subentity", "choice_group"], name="ix_sales_choice_override_scope"),
        ]

    def __str__(self) -> str:
        return f"{self.choice_group}:{self.choice_key} ({'on' if self.is_enabled else 'off'})"
