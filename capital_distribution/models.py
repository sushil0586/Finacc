from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from entity.models import Entity, EntityFinancialYear, EntityOwnershipV2, SubEntity
from financial.models import account
from helpers.models import TrackingModel
from posting.models import PostingBatch


class FormationType(models.TextChoices):
    UNCONFIGURED = "unconfigured", "Unconfigured"
    PROPRIETORSHIP = "proprietorship", "Proprietorship"
    PARTNERSHIP = "partnership", "Partnership Firm"
    LLP = "llp", "Limited Liability Partnership"
    COMPANY = "company", "Company"
    OPC = "opc", "One Person Company"
    HUF = "huf", "Hindu Undivided Family"
    TRUST = "trust", "Trust"
    SOCIETY = "society", "Society"
    NGO = "ngo", "NGO"
    SECTION_8 = "section_8", "Section 8 Company"
    COOPERATIVE = "cooperative", "Cooperative"
    GOVERNMENT = "government", "Government Entity"
    PSU = "psu", "Public Sector Undertaking"


WAVE_ONE_FORMATIONS = {
    FormationType.PROPRIETORSHIP,
    FormationType.PARTNERSHIP,
    FormationType.LLP,
}


class EntityFormationProfile(TrackingModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        VERIFIED = "verified", "Verified"
        CONTRADICTORY = "contradictory", "Contradictory"
        UNSUPPORTED = "unsupported", "Unsupported"
        SUPERSEDED = "superseded", "Superseded"

    entity = models.ForeignKey(Entity, on_delete=models.CASCADE, related_name="formation_profiles")
    formation_type = models.CharField(
        max_length=30,
        choices=FormationType.choices,
        default=FormationType.UNCONFIGURED,
        db_index=True,
    )
    strategy_code = models.CharField(max_length=60, blank=True, default="")
    policy_schema_version = models.PositiveIntegerField(default=1)
    version_number = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    effective_from = models.DateField(null=True, blank=True, db_index=True)
    effective_to = models.DateField(null=True, blank=True, db_index=True)
    source = models.CharField(max_length=40, blank=True, default="resolved")
    evidence = models.JSONField(default=dict, blank=True)
    readiness_issues = models.JSONField(default=list, blank=True)
    resolution_hash = models.CharField(max_length=64, blank=True, default="", db_index=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="formation_profiles_verified",
    )
    createdby = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="formation_profiles_created",
    )

    class Meta:
        ordering = ("entity_id", "-version_number", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("entity", "version_number"),
                name="uq_formation_profile_entity_version",
            ),
            models.CheckConstraint(
                condition=Q(effective_to__isnull=True)
                | Q(effective_from__isnull=True)
                | Q(effective_to__gte=models.F("effective_from")),
                name="ck_formation_profile_date_range",
            ),
        ]
        indexes = [
            models.Index(fields=("entity", "status", "effective_from"), name="ix_form_profile_scope_status"),
        ]

    def clean(self):
        if self.effective_from and self.effective_to and self.effective_from > self.effective_to:
            raise ValidationError({"effective_to": "Effective end date must be on or after effective start date."})
        if self.status == self.Status.VERIFIED and self.formation_type == FormationType.UNCONFIGURED:
            raise ValidationError({"formation_type": "An unconfigured formation cannot be verified."})

    def save(self, *args, **kwargs):
        self.strategy_code = (self.strategy_code or "").strip().lower()
        self.source = (self.source or "resolved").strip().lower()
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.entity_id}:{self.formation_type}:v{self.version_number}"


