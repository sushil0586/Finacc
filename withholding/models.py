from __future__ import annotations

from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone


class TaxLawType(models.TextChoices):
    INCOME_TAX = "INCOME_TAX", "Income Tax"
    GST = "GST", "GST"


class TcsSubType(models.TextChoices):
    SEC_206C_1 = "206C_1", "206C(1)"
    SEC_206C_1C = "206C_1C", "206C(1C)"
    SEC_206C_1F = "206C_1F", "206C(1F)"
    SEC_206C_1G = "206C_1G", "206C(1G)"
    LEGACY_206C_1H = "206C_1H_LEGACY", "206C(1H) Legacy"
    GST_SEC_52 = "GST_SEC_52", "GST Section 52"


class WithholdingTaxType(models.IntegerChoices):
    TDS = 1, "TDS"
    TCS = 2, "TCS"


class ResidencyStatus(models.TextChoices):
    RESIDENT = "resident", "Resident"
    NON_RESIDENT = "non_resident", "Non Resident"
    UNKNOWN = "unknown", "Unknown"


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
    law_type = models.CharField(max_length=16, choices=TaxLawType.choices, default=TaxLawType.INCOME_TAX, db_index=True)
    sub_type = models.CharField(max_length=24, choices=TcsSubType.choices, null=True, blank=True, db_index=True)
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
    higher_rate_206ab = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.0000"))],
        help_text="Higher rate to apply when deductee is specified person under section 206AB.",
    )

    # Optional: structured conditions (goods/service, resident etc.)
    applicability_json = models.JSONField(null=True, blank=True)

    effective_from = models.DateField(db_index=True)
    effective_to = models.DateField(null=True, blank=True, db_index=True)

    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        unique_together = (("tax_type", "section_code", "base_rule", "effective_from"),)
        indexes = [
            models.Index(fields=["tax_type", "section_code"]),
            models.Index(fields=["tax_type", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_tax_type_display()} {self.section_code} ({self.effective_from})"


class WithholdingSectionPolicyAudit(models.Model):
    class Action(models.TextChoices):
        CREATED = "CREATED", "Created"
        UPDATED = "UPDATED", "Updated"
        DELETED = "DELETED", "Deleted"

    section = models.ForeignKey(
        WithholdingSection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="policy_audits",
        db_index=True,
    )
    action = models.CharField(max_length=16, choices=Action.choices, db_index=True)
    changed_by = models.ForeignKey(
        "Authentication.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="withholding_policy_audits",
        db_index=True,
    )
    changed_fields_json = models.JSONField(null=True, blank=True)
    before_snapshot_json = models.JSONField(null=True, blank=True)
    after_snapshot_json = models.JSONField(null=True, blank=True)
    source = models.CharField(max_length=32, default="api", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "withholding_section_policy_audit"
        indexes = [
            models.Index(fields=["section", "created_at"], name="ix_wh_policy_audit_sec_dt"),
            models.Index(fields=["action", "created_at"], name="ix_wh_policy_audit_action_dt"),
        ]

    def __str__(self) -> str:
        return f"WithholdingPolicyAudit(section={self.section_id}, action={self.action})"


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
    is_specified_person_206ab = models.BooleanField(default=False)
    specified_person_valid_from = models.DateField(null=True, blank=True)
    specified_person_valid_to = models.DateField(null=True, blank=True)

    lower_deduction_rate = models.DecimalField(
        max_digits=7, decimal_places=4, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0.0000"))],
    )
    lower_deduction_valid_from = models.DateField(null=True, blank=True)
    lower_deduction_valid_to = models.DateField(null=True, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"TaxProfile({self.party_account_id})"


class EntityPartyTaxProfile(models.Model):
    """
    Entity-scoped withholding policy overrides for a party.
    Keeps global PAN master in PartyTaxProfile while allowing tenant-level behavior.
    """
    entity = models.ForeignKey("entity.Entity", on_delete=models.CASCADE, db_index=True)
    subentity = models.ForeignKey("entity.SubEntity", on_delete=models.CASCADE, null=True, blank=True, db_index=True)
    party_account = models.ForeignKey("financial.account", on_delete=models.CASCADE, db_index=True)

    is_exempt_withholding = models.BooleanField(default=False)
    is_specified_person_206ab = models.BooleanField(default=False)
    specified_person_valid_from = models.DateField(null=True, blank=True)
    specified_person_valid_to = models.DateField(null=True, blank=True)
    residency_status = models.CharField(
        max_length=24,
        choices=ResidencyStatus.choices,
        default=ResidencyStatus.UNKNOWN,
        db_index=True,
    )
    tax_identifier = models.CharField(max_length=64, null=True, blank=True)
    declaration_reference = models.CharField(max_length=64, null=True, blank=True)
    treaty_article = models.CharField(max_length=64, null=True, blank=True)
    treaty_rate = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.0000"))],
    )
    treaty_valid_from = models.DateField(null=True, blank=True)
    treaty_valid_to = models.DateField(null=True, blank=True)
    surcharge_rate = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.0000"))],
    )
    cess_rate = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.0000"))],
    )

    lower_deduction_rate = models.DecimalField(
        max_digits=7, decimal_places=4, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0.0000"))],
    )
    lower_deduction_valid_from = models.DateField(null=True, blank=True)
    lower_deduction_valid_to = models.DateField(null=True, blank=True)

    is_active = models.BooleanField(default=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "subentity", "party_account"],
                name="uq_wh_entity_party_profile",
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "subentity", "party_account", "is_active"], name="ix_wh_ent_party_profile"),
        ]

    def __str__(self) -> str:
        return (
            f"EntityPartyTaxProfile(entity={self.entity_id}, sub={self.subentity_id}, "
            f"party={self.party_account_id})"
        )


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
    tcs_206c1h_prev_fy_turnover = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    tcs_206c1h_turnover_limit = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("100000000.00"))
    tcs_206c1h_force_eligible = models.BooleanField(null=True, blank=True, help_text="Optional manual override for 206C(1H) turnover eligibility.")

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


