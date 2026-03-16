from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from financial.models import account
from payroll.base import TimeStampedModel

ZERO2 = Decimal("0.00")
User = settings.AUTH_USER_MODEL


def _load_original(instance):
    if not instance.pk:
        return None
    return instance.__class__.objects.get(pk=instance.pk)


def _changed_fields(instance, *, original=None):
    original = original or _load_original(instance)
    if not original:
        return set()
    changed = set()
    for field in instance._meta.concrete_fields:
        if field.name in {"created_at", "updated_at"}:
            continue
        if getattr(instance, field.attname) != getattr(original, field.attname):
            changed.add(field.name)
    return changed


def _enforce_allowed_changes(instance, *, allowed_fields: set[str], message: str):
    original = _load_original(instance)
    if not original:
        return
    changed = _changed_fields(instance, original=original)
    if changed and not changed.issubset(allowed_fields):
        raise ValidationError(message)


class PayrollComponent(TimeStampedModel):
    class ComponentType(models.TextChoices):
        EARNING = "EARNING", "Earning"
        DEDUCTION = "DEDUCTION", "Deduction"
        EMPLOYER_CONTRIBUTION = "EMPLOYER_CONTRIBUTION", "Employer Contribution"
        REIMBURSEMENT = "REIMBURSEMENT", "Reimbursement"
        RECOVERY = "RECOVERY", "Recovery"

    class PostingBehavior(models.TextChoices):
        GROSS_EARNING = "GROSS_EARNING", "Gross Earning"
        EMPLOYEE_LIABILITY = "EMPLOYEE_LIABILITY", "Employee Liability"
        EMPLOYER_LIABILITY = "EMPLOYER_LIABILITY", "Employer Liability"
        REIMBURSEMENT = "REIMBURSEMENT", "Reimbursement"
        RECOVERY = "RECOVERY", "Recovery"
        MEMO_ONLY = "MEMO_ONLY", "Memo Only"

    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, related_name="payroll_components")
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=120)
    component_type = models.CharField(max_length=30, choices=ComponentType.choices)
    posting_behavior = models.CharField(max_length=30, choices=PostingBehavior.choices)
    is_taxable = models.BooleanField(default=True)
    is_statutory = models.BooleanField(default=False)
    affects_net_pay = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    default_sequence = models.PositiveIntegerField(default=100)
    description = models.CharField(max_length=255, blank=True, default="")
    country_code = models.CharField(max_length=2, blank=True, default="")
    state_code = models.CharField(max_length=10, blank=True, default="")
    statutory_tag = models.CharField(max_length=40, blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["entity", "code"], name="uq_payroll_component_entity_code"),
        ]
        indexes = [
            models.Index(fields=["entity", "component_type"], name="ix_payroll_comp_entity_type"),
            models.Index(fields=["entity", "is_active"], name="ix_payroll_comp_entity_active"),
        ]
        ordering = ["entity_id", "default_sequence", "code"]

    def __str__(self) -> str:
        return f"{self.entity_id}:{self.code}"


class PayrollComponentPosting(TimeStampedModel):
    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, related_name="payroll_component_postings")
    entityfinid = models.ForeignKey(
        "entity.EntityFinancialYear",
        on_delete=models.PROTECT,
        related_name="payroll_component_postings",
    )
    subentity = models.ForeignKey(
        "entity.SubEntity",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="payroll_component_postings",
    )
    component = models.ForeignKey(PayrollComponent, on_delete=models.CASCADE, related_name="posting_maps")
    expense_account = models.ForeignKey(
        account,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payroll_component_expense_maps",
    )
    liability_account = models.ForeignKey(
        account,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payroll_component_liability_maps",
    )
    payable_account = models.ForeignKey(
        account,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payroll_component_payable_maps",
    )
    cost_allocation_required = models.BooleanField(default=False)
    allow_branch_split = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    version_no = models.PositiveIntegerField(default=1)
    effective_from = models.DateField(default=timezone.localdate)
    effective_to = models.DateField(null=True, blank=True)
    approved_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approved_payroll_component_postings",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    superseded_by = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="superseded_component_postings",
    )
    notes = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "entityfinid", "subentity", "component", "version_no"],
                name="uq_payroll_comp_post_ver",
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "entityfinid", "is_active"], name="ix_pay_post_scope_act"),
            models.Index(fields=["component", "effective_from"], name="ix_pay_post_comp_eff"),
        ]

    def __str__(self) -> str:
        return f"{self.entity_id}:{self.component.code}:v{self.version_no}"