class DistributionPolicyVersion(TrackingModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        SUPERSEDED = "superseded", "Superseded"
        CANCELLED = "cancelled", "Cancelled"

    entity = models.ForeignKey(Entity, on_delete=models.CASCADE, related_name="distribution_policies")
    entityfin = models.ForeignKey(
        EntityFinancialYear,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="distribution_policies",
    )
    subentity = models.ForeignKey(
        SubEntity,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="distribution_policies",
    )
    formation_profile = models.ForeignKey(
        EntityFormationProfile,
        on_delete=models.PROTECT,
        related_name="policies",
    )
    formation_type = models.CharField(max_length=30, choices=FormationType.choices, db_index=True)
    version_number = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    effective_from = models.DateField(db_index=True)
    effective_to = models.DateField(null=True, blank=True, db_index=True)
    governing_document_reference = models.CharField(max_length=255, blank=True, default="")
    configuration = models.JSONField(default=dict, blank=True)
    schema_version = models.PositiveIntegerField(default=1)
    notes = models.TextField(blank=True, default="")
    submitted_at = models.DateTimeField(null=True, blank=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="distribution_policies_submitted",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="distribution_policies_approved",
    )
    createdby = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="distribution_policies_created",
    )

    class Meta:
        ordering = ("entity_id", "-version_number", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("entity", "version_number"),
                name="uq_distribution_policy_entity_version",
            ),
            models.CheckConstraint(
                condition=Q(effective_to__isnull=True) | Q(effective_to__gte=models.F("effective_from")),
                name="ck_distribution_policy_date_range",
            ),
        ]
        indexes = [
            models.Index(fields=("entity", "status", "effective_from"), name="ix_dist_policy_scope_status"),
            models.Index(fields=("entity", "formation_type", "effective_from"), name="ix_dist_policy_form_date"),
        ]

    def clean(self):
        errors = {}
        if self.effective_to and self.effective_from and self.effective_from > self.effective_to:
            errors["effective_to"] = "Effective end date must be on or after effective start date."
        if self.formation_profile_id:
            if self.formation_profile.entity_id != self.entity_id:
                errors["formation_profile"] = "Formation profile must belong to the selected entity."
            if self.formation_type != self.formation_profile.formation_type:
                errors["formation_type"] = "Policy formation must match its formation profile."
        if self.entityfin_id and self.entityfin.entity_id != self.entity_id:
            errors["entityfin"] = "Financial year must belong to the selected entity."
        if self.subentity_id and self.subentity.entity_id != self.entity_id:
            errors["subentity"] = "Subentity must belong to the selected entity."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.governing_document_reference = (self.governing_document_reference or "").strip()
        self.notes = (self.notes or "").strip()
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.entity_id}:{self.formation_type}:policy-v{self.version_number}"


class DistributionPolicyStakeholder(TrackingModel):
    class TargetType(models.TextChoices):
        PROPRIETOR = "proprietor", "Proprietor"
        PARTNER = "partner", "Partner"
        SHAREHOLDER = "shareholder", "Shareholder"
        MEMBER = "member", "Member"
        TRUSTEE = "trustee", "Trustee"
        FUND = "fund", "Fund"
        GOVERNMENT = "government", "Government"
        OTHER = "other", "Other"

    policy = models.ForeignKey(
        DistributionPolicyVersion,
        on_delete=models.CASCADE,
        related_name="stakeholders",
    )
    ownership = models.ForeignKey(
        EntityOwnershipV2,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="distribution_policy_rows",
    )
    target_type = models.CharField(max_length=20, choices=TargetType.choices)
    target_name = models.CharField(max_length=150)
    profit_percentage = models.DecimalField(max_digits=7, decimal_places=4, null=True, blank=True)
    loss_percentage = models.DecimalField(max_digits=7, decimal_places=4, null=True, blank=True)
    destination_account_preference = models.CharField(
        max_length=20,
        choices=EntityOwnershipV2.AccountPreference.choices,
        default=EntityOwnershipV2.AccountPreference.CURRENT,
    )
    configuration = models.JSONField(default=dict, blank=True)
    sort_order = models.PositiveIntegerField(default=100)
    createdby = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="distribution_policy_stakeholders_created",
    )

    class Meta:
        ordering = ("policy_id", "sort_order", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("policy", "ownership"),
                condition=Q(ownership__isnull=False),
                name="uq_dist_policy_ownership",
            ),
            models.CheckConstraint(
                condition=Q(profit_percentage__isnull=True)
                | (Q(profit_percentage__gte=0) & Q(profit_percentage__lte=100)),
                name="ck_dist_policy_profit_pct",
            ),
            models.CheckConstraint(
                condition=Q(loss_percentage__isnull=True)
                | (Q(loss_percentage__gte=0) & Q(loss_percentage__lte=100)),
                name="ck_dist_policy_loss_pct",
            ),
        ]

    def clean(self):
        errors = {}
        if self.ownership_id and self.policy_id and self.ownership.entity_id != self.policy.entity_id:
            errors["ownership"] = "Ownership row must belong to the policy entity."
        if self.policy_id and self.policy.formation_type in WAVE_ONE_FORMATIONS and not self.ownership_id:
            errors["ownership"] = "Wave 1 owner and partner policies require an ownership row."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.target_name = (self.target_name or "").strip()
        self.destination_account_preference = (
            self.destination_account_preference or EntityOwnershipV2.AccountPreference.CURRENT
        ).strip().lower()
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.policy_id}:{self.target_type}:{self.target_name}"