class EntityTcsThresholdOpening(models.Model):
    """
    Opening cumulative base support for migration-safe threshold logic.
    """
    entity = models.ForeignKey("entity.Entity", on_delete=models.CASCADE, db_index=True)
    entityfin = models.ForeignKey("entity.EntityFinancialYear", on_delete=models.CASCADE, db_index=True)
    subentity = models.ForeignKey("entity.SubEntity", on_delete=models.CASCADE, null=True, blank=True, db_index=True)
    party_account = models.ForeignKey("financial.account", on_delete=models.CASCADE, db_index=True)
    section = models.ForeignKey(
        WithholdingSection,
        on_delete=models.CASCADE,
        db_index=True,
        limit_choices_to={"tax_type": WithholdingTaxType.TCS},
    )
    opening_base_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    effective_from = models.DateField(default=timezone.localdate, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["entity", "entityfin", "party_account", "section", "is_active"], name="ix_tcs_opening_lookup"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "entityfin", "subentity", "party_account", "section", "effective_from"],
                name="uq_tcs_opening_entity_fin_sub_party_sec_eff",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"TcsOpening(entity={self.entity_id}, fin={self.entityfin_id}, sub={self.subentity_id}, "
            f"party={self.party_account_id}, sec={self.section_id}, amt={self.opening_base_amount})"
        )


class EntityWithholdingSectionPostingMap(models.Model):
    """
    SaaS-safe mapping of withholding section to tenant-specific payable account/ledger.
    """
    entity = models.ForeignKey("entity.Entity", on_delete=models.CASCADE, db_index=True)
    subentity = models.ForeignKey("entity.SubEntity", on_delete=models.CASCADE, null=True, blank=True, db_index=True)
    section = models.ForeignKey(WithholdingSection, on_delete=models.CASCADE, db_index=True)
    payable_account = models.ForeignKey("financial.account", on_delete=models.PROTECT, db_index=True)
    payable_ledger = models.ForeignKey("financial.Ledger", on_delete=models.PROTECT, null=True, blank=True, db_index=True)
    effective_from = models.DateField(default=timezone.localdate, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["entity", "section", "subentity", "is_active"], name="ix_wh_sec_map_lookup"),
            models.Index(fields=["entity", "effective_from"], name="ix_wh_sec_map_eff"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "subentity", "section", "effective_from"],
                name="uq_wh_sec_map_entity_sub_sec_eff",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"EntitySectionMap(entity={self.entity_id}, sub={self.subentity_id}, "
            f"section={self.section_id}, account={self.payable_account_id})"
        )