class SalaryStructure(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        ACTIVE = "ACTIVE", "Active"
        RETIRED = "RETIRED", "Retired"

    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, related_name="salary_structures")
    entityfinid = models.ForeignKey(
        "entity.EntityFinancialYear",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="salary_structures",
    )
    subentity = models.ForeignKey(
        "entity.SubEntity",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="salary_structures",
    )
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=120)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    notes = models.CharField(max_length=255, blank=True, default="")
    is_active = models.BooleanField(default=True)
    is_template = models.BooleanField(default=False)
    current_version = models.ForeignKey(
        "payroll.SalaryStructureVersion",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "entityfinid", "subentity", "code"],
                name="uq_salary_structure_scope_code",
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "status"], name="ix_sal_struct_ent_stat"),
            models.Index(fields=["entity", "entityfinid", "subentity"], name="ix_sal_struct_scope"),
        ]
        ordering = ["entity_id", "code"]

    def __str__(self) -> str:
        return f"{self.entity_id}:{self.code}"


class SalaryStructureVersion(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        APPROVED = "APPROVED", "Approved"
        RETIRED = "RETIRED", "Retired"

    salary_structure = models.ForeignKey(SalaryStructure, on_delete=models.CASCADE, related_name="versions")
    version_no = models.PositiveIntegerField(default=1)
    effective_from = models.DateField(default=timezone.localdate)
    effective_to = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    calculation_policy_json = models.JSONField(default=dict, blank=True)
    approved_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approved_salary_structure_versions",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["salary_structure", "version_no"],
                name="uq_salary_structure_version",
            ),
        ]
        indexes = [
            models.Index(fields=["salary_structure", "effective_from"], name="ix_sal_struct_ver_eff"),
        ]
        ordering = ["salary_structure_id", "-version_no"]

    def __str__(self) -> str:
        return f"{self.salary_structure.code}:v{self.version_no}"


class SalaryStructureLine(TimeStampedModel):
    class CalculationBasis(models.TextChoices):
        FIXED = "FIXED", "Fixed Amount"
        PERCENT_OF_CTC = "PERCENT_OF_CTC", "Percent of CTC"
        PERCENT_OF_COMPONENT = "PERCENT_OF_COMPONENT", "Percent of Component"
        INPUT = "INPUT", "Manual Input"

    salary_structure = models.ForeignKey(
        SalaryStructure,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    salary_structure_version = models.ForeignKey(
        SalaryStructureVersion,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    component = models.ForeignKey(PayrollComponent, on_delete=models.PROTECT, related_name="salary_structure_lines")
    sequence = models.PositiveIntegerField(default=100)
    calculation_basis = models.CharField(max_length=30, choices=CalculationBasis.choices, default=CalculationBasis.FIXED)
    basis_component = models.ForeignKey(
        PayrollComponent,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="dependent_salary_structure_lines",
    )
    rate = models.DecimalField(max_digits=9, decimal_places=4, default=ZERO2)
    fixed_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    is_pro_rated = models.BooleanField(default=True)
    is_override_allowed = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["salary_structure_version", "component"],
                name="uq_sal_struct_ver_component",
            ),
        ]
        ordering = ["sequence", "id"]

    def __str__(self) -> str:
        parent = self.salary_structure_version or self.salary_structure
        return f"{parent}:{self.component.code}"