class TaxPolicyVersion(TrackingModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        SUPERSEDED = "superseded", "Superseded"
        CANCELLED = "cancelled", "Cancelled"

    class TaxType(models.TextChoices):
        INCOME_TAX = "income_tax", "Income tax"

    entity = models.ForeignKey(Entity, on_delete=models.CASCADE, related_name="capital_distribution_tax_policies")
    entityfin = models.ForeignKey(
        EntityFinancialYear,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="capital_distribution_tax_policies",
    )
    formation_profile = models.ForeignKey(
        EntityFormationProfile,
        on_delete=models.PROTECT,
        related_name="tax_policies",
    )
    formation_type = models.CharField(max_length=30, choices=FormationType.choices, db_index=True)
    tax_type = models.CharField(max_length=30, choices=TaxType.choices, default=TaxType.INCOME_TAX, db_index=True)
    policy_code = models.CharField(max_length=80, db_index=True)
    version_number = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    jurisdiction_country = models.CharField(max_length=2, default="IN", db_index=True)
    jurisdiction_state = models.CharField(max_length=10, blank=True, default="", db_index=True)
    effective_from = models.DateField(db_index=True)
    effective_to = models.DateField(null=True, blank=True, db_index=True)
    statutory_reference = models.CharField(max_length=255)
    source_url = models.URLField(max_length=500, blank=True, default="")
    source_published_on = models.DateField(null=True, blank=True)
    configuration = models.JSONField(default=dict)
    schema_version = models.PositiveIntegerField(default=1)
    notes = models.TextField(blank=True, default="")
    submitted_at = models.DateTimeField(null=True, blank=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="capital_distribution_tax_policies_submitted",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="capital_distribution_tax_policies_approved",
    )
    createdby = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="capital_distribution_tax_policies_created",
    )

    class Meta:
        ordering = ("entity_id", "policy_code", "-version_number", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("entity", "policy_code", "jurisdiction_country", "jurisdiction_state", "version_number"),
                name="uq_cap_tax_policy_scope_version",
            ),
            models.CheckConstraint(
                condition=Q(effective_to__isnull=True) | Q(effective_to__gte=models.F("effective_from")),
                name="ck_cap_tax_policy_date_range",
            ),
        ]
        indexes = [
            models.Index(
                fields=("entity", "tax_type", "status", "effective_from"),
                name="ix_cap_tax_policy_scope",
            ),
            models.Index(
                fields=("policy_code", "jurisdiction_country", "jurisdiction_state"),
                name="ix_cap_tax_policy_code",
            ),
        ]

    def clean(self):
        errors = {}
        if self.effective_to and self.effective_from and self.effective_from > self.effective_to:
            errors["effective_to"] = "Effective end date must be on or after effective start date."
        if self.entityfin_id and self.entityfin.entity_id != self.entity_id:
            errors["entityfin"] = "Financial year must belong to the selected entity."
        if self.formation_profile_id:
            if self.formation_profile.entity_id != self.entity_id:
                errors["formation_profile"] = "Formation profile must belong to the selected entity."
            if self.formation_profile.formation_type != self.formation_type:
                errors["formation_type"] = "Tax policy formation must match its formation profile."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.policy_code = (self.policy_code or "").strip().lower()
        self.jurisdiction_country = (self.jurisdiction_country or "IN").strip().upper()
        self.jurisdiction_state = (self.jurisdiction_state or "").strip().upper()
        self.statutory_reference = (self.statutory_reference or "").strip()
        self.source_url = (self.source_url or "").strip()
        self.notes = (self.notes or "").strip()
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.entity_id}:{self.policy_code}:tax-v{self.version_number}"


