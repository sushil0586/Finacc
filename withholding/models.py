from __future__ import annotations

from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator


class WithholdingTaxType(models.IntegerChoices):
    TDS = 1, "TDS"
    TCS = 2, "TCS"


class WithholdingBaseRule(models.IntegerChoices):
    INVOICE_VALUE_EXCL_GST = 1, "Invoice value excl GST"
    INVOICE_VALUE_INCL_GST = 2, "Invoice value incl GST"
    RECEIPT_VALUE = 3, "Receipt value"
    PAYMENT_VALUE = 4, "Payment value"


class WithholdingSection(models.Model):
    """
    Master catalog for both TDS & TCS.
    Example:
      - TDS 194C / 194J / 194Q ...
      - TCS 206C(1), etc
    """
    tax_type = models.PositiveSmallIntegerField(choices=WithholdingTaxType.choices, db_index=True)
    section_code = models.CharField(max_length=16, db_index=True)  # "194C", "194Q", "206C(1)"
    description = models.CharField(max_length=255)

    base_rule = models.PositiveSmallIntegerField(
        choices=WithholdingBaseRule.choices,
        default=WithholdingBaseRule.INVOICE_VALUE_EXCL_GST,
    )

    rate_default = models.DecimalField(
        max_digits=7, decimal_places=4, default=Decimal("0.0000"),
        validators=[MinValueValidator(Decimal("0.0000"))],
    )
    threshold_default = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    requires_pan = models.BooleanField(default=False)
    higher_rate_no_pan = models.DecimalField(
        max_digits=7, decimal_places=4, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0.0000"))],
    )

    # Optional: structured conditions (goods/service, resident etc.)
    applicability_json = models.JSONField(null=True, blank=True)

    effective_from = models.DateField(db_index=True)
    effective_to = models.DateField(null=True, blank=True, db_index=True)

    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        unique_together = (("tax_type", "section_code", "effective_from"),)
        indexes = [
            models.Index(fields=["tax_type", "section_code"]),
            models.Index(fields=["tax_type", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_tax_type_display()} {self.section_code} ({self.effective_from})"


class PartyTaxProfile(models.Model):
    """
    Linked to your Account master (customer/vendor).
    Keep PAN here + lower deduction certificate rate window.
    """
    party_account = models.OneToOneField(
        "financial.account",
        on_delete=models.CASCADE,
        related_name="tax_profile",
        db_index=True,
    )

    pan = models.CharField(max_length=16, null=True, blank=True)
    is_pan_available = models.BooleanField(default=False)

    is_exempt_withholding = models.BooleanField(default=False)

    lower_deduction_rate = models.DecimalField(
        max_digits=7, decimal_places=4, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0.0000"))],
    )
    lower_deduction_valid_from = models.DateField(null=True, blank=True)
    lower_deduction_valid_to = models.DateField(null=True, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"TaxProfile({self.party_account_id})"


class EntityWithholdingConfig(models.Model):
    """
    Entity/subentity/fy configuration.
    """
    entity = models.ForeignKey("entity.Entity", on_delete=models.CASCADE, db_index=True)
    entityfin = models.ForeignKey("entity.EntityFinancialYear", on_delete=models.CASCADE, db_index=True)
    subentity = models.ForeignKey("entity.SubEntity", on_delete=models.CASCADE, null=True, blank=True, db_index=True)

    enable_tds = models.BooleanField(default=True)
    enable_tcs = models.BooleanField(default=True)

    default_tds_section = models.ForeignKey(
        WithholdingSection, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="default_for_tds_configs",
        limit_choices_to={"tax_type": WithholdingTaxType.TDS},
    )
    default_tcs_section = models.ForeignKey(
        WithholdingSection, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="default_for_tcs_configs",
        limit_choices_to={"tax_type": WithholdingTaxType.TCS},
    )

    apply_194q = models.BooleanField(default=False)
    apply_tcs_206c1h = models.BooleanField(default=False)  # keep for history

    effective_from = models.DateField(db_index=True)

    rounding_places = models.PositiveSmallIntegerField(default=2)

    class Meta:
        indexes = [
            models.Index(fields=["entity", "entityfin", "subentity"]),
            models.Index(fields=["entity", "effective_from"]),
        ]
        unique_together = (("entity", "entityfin", "subentity", "effective_from"),)

    def __str__(self) -> str:
        return f"WithholdingConfig(entity={self.entity_id}, fy={self.entityfin_id}, sub={self.subentity_id})"