class PayrollEmployeeProfile(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        HOLD = "HOLD", "Hold"
        EXITED = "EXITED", "Exited"

    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, related_name="payroll_employee_profiles")
    entityfinid = models.ForeignKey(
        "entity.EntityFinancialYear",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payroll_employee_profiles",
    )
    subentity = models.ForeignKey(
        "entity.SubEntity",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="payroll_employee_profiles",
    )
    employee_user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payroll_profiles",
    )
    employee_code = models.CharField(max_length=40)
    full_name = models.CharField(max_length=200)
    work_email = models.EmailField(blank=True, default="")
    pan = models.CharField(max_length=20, blank=True, default="")
    uan = models.CharField(max_length=20, blank=True, default="")
    date_of_joining = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    salary_structure = models.ForeignKey(
        SalaryStructure,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="employee_profiles",
    )
    salary_structure_version = models.ForeignKey(
        SalaryStructureVersion,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="employee_profiles",
    )
    ctc_annual = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    payment_account = models.ForeignKey(
        account,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payroll_employee_payment_accounts",
    )
    tax_regime = models.CharField(max_length=30, blank=True, default="")
    pay_frequency = models.CharField(max_length=20, default="MONTHLY")
    effective_from = models.DateField(default=timezone.localdate)
    effective_to = models.DateField(null=True, blank=True)
    blocked_for_payroll = models.BooleanField(default=False)
    locked_for_processing = models.BooleanField(default=False)
    extra_data = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["entity", "employee_code"], name="uq_payroll_profile_entity_code"),
        ]
        indexes = [
            models.Index(fields=["entity", "status"], name="ix_pay_prof_ent_stat"),
            models.Index(fields=["entity", "subentity"], name="ix_payroll_profile_entity_sub"),
        ]
        ordering = ["entity_id", "employee_code"]

    def __str__(self) -> str:
        return f"{self.entity_id}:{self.employee_code}"


class PayrollLedgerPolicy(TimeStampedModel):
    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, related_name="payroll_ledger_policies")
    entityfinid = models.ForeignKey(
        "entity.EntityFinancialYear",
        on_delete=models.PROTECT,
        related_name="payroll_ledger_policies",
    )
    subentity = models.ForeignKey(
        "entity.SubEntity",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="payroll_ledger_policies",
    )
    salary_payable_account = models.ForeignKey(
        account,
        on_delete=models.PROTECT,
        related_name="salary_payable_policies",
    )
    payroll_clearing_account = models.ForeignKey(
        account,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payroll_clearing_policies",
    )
    reimbursement_payable_account = models.ForeignKey(
        account,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payroll_reimbursement_policies",
    )
    employer_contribution_payable_account = models.ForeignKey(
        account,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payroll_employer_liability_policies",
    )
    is_active = models.BooleanField(default=True)
    policy_code = models.CharField(max_length=30, default="DEFAULT")
    version_no = models.PositiveIntegerField(default=1)
    effective_from = models.DateField(default=timezone.localdate)
    effective_to = models.DateField(null=True, blank=True)
    policy_json = models.JSONField(default=dict, blank=True)
    approved_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approved_payroll_ledger_policies",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    superseded_by = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="superseded_ledger_policies",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "entityfinid", "subentity", "policy_code", "version_no"],
                name="uq_payroll_ledger_policy_ver",
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "entityfinid", "subentity"], name="ix_payroll_ledger_policy_scope"),
            models.Index(fields=["entity", "entityfinid", "effective_from"], name="ix_payroll_ledger_eff"),
        ]

    def __str__(self) -> str:
        return f"{self.entity_id}:{self.entityfinid_id}:{self.subentity_id or 0}"


class PayrollPeriod(TimeStampedModel):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        LOCKED = "LOCKED", "Locked"
        CLOSED = "CLOSED", "Closed"

    class PayFrequency(models.TextChoices):
        MONTHLY = "MONTHLY", "Monthly"
        WEEKLY = "WEEKLY", "Weekly"
        FORTNIGHTLY = "FORTNIGHTLY", "Fortnightly"
        BI_MONTHLY = "BI_MONTHLY", "Bi-Monthly"

    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, related_name="payroll_periods")
    entityfinid = models.ForeignKey(
        "entity.EntityFinancialYear",
        on_delete=models.PROTECT,
        related_name="payroll_periods",
    )
    subentity = models.ForeignKey(
        "entity.SubEntity",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="payroll_periods",
    )
    code = models.CharField(max_length=30)
    pay_frequency = models.CharField(max_length=20, choices=PayFrequency.choices, default=PayFrequency.MONTHLY)
    period_start = models.DateField()
    period_end = models.DateField()
    payout_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="locked_payroll_periods",
    )
    submitted_for_close_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="submitted_payroll_period_closures",
    )
    submitted_for_close_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="closed_payroll_periods",
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    close_note = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "entityfinid", "subentity", "code"],
                name="uq_payroll_period_scope_code",
            ),
            models.CheckConstraint(check=Q(period_end__gte=models.F("period_start")), name="ck_payroll_period_dates"),
        ]
        indexes = [
            models.Index(fields=["entity", "entityfinid", "period_start"], name="ix_payroll_period_scope_start"),
            models.Index(fields=["entity", "entityfinid", "status"], name="ix_payroll_period_scope_status"),
        ]
        ordering = ["-period_start", "-id"]

    def __str__(self) -> str:
        return self.code