class CapitalDistributionAuditEvent(TrackingModel):
    entity = models.ForeignKey(Entity, on_delete=models.CASCADE, related_name="capital_distribution_audit_events")
    policy = models.ForeignKey(
        DistributionPolicyVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    tax_policy = models.ForeignKey(
        TaxPolicyVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    run = models.ForeignKey(
        "CapitalDistributionRun",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    tax_working = models.ForeignKey(
        "CapitalDistributionTaxWorking",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="capital_distribution_audit_events",
    )
    action = models.CharField(max_length=50, db_index=True)
    correlation_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    reason = models.CharField(max_length=500, blank=True, default="")
    before_state = models.JSONField(default=dict, blank=True)
    after_state = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=("entity", "action", "created_at"), name="ix_cap_dist_audit_scope"),
        ]

    def save(self, *args, **kwargs):
        self.action = (self.action or "").strip().lower()
        self.correlation_id = (self.correlation_id or "").strip()
        self.reason = (self.reason or "").strip()
        super().save(*args, **kwargs)


class CapitalDistributionRun(TrackingModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        CALCULATED = "calculated", "Calculated"
        SUBMITTED = "submitted", "Submitted"
        APPROVED = "approved", "Approved"
        POSTED = "posted", "Posted"
        REVERSED = "reversed", "Reversed"
        STALE = "stale", "Stale"
        CANCELLED = "cancelled", "Cancelled"

    class Cadence(models.TextChoices):
        MONTHLY = "monthly", "Monthly"
        QUARTERLY = "quarterly", "Quarterly"
        CUSTOM = "custom", "Custom"
        ANNUAL = "annual", "Annual"

    class ProfitSource(models.TextChoices):
        POSTED_BOOKS = "posted_books", "Posted books"
        MANUAL_APPROVED = "manual_approved", "Approved manual amount"
        DAY_WEIGHTED = "day_weighted", "Day-weighted annual result"

    entity = models.ForeignKey(Entity, on_delete=models.CASCADE, related_name="capital_distribution_runs")
    entityfin = models.ForeignKey(EntityFinancialYear, on_delete=models.PROTECT, related_name="capital_distribution_runs")
    subentity = models.ForeignKey(
        SubEntity,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="capital_distribution_runs",
    )
    formation_profile = models.ForeignKey(EntityFormationProfile, on_delete=models.PROTECT, related_name="runs")
    policy = models.ForeignKey(DistributionPolicyVersion, on_delete=models.PROTECT, related_name="runs")
    period_from = models.DateField(db_index=True)
    period_to = models.DateField(db_index=True)
    cadence = models.CharField(max_length=20, choices=Cadence.choices, default=Cadence.CUSTOM)
    sequence = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    profit_source = models.CharField(max_length=20, choices=ProfitSource.choices, default=ProfitSource.POSTED_BOOKS)
    source_profit = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    book_adjustments = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    distributable_result = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    calculation_hash = models.CharField(max_length=64, blank=True, default="", db_index=True)
    idempotency_key = models.CharField(max_length=80, db_index=True)
    source_snapshot = models.JSONField(default=dict, blank=True)
    calculated_at = models.DateTimeField(null=True, blank=True)
    calculated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="capital_distribution_runs_calculated",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="capital_distribution_runs_submitted",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="capital_distribution_runs_approved",
    )
    posted_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="capital_distribution_runs_posted",
    )
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="capital_distribution_runs_reversed",
    )
    lifecycle_reason = models.CharField(max_length=500, blank=True, default="")
    posting_batch = models.ForeignKey(
        PostingBatch,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="capital_distribution_original_runs",
    )
    reversal_batch = models.ForeignKey(
        PostingBatch,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="capital_distribution_reversed_runs",
    )
    createdby = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="capital_distribution_runs_created",
    )

    class Meta:
        ordering = ("-period_to", "-id")
        constraints = [
            models.UniqueConstraint(fields=("entity", "idempotency_key"), name="uq_cap_dist_run_idempotency"),
            models.CheckConstraint(condition=Q(period_to__gte=models.F("period_from")), name="ck_cap_dist_run_period"),
        ]
        indexes = [
            models.Index(fields=("entity", "entityfin", "status", "period_from"), name="ix_cap_run_scope_status"),
        ]

    def clean(self):
        errors = {}
        if self.period_from and self.period_to and self.period_from > self.period_to:
            errors["period_to"] = "Period end must be on or after period start."
        if self.entityfin_id and self.entityfin.entity_id != self.entity_id:
            errors["entityfin"] = "Financial year must belong to the run entity."
        if self.subentity_id and self.subentity.entity_id != self.entity_id:
            errors["subentity"] = "Subentity must belong to the run entity."
        if self.policy_id and self.policy.entity_id != self.entity_id:
            errors["policy"] = "Policy must belong to the run entity."
        if self.formation_profile_id and self.formation_profile.entity_id != self.entity_id:
            errors["formation_profile"] = "Formation profile must belong to the run entity."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.idempotency_key = (self.idempotency_key or "").strip()
        self.lifecycle_reason = (self.lifecycle_reason or "").strip()
        self.full_clean()
        super().save(*args, **kwargs)