class TcsComputation(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        CONFIRMED = "CONFIRMED", "Confirmed"
        REVERSED = "REVERSED", "Reversed"

    module_name = models.CharField(max_length=30, db_index=True)  # sales/purchase/...
    document_type = models.CharField(max_length=30, db_index=True)  # invoice/cn/dn/...
    document_id = models.BigIntegerField(db_index=True)
    document_no = models.CharField(max_length=60, blank=True, default="")
    doc_date = models.DateField(db_index=True)

    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, db_index=True)
    entityfin = models.ForeignKey("entity.EntityFinancialYear", on_delete=models.PROTECT, db_index=True)
    subentity = models.ForeignKey("entity.SubEntity", on_delete=models.PROTECT, null=True, blank=True, db_index=True)
    party_account = models.ForeignKey("financial.account", on_delete=models.PROTECT, db_index=True)

    section = models.ForeignKey(WithholdingSection, null=True, blank=True, on_delete=models.PROTECT, db_index=True)
    rule_snapshot_json = models.JSONField(null=True, blank=True)
    applicability_status = models.CharField(max_length=24, default="APPLICABLE", db_index=True)
    trigger_basis = models.CharField(max_length=20, blank=True, default="INVOICE")

    taxable_base = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    excluded_base = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    tcs_base_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    rate = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0.0000"))
    tcs_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    no_pan_applied = models.BooleanField(default=False)
    lower_rate_applied = models.BooleanField(default=False)

    override_reason = models.CharField(max_length=255, blank=True, default="")
    overridden_by = models.ForeignKey("Authentication.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="tcs_overridden")
    overridden_at = models.DateTimeField(null=True, blank=True)

    fiscal_year = models.CharField(max_length=9, blank=True, default="")  # 2025-26
    quarter = models.CharField(max_length=2, blank=True, default="")      # Q1..Q4
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True)

    computation_json = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "withholding_tcs_computation"
        indexes = [
            models.Index(fields=["module_name", "document_type", "document_id"], name="ix_tcs_cmp_doc"),
            models.Index(fields=["entity", "fiscal_year", "quarter"], name="ix_tcs_cmp_fy_qtr"),
            models.Index(fields=["party_account", "doc_date"], name="ix_tcs_cmp_party_dt"),
        ]