class PayrollAdjustment(TimeStampedModel):
    class Kind(models.TextChoices):
        BONUS = "BONUS", "Bonus"
        INCENTIVE = "INCENTIVE", "Incentive"
        ARREARS = "ARREARS", "Arrears"
        LOAN_RECOVERY = "LOAN_RECOVERY", "Loan Recovery"
        ADVANCE_RECOVERY = "ADVANCE_RECOVERY", "Advance Recovery"
        REIMBURSEMENT = "REIMBURSEMENT", "Reimbursement"
        MANUAL = "MANUAL", "Manual Adjustment"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        APPROVED = "APPROVED", "Approved"
        CANCELLED = "CANCELLED", "Cancelled"

    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, related_name="payroll_adjustments")
    entityfinid = models.ForeignKey(
        "entity.EntityFinancialYear",
        on_delete=models.PROTECT,
        related_name="payroll_adjustments",
    )
    subentity = models.ForeignKey(
        "entity.SubEntity",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="payroll_adjustments",
    )
    employee_profile = models.ForeignKey(
        PayrollEmployeeProfile,
        on_delete=models.PROTECT,
        related_name="adjustments",
    )
    payroll_period = models.ForeignKey(
        PayrollPeriod,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="adjustments",
    )
    component = models.ForeignKey(
        PayrollComponent,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="adjustments",
    )
    kind = models.CharField(max_length=30, choices=Kind.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(ZERO2)])
    effective_date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    remarks = models.CharField(max_length=255, blank=True, default="")
    source_reference_type = models.CharField(max_length=40, blank=True, default="")
    source_reference_id = models.CharField(max_length=80, blank=True, default="")
    approved_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approved_payroll_adjustments",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_run = models.ForeignKey(
        "payroll.PayrollRun",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_adjustments",
    )
    reversed_adjustment = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reversal_adjustments",
    )

    class Meta:
        indexes = [
            models.Index(fields=["entity", "entityfinid", "effective_date"], name="ix_payroll_adj_scope_date"),
            models.Index(fields=["entity", "entityfinid", "status"], name="ix_payroll_adj_scope_status"),
        ]

    def __str__(self) -> str:
        return f"{self.employee_profile.employee_code}:{self.kind}:{self.amount}"