class CapitalDistributionAccountMapping(TrackingModel):
    entity = models.ForeignKey(Entity, on_delete=models.CASCADE, related_name="capital_distribution_account_mappings")
    ownership = models.ForeignKey(
        EntityOwnershipV2,
        on_delete=models.PROTECT,
        related_name="capital_distribution_account_mappings",
    )
    capital_account = models.ForeignKey(
        account,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="capital_distribution_capital_mappings",
    )
    current_account = models.ForeignKey(
        account,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="capital_distribution_current_mappings",
    )
    drawings_account = models.ForeignKey(
        account,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="capital_distribution_drawings_mappings",
    )
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)
    createdby = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="capital_distribution_account_mappings_created",
    )

    class Meta:
        ordering = ("entity_id", "ownership_id", "-effective_from", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("entity", "ownership"),
                condition=Q(isactive=True),
                name="uq_cap_dist_active_owner_mapping",
            ),
            models.CheckConstraint(
                condition=Q(effective_to__isnull=True)
                | Q(effective_from__isnull=True)
                | Q(effective_to__gte=models.F("effective_from")),
                name="ck_cap_dist_mapping_dates",
            ),
        ]
        indexes = [
            models.Index(fields=("entity", "isactive", "ownership"), name="ix_cap_dist_map_scope_owner"),
        ]

    def clean(self):
        errors = {}
        if self.ownership_id and self.ownership.entity_id != self.entity_id:
            errors["ownership"] = "Ownership row must belong to the selected entity."
        for field_name in ("capital_account", "current_account", "drawings_account"):
            selected = getattr(self, field_name, None)
            if not selected:
                continue
            if selected.entity_id != self.entity_id:
                errors[field_name] = "Mapped account must belong to the selected entity."
            elif not selected.ledger_id:
                errors[field_name] = "Mapped account must be linked to a ledger."
            elif not selected.isactive or not selected.ledger.isactive:
                errors[field_name] = "Mapped account and ledger must be active."
        if not self.capital_account_id and not self.current_account_id:
            errors["current_account"] = "Map at least one capital or current account."
        if self.effective_from and self.effective_to and self.effective_from > self.effective_to:
            errors["effective_to"] = "Effective end date must be on or after effective start date."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def destination_account(self, preference):
        if preference == EntityOwnershipV2.AccountPreference.CAPITAL and self.capital_account_id:
            return self.capital_account
        return self.current_account or self.capital_account