class TcsCollection(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        ALLOCATED = "ALLOCATED", "Allocated"
        CANCELLED = "CANCELLED", "Cancelled"

    computation = models.ForeignKey(TcsComputation, on_delete=models.CASCADE, related_name="collections", db_index=True)
    collection_date = models.DateField(db_index=True)
    receipt_voucher_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    amount_received = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    tcs_collected_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    collection_reference = models.CharField(max_length=80, blank=True, default="")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "withholding_tcs_collection"
        indexes = [
            models.Index(fields=["collection_date", "status"], name="ix_tcs_col_dt_st"),
        ]


class TcsDeposit(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        CONFIRMED = "CONFIRMED", "Confirmed"
        FILED = "FILED", "Filed"

    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, db_index=True)
    financial_year = models.CharField(max_length=9, db_index=True)
    month = models.PositiveSmallIntegerField(db_index=True)  # 1..12
    challan_no = models.CharField(max_length=40, db_index=True)
    challan_date = models.DateField(db_index=True)
    bsr_code = models.CharField(max_length=20, blank=True, default="")
    cin = models.CharField(max_length=40, blank=True, default="")
    bank_name = models.CharField(max_length=100, blank=True, default="")
    total_deposit_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    deposited_by = models.ForeignKey("Authentication.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="tcs_deposited")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "withholding_tcs_deposit"
        indexes = [
            models.Index(fields=["entity", "financial_year", "month"], name="ix_tcs_dep_fy_m"),
        ]


class TcsDepositAllocation(models.Model):
    deposit = models.ForeignKey(TcsDeposit, on_delete=models.CASCADE, related_name="allocations", db_index=True)
    collection = models.ForeignKey(TcsCollection, on_delete=models.PROTECT, related_name="deposit_allocations", db_index=True)
    allocated_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "withholding_tcs_deposit_allocation"
        constraints = [
            models.UniqueConstraint(fields=["deposit", "collection"], name="uq_tcs_dep_alloc_once"),
        ]


class TcsQuarterlyReturn(models.Model):
    class ReturnType(models.TextChoices):
        ORIGINAL = "ORIGINAL", "Original"
        CORRECTION = "CORRECTION", "Correction"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        VALIDATED = "VALIDATED", "Validated"
        FILED = "FILED", "Filed"

    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, db_index=True)
    fy = models.CharField(max_length=9, db_index=True)
    quarter = models.CharField(max_length=2, db_index=True)
    form_name = models.CharField(max_length=10, default="27EQ")
    return_type = models.CharField(max_length=12, choices=ReturnType.choices, default=ReturnType.ORIGINAL)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True)
    ack_no = models.CharField(max_length=50, blank=True, default="")
    filed_on = models.DateField(null=True, blank=True)
    json_snapshot = models.JSONField(null=True, blank=True)
    file_path = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "withholding_tcs_quarterly_return"
        indexes = [models.Index(fields=["entity", "fy", "quarter"], name="ix_tcs_ret_fy_q")]


class TcsCertificate(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        ISSUED = "ISSUED", "Issued"
        CANCELLED = "CANCELLED", "Cancelled"

    quarterly_return = models.ForeignKey(TcsQuarterlyReturn, on_delete=models.CASCADE, related_name="certificates", db_index=True)
    party_account = models.ForeignKey("financial.account", on_delete=models.PROTECT, db_index=True)
    certificate_no = models.CharField(max_length=50, db_index=True)
    form_name = models.CharField(max_length=10, default="27D")
    issue_date = models.DateField(null=True, blank=True)
    amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    file_path = models.CharField(max_length=255, blank=True, default="")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "withholding_tcs_certificate"
        constraints = [
            models.UniqueConstraint(fields=["quarterly_return", "party_account"], name="uq_tcs_cert_party_once"),
        ]


class GstTcsEcoProfile(models.Model):
    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, db_index=True)
    gstin = models.CharField(max_length=15, db_index=True)
    is_eco = models.BooleanField(default=False, db_index=True)
    section_code = models.CharField(max_length=16, default="52")
    default_rate = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("1.0000"))
    effective_from = models.DateField(db_index=True)
    effective_to = models.DateField(null=True, blank=True, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "withholding_gst_tcs_eco_profile"
        constraints = [
            models.UniqueConstraint(fields=["entity", "gstin", "effective_from"], name="uq_gst_tcs_eco_scope"),
        ]


class GstTcsComputation(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        LOCKED = "LOCKED", "Locked"
        FILED = "FILED", "Filed"

    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, db_index=True)
    eco_profile = models.ForeignKey(GstTcsEcoProfile, on_delete=models.PROTECT, db_index=True)
    supplier_account = models.ForeignKey("financial.account", on_delete=models.PROTECT, db_index=True)
    doc_date = models.DateField(db_index=True)
    document_type = models.CharField(max_length=20, db_index=True)
    document_id = models.BigIntegerField(db_index=True)
    document_no = models.CharField(max_length=60, blank=True, default="")
    taxable_value = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    gst_tcs_rate = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("1.0000"))
    gst_tcs_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    fy = models.CharField(max_length=9, db_index=True)
    month = models.PositiveSmallIntegerField(db_index=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT, db_index=True)
    snapshot_json = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "withholding_gst_tcs_computation"
        indexes = [
            models.Index(fields=["entity", "fy", "month"], name="ix_gst_tcs_fy_m"),
            models.Index(fields=["document_type", "document_id"], name="ix_gst_tcs_doc"),
        ]