class PayrollRun(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        CALCULATED = "CALCULATED", "Calculated"
        APPROVED = "APPROVED", "Approved"
        POSTED = "POSTED", "Posted"
        CANCELLED = "CANCELLED", "Cancelled"
        REVERSED = "REVERSED", "Reversed"

    class PaymentStatus(models.TextChoices):
        NOT_READY = "NOT_READY", "Not Ready"
        HANDED_OFF = "HANDED_OFF", "Handed Off"
        PARTIALLY_DISBURSED = "PARTIALLY_DISBURSED", "Partially Disbursed"
        DISBURSED = "DISBURSED", "Disbursed"
        FAILED = "FAILED", "Failed"
        RECONCILED = "RECONCILED", "Reconciled"

    class RunType(models.TextChoices):
        REGULAR = "REGULAR", "Regular"
        OFF_CYCLE = "OFF_CYCLE", "Off Cycle"
        ADJUSTMENT = "ADJUSTMENT", "Adjustment"

    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, related_name="payroll_runs")
    entityfinid = models.ForeignKey(
        "entity.EntityFinancialYear",
        on_delete=models.PROTECT,
        related_name="payroll_runs",
    )
    subentity = models.ForeignKey(
        "entity.SubEntity",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="payroll_runs",
    )
    payroll_period = models.ForeignKey(PayrollPeriod, on_delete=models.PROTECT, related_name="runs")
    run_type = models.CharField(max_length=20, choices=RunType.choices, default=RunType.REGULAR)
    doc_code = models.CharField(max_length=10, default="PRUN")
    doc_no = models.PositiveIntegerField(null=True, blank=True)
    run_number = models.CharField(max_length=50, blank=True, default="")
    posting_date = models.DateField(default=timezone.localdate)
    payout_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    payment_status = models.CharField(
        max_length=30,
        choices=PaymentStatus.choices,
        default=PaymentStatus.NOT_READY,
    )

    employee_count = models.PositiveIntegerField(default=0)
    gross_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    deduction_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    employer_contribution_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    reimbursement_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    net_pay_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)

    calculation_payload = models.JSONField(default=dict, blank=True)
    config_snapshot = models.JSONField(default=dict, blank=True)
    approval_note = models.CharField(max_length=255, blank=True, default="")
    status_reason_code = models.CharField(max_length=40, blank=True, default="")
    status_comment = models.CharField(max_length=255, blank=True, default="")
    post_reference = models.CharField(max_length=100, blank=True, default="")
    posted_entry_id = models.PositiveBigIntegerField(null=True, blank=True)
    payment_batch_ref = models.CharField(max_length=80, blank=True, default="")
    payment_handoff_payload = models.JSONField(default=dict, blank=True)
    payment_handed_off_at = models.DateTimeField(null=True, blank=True)
    payment_reconciled_at = models.DateTimeField(null=True, blank=True)
    ledger_policy_version = models.ForeignKey(
        PayrollLedgerPolicy,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payroll_runs",
    )
    statutory_policy_version_ref = models.CharField(max_length=80, blank=True, default="")
    is_immutable = models.BooleanField(default=False)
    correction_of_run = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="correction_runs",
    )
    reversed_run = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reversal_runs",
    )
    reversal_reason = models.CharField(max_length=255, blank=True, default="")
    reversal_posting_entry_id = models.PositiveBigIntegerField(null=True, blank=True)

    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name="created_payroll_runs")
    submitted_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name="submitted_payroll_runs")
    approved_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name="approved_payroll_runs")
    locked_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name="locked_payroll_runs")
    posted_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name="posted_payroll_runs")
    cancelled_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name="cancelled_payroll_runs")
    reversed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name="reversed_payroll_runs")
    approved_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    posted_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    reversed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "entityfinid", "subentity", "payroll_period", "run_type", "correction_of_run"],
                name="uq_payroll_run_scope_period_type",
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "entityfinid", "status"], name="ix_payroll_run_scope_status"),
            models.Index(fields=["entity", "entityfinid", "posting_date"], name="ix_payroll_run_scope_posting"),
            models.Index(fields=["entity", "entityfinid", "payment_status"], name="ix_payroll_run_pay_stat"),
        ]
        ordering = ["-posting_date", "-id"]

    def __str__(self) -> str:
        return self.run_number or f"{self.doc_code}-{self.doc_no or self.id}"

    def clean(self):
        super().clean()
        original = _load_original(self)
        if not original:
            return
        protected = (
            original.is_immutable
            or original.status in {self.Status.POSTED, self.Status.REVERSED}
            or original.payment_status in {
                self.PaymentStatus.HANDED_OFF,
                self.PaymentStatus.PARTIALLY_DISBURSED,
                self.PaymentStatus.DISBURSED,
                self.PaymentStatus.FAILED,
                self.PaymentStatus.RECONCILED,
            }
        )
        if not protected:
            return
        allowed_fields = {
            "status",
            "payment_status",
            "status_reason_code",
            "status_comment",
            "approval_note",
            "post_reference",
            "posted_entry_id",
            "posted_by",
            "posted_at",
            "payment_batch_ref",
            "payment_handoff_payload",
            "payment_handed_off_at",
            "payment_reconciled_at",
            "reversal_reason",
            "reversal_posting_entry_id",
            "reversed_by",
            "reversed_at",
            "updated_at",
        }
        changed = _changed_fields(self, original=original)
        if changed and not changed.issubset(allowed_fields):
            raise ValidationError(
                "This payroll run is operationally locked. Historical payroll data cannot be modified directly."
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        protected = (
            self.is_immutable
            or self.status in {self.Status.APPROVED, self.Status.POSTED, self.Status.CANCELLED, self.Status.REVERSED}
            or self.payment_status in {
                self.PaymentStatus.HANDED_OFF,
                self.PaymentStatus.PARTIALLY_DISBURSED,
                self.PaymentStatus.DISBURSED,
                self.PaymentStatus.FAILED,
                self.PaymentStatus.RECONCILED,
            }
        )
        if protected:
            raise ValidationError("Finalized payroll runs cannot be deleted.")
        return super().delete(*args, **kwargs)


class PayrollRunEmployee(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        HOLD = "HOLD", "Hold"
        SKIPPED = "SKIPPED", "Skipped"

    payroll_run = models.ForeignKey(PayrollRun, on_delete=models.CASCADE, related_name="employee_runs")
    employee_profile = models.ForeignKey(PayrollEmployeeProfile, on_delete=models.PROTECT, related_name="payroll_run_rows")
    salary_structure = models.ForeignKey(
        SalaryStructure,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payroll_run_rows",
    )
    salary_structure_version = models.ForeignKey(
        SalaryStructureVersion,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="run_rows",
    )
    ledger_policy_version = models.ForeignKey(
        PayrollLedgerPolicy,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="run_employee_rows",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    payment_status = models.CharField(
        max_length=30,
        choices=PayrollRun.PaymentStatus.choices,
        default=PayrollRun.PaymentStatus.NOT_READY,
    )
    gross_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    deduction_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    employer_contribution_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    reimbursement_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    payable_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    remarks = models.CharField(max_length=255, blank=True, default="")
    calculation_payload = models.JSONField(default=dict, blank=True)
    statutory_policy_version_ref = models.CharField(max_length=80, blank=True, default="")
    calculation_assumptions = models.JSONField(default=dict, blank=True)
    is_frozen = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["payroll_run", "employee_profile"],
                name="uq_payroll_run_employee",
            ),
        ]
        indexes = [
            models.Index(fields=["payroll_run", "status"], name="ix_payroll_run_employee_status"),
        ]
        ordering = ["employee_profile__employee_code", "id"]

    def __str__(self) -> str:
        return f"{self.payroll_run_id}:{self.employee_profile.employee_code}"

    def clean(self):
        super().clean()
        original = _load_original(self)
        if not original:
            return
        run = getattr(original, "payroll_run", None) or self.payroll_run
        protected = original.is_frozen or run.is_immutable or run.status in {run.Status.POSTED, run.Status.REVERSED}
        if not protected:
            return
        allowed_fields = {"remarks", "payment_status", "updated_at"}
        changed = _changed_fields(self, original=original)
        if changed and not changed.issubset(allowed_fields):
            raise ValidationError(
                "Payroll employee rows are frozen for this run and cannot be modified directly."
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        run = self.payroll_run
        if self.is_frozen or run.is_immutable or run.status in {run.Status.APPROVED, run.Status.POSTED, run.Status.REVERSED}:
            raise ValidationError("Finalized payroll employee rows cannot be deleted.")
        return super().delete(*args, **kwargs)


class PayrollRunEmployeeComponent(TimeStampedModel):
    payroll_run_employee = models.ForeignKey(
        PayrollRunEmployee,
        on_delete=models.CASCADE,
        related_name="components",
    )
    component = models.ForeignKey(PayrollComponent, on_delete=models.PROTECT, related_name="run_components")
    payroll_adjustment = models.ForeignKey(
        PayrollAdjustment,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="run_components",
    )
    component_code = models.CharField(max_length=40)
    component_name = models.CharField(max_length=120)
    component_type = models.CharField(max_length=30)
    posting_behavior = models.CharField(max_length=30)
    component_posting_version = models.ForeignKey(
        PayrollComponentPosting,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="run_components",
    )
    source_structure_line = models.ForeignKey(
        SalaryStructureLine,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="run_components",
    )
    sequence = models.PositiveIntegerField(default=100)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    taxable_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    is_employer_cost = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)
    calculation_basis_snapshot = models.JSONField(default=dict, blank=True)
    is_frozen = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["payroll_run_employee", "sequence"], name="ix_payroll_run_emp_comp_seq"),
            models.Index(fields=["component", "component_type"], name="ix_payroll_run_comp_type"),
        ]
        ordering = ["sequence", "id"]

    def __str__(self) -> str:
        return f"{self.payroll_run_employee_id}:{self.component_code}"

    def clean(self):
        super().clean()
        original = _load_original(self)
        if not original:
            return
        row = getattr(original, "payroll_run_employee", None) or self.payroll_run_employee
        protected = original.is_frozen or row.is_frozen or row.payroll_run.is_immutable
        if not protected:
            return
        raise ValidationError(
            "Payroll component snapshots are immutable after approval and cannot be edited directly."
        )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        row = self.payroll_run_employee
        if self.is_frozen or row.is_frozen or row.payroll_run.is_immutable:
            raise ValidationError("Finalized payroll component snapshots cannot be deleted.")
        return super().delete(*args, **kwargs)