class CapitalDistributionSegment(TrackingModel):
    run = models.ForeignKey(CapitalDistributionRun, on_delete=models.CASCADE, related_name="segments")
    policy = models.ForeignKey(DistributionPolicyVersion, on_delete=models.PROTECT, related_name="run_segments")
    sequence = models.PositiveIntegerField()
    period_from = models.DateField()
    period_to = models.DateField()
    days = models.PositiveIntegerField()
    source_profit = models.DecimalField(max_digits=18, decimal_places=2)
    allocation_basis = models.CharField(max_length=30, default="actual_segment")
    source_snapshot = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("run_id", "sequence")
        constraints = [
            models.UniqueConstraint(fields=("run", "sequence"), name="uq_cap_dist_segment_sequence"),
            models.CheckConstraint(condition=Q(period_to__gte=models.F("period_from")), name="ck_cap_dist_segment_period"),
        ]


class CapitalDistributionLine(TrackingModel):
    class Component(models.TextChoices):
        REMUNERATION = "remuneration", "Remuneration"
        CAPITAL_INTEREST = "capital_interest", "Interest on capital"
        DRAWING_INTEREST = "drawing_interest", "Interest on drawings"
        RESIDUAL_PROFIT = "residual_profit", "Residual profit"
        RESIDUAL_LOSS = "residual_loss", "Residual loss"
        ROUNDING = "rounding", "Rounding"

    class Side(models.TextChoices):
        CREDIT = "credit", "Credit stakeholder"
        DEBIT = "debit", "Debit stakeholder"

    run = models.ForeignKey(CapitalDistributionRun, on_delete=models.CASCADE, related_name="lines")
    segment = models.ForeignKey(CapitalDistributionSegment, on_delete=models.CASCADE, related_name="lines")
    stakeholder = models.ForeignKey(DistributionPolicyStakeholder, on_delete=models.PROTECT, related_name="calculation_lines")
    component_type = models.CharField(max_length=30, choices=Component.choices)
    basis_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    rate = models.DecimalField(max_digits=9, decimal_places=4, null=True, blank=True)
    days = models.PositiveIntegerField(default=0)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    side = models.CharField(max_length=10, choices=Side.choices)
    explanation = models.JSONField(default=dict, blank=True)
    source_references = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ("segment_id", "stakeholder_id", "component_type", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("segment", "stakeholder", "component_type"),
                name="uq_cap_dist_line_identity",
            ),
            models.CheckConstraint(condition=Q(amount__gte=0), name="ck_cap_dist_line_amount"),
        ]


class CapitalDistributionTaxWorking(TrackingModel):
    class Status(models.TextChoices):
        CALCULATED = "calculated", "Calculated"
        SUBMITTED = "submitted", "Submitted"
        APPROVED = "approved", "Approved"
        REVERSED = "reversed", "Reversed"

    entity = models.ForeignKey(Entity, on_delete=models.CASCADE, related_name="capital_distribution_tax_workings")
    entityfin = models.ForeignKey(
        EntityFinancialYear,
        on_delete=models.PROTECT,
        related_name="capital_distribution_tax_workings",
    )
    subentity = models.ForeignKey(
        SubEntity,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="capital_distribution_tax_workings",
    )
    run = models.ForeignKey(CapitalDistributionRun, on_delete=models.PROTECT, related_name="tax_workings")
    tax_policy = models.ForeignKey(TaxPolicyVersion, on_delete=models.PROTECT, related_name="tax_workings")
    period_from = models.DateField(db_index=True)
    period_to = models.DateField(db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.CALCULATED, db_index=True)
    idempotency_key = models.CharField(max_length=80, db_index=True)
    calculation_hash = models.CharField(max_length=64, db_index=True)
    source_snapshot = models.JSONField(default=dict)
    policy_snapshot = models.JSONField(default=dict)
    book_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    allowable_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    disallowed_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    calculated_at = models.DateTimeField(null=True, blank=True)
    calculated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="capital_distribution_tax_workings_calculated",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="capital_distribution_tax_workings_submitted",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="capital_distribution_tax_workings_approved",
    )
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="capital_distribution_tax_workings_reversed",
    )
    lifecycle_reason = models.CharField(max_length=500, blank=True, default="")
    createdby = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="capital_distribution_tax_workings_created",
    )

    class Meta:
        ordering = ("-period_to", "-id")
        constraints = [
            models.UniqueConstraint(fields=("entity", "idempotency_key"), name="uq_cap_tax_work_idempotency"),
            models.UniqueConstraint(fields=("run", "tax_policy"), name="uq_cap_tax_work_run_policy"),
            models.CheckConstraint(condition=Q(period_to__gte=models.F("period_from")), name="ck_cap_tax_work_period"),
            models.CheckConstraint(condition=Q(book_amount__gte=0), name="ck_cap_tax_work_book"),
            models.CheckConstraint(condition=Q(allowable_amount__gte=0), name="ck_cap_tax_work_allowable"),
            models.CheckConstraint(condition=Q(disallowed_amount__gte=0), name="ck_cap_tax_work_disallowed"),
            models.CheckConstraint(
                condition=Q(book_amount=models.F("allowable_amount") + models.F("disallowed_amount")),
                name="ck_cap_tax_work_reconciled",
            ),
        ]
        indexes = [
            models.Index(fields=("entity", "entityfin", "status", "period_from"), name="ix_cap_tax_work_scope"),
        ]

    def clean(self):
        errors = {}
        if self.period_from and self.period_to and self.period_from > self.period_to:
            errors["period_to"] = "Period end must be on or after period start."
        if self.book_amount != self.allowable_amount + self.disallowed_amount:
            errors["allowable_amount"] = "Book amount must equal allowable plus disallowed amount."
        if self.run_id and self.run.entity_id != self.entity_id:
            errors["run"] = "Book run must belong to the working entity."
        elif self.run_id:
            if self.run.entityfin_id != self.entityfin_id:
                errors["entityfin"] = "Financial year must match the source book run."
            if self.run.subentity_id != self.subentity_id:
                errors["subentity"] = "Branch must match the source book run."
            if self.run.period_from != self.period_from or self.run.period_to != self.period_to:
                errors["period_from"] = "Working period must match the source book run."
        if self.tax_policy_id and self.tax_policy.entity_id != self.entity_id:
            errors["tax_policy"] = "Tax policy must belong to the working entity."
        if self.entityfin_id and self.entityfin.entity_id != self.entity_id:
            errors["entityfin"] = "Financial year must belong to the working entity."
        if self.subentity_id and self.subentity.entity_id != self.entity_id:
            errors["subentity"] = "Branch must belong to the working entity."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.idempotency_key = (self.idempotency_key or "").strip()
        self.lifecycle_reason = (self.lifecycle_reason or "").strip()
        self.full_clean()
        super().save(*args, **kwargs)