class Payslip(TimeStampedModel):
    payroll_run_employee = models.OneToOneField(
        PayrollRunEmployee,
        on_delete=models.CASCADE,
        related_name="payslip",
    )
    payslip_number = models.CharField(max_length=50)
    version_no = models.PositiveIntegerField(default=1)
    generated_at = models.DateTimeField(default=timezone.now)
    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="published_payslips",
    )
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.CharField(max_length=255, blank=True, default="")
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["payslip_number"], name="uq_payslip_number"),
        ]
        indexes = [
            models.Index(fields=["generated_at"], name="ix_payslip_generated"),
        ]

    def __str__(self) -> str:
        return self.payslip_number

    def clean(self):
        super().clean()
        original = _load_original(self)
        if not original:
            return
        row = getattr(original, "payroll_run_employee", None) or self.payroll_run_employee
        protected = row.is_frozen or row.payroll_run.is_immutable or row.payroll_run.status in {
            row.payroll_run.Status.POSTED,
            row.payroll_run.Status.REVERSED,
        }
        if not protected:
            return
        allowed_fields = {"published_at", "published_by", "voided_at", "void_reason", "updated_at"}
        changed = _changed_fields(self, original=original)
        if changed and not changed.issubset(allowed_fields):
            raise ValidationError("Payslip payload and historical payroll document data are immutable once frozen.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        row = self.payroll_run_employee
        if row.is_frozen or row.payroll_run.is_immutable or row.payroll_run.status in {
            row.payroll_run.Status.APPROVED,
            row.payroll_run.Status.POSTED,
            row.payroll_run.Status.REVERSED,
        }:
            raise ValidationError("Finalized payslips cannot be deleted.")
        return super().delete(*args, **kwargs)


class PayrollRunActionLog(TimeStampedModel):
    class Action(models.TextChoices):
        CREATED = "CREATED", "Created"
        CALCULATED = "CALCULATED", "Calculated"
        SUBMITTED = "SUBMITTED", "Submitted"
        APPROVED = "APPROVED", "Approved"
        POSTED = "POSTED", "Posted"
        PAYMENT_HANDED_OFF = "PAYMENT_HANDED_OFF", "Payment Handed Off"
        PAYMENT_FAILED = "PAYMENT_FAILED", "Payment Failed"
        DISBURSED = "DISBURSED", "Disbursed"
        RECONCILED = "RECONCILED", "Reconciled"
        CANCELLED = "CANCELLED", "Cancelled"
        REVERSED = "REVERSED", "Reversed"

    payroll_run = models.ForeignKey(PayrollRun, on_delete=models.CASCADE, related_name="action_logs")
    action = models.CharField(max_length=40, choices=Action.choices)
    old_status = models.CharField(max_length=20, blank=True, default="")
    new_status = models.CharField(max_length=20, blank=True, default="")
    old_payment_status = models.CharField(max_length=30, blank=True, default="")
    new_payment_status = models.CharField(max_length=30, blank=True, default="")
    acted_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payroll_run_actions",
    )
    reason_code = models.CharField(max_length=40, blank=True, default="")
    comment = models.CharField(max_length=255, blank=True, default="")
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["payroll_run", "action"], name="ix_payrun_action"),
        ]
        ordering = ["created_at", "id"]

    def clean(self):
        super().clean()
        if self.pk:
            raise ValidationError("Payroll audit logs are immutable and cannot be edited.")

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Payroll audit logs are immutable and cannot be edited.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Payroll audit logs are immutable and cannot be deleted.")