class CapitalDistributionTaxWorkingLine(TrackingModel):
    working = models.ForeignKey(CapitalDistributionTaxWorking, on_delete=models.CASCADE, related_name="lines")
    source_line = models.ForeignKey(CapitalDistributionLine, on_delete=models.PROTECT, related_name="tax_working_lines")
    component_type = models.CharField(max_length=30, choices=CapitalDistributionLine.Component.choices)
    stakeholder_name = models.CharField(max_length=150)
    book_amount = models.DecimalField(max_digits=18, decimal_places=2)
    treatment = models.CharField(max_length=20)
    calculated_allowable_amount = models.DecimalField(max_digits=18, decimal_places=2)
    calculated_disallowed_amount = models.DecimalField(max_digits=18, decimal_places=2)
    override_allowable_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    allowable_amount = models.DecimalField(max_digits=18, decimal_places=2)
    disallowed_amount = models.DecimalField(max_digits=18, decimal_places=2)
    rule_snapshot = models.JSONField(default=dict)
    source_snapshot = models.JSONField(default=dict)
    override_reason = models.CharField(max_length=500, blank=True, default="")
    evidence_references = models.JSONField(default=list, blank=True)
    overridden_at = models.DateTimeField(null=True, blank=True)
    overridden_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="capital_distribution_tax_working_lines_overridden",
    )

    class Meta:
        ordering = ("working_id", "source_line_id")
        constraints = [
            models.UniqueConstraint(fields=("working", "source_line"), name="uq_cap_tax_work_source_line"),
            models.CheckConstraint(condition=Q(book_amount__gte=0), name="ck_cap_tax_line_book"),
            models.CheckConstraint(condition=Q(allowable_amount__gte=0), name="ck_cap_tax_line_allowable"),
            models.CheckConstraint(condition=Q(disallowed_amount__gte=0), name="ck_cap_tax_line_disallowed"),
            models.CheckConstraint(
                condition=Q(calculated_allowable_amount__gte=0),
                name="ck_cap_tax_line_calc_allowable",
            ),
            models.CheckConstraint(
                condition=Q(calculated_disallowed_amount__gte=0),
                name="ck_cap_tax_line_calc_disallowed",
            ),
            models.CheckConstraint(
                condition=Q(book_amount=models.F("allowable_amount") + models.F("disallowed_amount")),
                name="ck_cap_tax_line_reconciled",
            ),
            models.CheckConstraint(
                condition=Q(
                    book_amount=models.F("calculated_allowable_amount")
                    + models.F("calculated_disallowed_amount")
                ),
                name="ck_cap_tax_line_calc_reconciled",
            ),
            models.CheckConstraint(
                condition=Q(override_allowable_amount__isnull=True)
                | (
                    Q(override_allowable_amount__gte=0)
                    & Q(override_allowable_amount__lte=models.F("book_amount"))
                ),
                name="ck_cap_tax_line_override_range",
            ),
        ]

    def clean(self):
        errors = {}
        if self.source_line_id and self.working_id:
            if self.source_line.run_id != self.working.run_id:
                errors["source_line"] = "Source line must belong to the working's book run."
            if self.source_line.component_type != self.component_type:
                errors["component_type"] = "Component must match the frozen source line."
        if self.book_amount != self.allowable_amount + self.disallowed_amount:
            errors["allowable_amount"] = "Book amount must equal allowable plus disallowed amount."
        if self.book_amount != self.calculated_allowable_amount + self.calculated_disallowed_amount:
            errors["calculated_allowable_amount"] = (
                "Book amount must equal calculated allowable plus calculated disallowed amount."
            )
        if self.override_allowable_amount is not None:
            if self.override_allowable_amount < 0 or self.override_allowable_amount > self.book_amount:
                errors["override_allowable_amount"] = "Override must be between zero and the book amount."
            if not self.override_reason.strip():
                errors["override_reason"] = "An override reason is required."
            if not self.evidence_references:
                errors["evidence_references"] = "At least one evidence reference is required."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.stakeholder_name = (self.stakeholder_name or "").strip()
        self.treatment = (self.treatment or "").strip().lower()
        self.override_reason = (self.override_reason or "").strip()
        self.full_clean()
        super().save(*args, **kwargs)


class DistributionBalanceSnapshot(TrackingModel):
    run = models.ForeignKey(CapitalDistributionRun, on_delete=models.CASCADE, related_name="balance_snapshots")
    stakeholder = models.ForeignKey(DistributionPolicyStakeholder, on_delete=models.PROTECT, related_name="balance_snapshots")
    cutoff_date = models.DateField()
    capital_balance = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    drawing_balance = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    movements = models.JSONField(default=list, blank=True)
    source_references = models.JSONField(default=list, blank=True)
    snapshot_hash = models.CharField(max_length=64, db_index=True)

    class Meta:
        ordering = ("run_id", "stakeholder_id")
        constraints = [
            models.UniqueConstraint(fields=("run", "stakeholder"), name="uq_cap_dist_balance_snapshot"),
        ]
