from __future__ import annotations

import uuid
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

    class SemanticCode(models.TextChoices):
        BASIC_PAY = "BASIC_PAY", "Basic Pay"
        HRA = "HRA", "House Rent Allowance"
        SPECIAL_ALLOWANCE = "SPECIAL_ALLOWANCE", "Special Allowance"
        GROSS_EARNING = "GROSS_EARNING", "Gross Earning"
        PF_EMPLOYEE = "PF_EMPLOYEE", "PF Employee"
        PF_EMPLOYER = "PF_EMPLOYER", "PF Employer"
        ESI_EMPLOYEE = "ESI_EMPLOYEE", "ESI Employee"
        ESI_EMPLOYER = "ESI_EMPLOYER", "ESI Employer"
        PT = "PT", "Professional Tax"
        TDS = "TDS", "Tax Deducted at Source"
        LWF_EMPLOYEE = "LWF_EMPLOYEE", "LWF Employee"
        LWF_EMPLOYER = "LWF_EMPLOYER", "LWF Employer"
        OTHER_EARNING = "OTHER_EARNING", "Other Earning"
        OTHER_DEDUCTION = "OTHER_DEDUCTION", "Other Deduction"
        REIMBURSEMENT = "REIMBURSEMENT", "Reimbursement"
        RECOVERY = "RECOVERY", "Recovery"
        OTHER_EMPLOYER_CONTRIBUTION = "OTHER_EMPLOYER_CONTRIBUTION", "Other Employer Contribution"

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
    semantic_code = models.CharField(max_length=40, choices=SemanticCode.choices, blank=True, default="")

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

    @classmethod
    def default_semantic_code_for_code(cls, code: str | None) -> str:
        normalized = str(code or "").strip().upper()
        exact_map = {
            "BASIC": cls.SemanticCode.BASIC_PAY,
            "HRA": cls.SemanticCode.HRA,
            "SPECIAL_ALLOWANCE": cls.SemanticCode.SPECIAL_ALLOWANCE,
            "OTHER_ALLOWANCE": cls.SemanticCode.OTHER_EARNING,
            "BONUS": cls.SemanticCode.OTHER_EARNING,
            "INCENTIVE": cls.SemanticCode.OTHER_EARNING,
            "COMMISSION": cls.SemanticCode.OTHER_EARNING,
            "ARREARS": cls.SemanticCode.OTHER_EARNING,
            "OVERTIME": cls.SemanticCode.OTHER_EARNING,
            "LEAVE_ENCASHMENT": cls.SemanticCode.OTHER_EARNING,
            "REIMBURSEMENT": cls.SemanticCode.REIMBURSEMENT,
            "LOAN_RECOVERY": cls.SemanticCode.RECOVERY,
            "ADVANCE_RECOVERY": cls.SemanticCode.RECOVERY,
            "PF_EMPLOYEE": cls.SemanticCode.PF_EMPLOYEE,
            "PF_EMPLOYER": cls.SemanticCode.PF_EMPLOYER,
            "PROFESSIONAL_TAX": cls.SemanticCode.PT,
            "ESI_EMPLOYEE": cls.SemanticCode.ESI_EMPLOYEE,
            "ESI_EMPLOYER": cls.SemanticCode.ESI_EMPLOYER,
            "TDS": cls.SemanticCode.TDS,
            "LWF_EMPLOYEE": cls.SemanticCode.LWF_EMPLOYEE,
            "LWF_EMPLOYER": cls.SemanticCode.LWF_EMPLOYER,
        }
        return exact_map.get(normalized, "")

    def save(self, *args, **kwargs):
        if not self.semantic_code:
            semantic_code = self.default_semantic_code_for_code(self.code)
            if semantic_code:
                self.semantic_code = semantic_code
                update_fields = kwargs.get("update_fields")
                if update_fields is not None and "semantic_code" not in update_fields:
                    kwargs["update_fields"] = tuple(update_fields) + ("semantic_code",)
        return super().save(*args, **kwargs)


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
    class RuleMode(models.TextChoices):
        STANDARD = "STANDARD", "Standard"
        CUSTOM_FORMULA = "CUSTOM_FORMULA", "Custom Formula"

    class CalculationBasis(models.TextChoices):
        FIXED = "FIXED", "Fixed Amount"
        PERCENT_OF_CTC = "PERCENT_OF_CTC", "Percent of CTC"
        PERCENT_OF_COMPONENT = "PERCENT_OF_COMPONENT", "Percent of Component"
        INPUT = "INPUT", "Manual Input"

    class RecurrenceFrequency(models.TextChoices):
        MONTHLY = "MONTHLY", "Monthly"
        QUARTERLY = "QUARTERLY", "Quarterly"
        HALF_YEARLY = "HALF_YEARLY", "Half-Yearly"
        YEARLY = "YEARLY", "Yearly"
        ONE_TIME = "ONE_TIME", "One-Time"
        OFF_CYCLE = "OFF_CYCLE", "Off-Cycle"

    class CompensationBucket(models.TextChoices):
        FIXED_PAY = "FIXED_PAY", "Fixed Pay"
        VARIABLE_PAY = "VARIABLE_PAY", "Variable Pay"
        EMPLOYER_COST = "EMPLOYER_COST", "Employer Cost"
        REIMBURSEMENT = "REIMBURSEMENT", "Reimbursement"
        RECOVERY = "RECOVERY", "Recovery"
        STATUTORY = "STATUTORY", "Statutory"

    class CTCTreatment(models.TextChoices):
        INCLUDED = "INCLUDED", "Included In CTC"
        EXCLUDED = "EXCLUDED", "Excluded From CTC"
        TARGET_ONLY = "TARGET_ONLY", "Target Variable In CTC"

    class GrossTreatment(models.TextChoices):
        INCLUDED = "INCLUDED", "Included In Gross"
        EXCLUDED = "EXCLUDED", "Excluded From Gross"

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
    rule_mode = models.CharField(max_length=30, choices=RuleMode.choices, default=RuleMode.STANDARD)
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
    recurrence_frequency = models.CharField(
        max_length=20,
        choices=RecurrenceFrequency.choices,
        default=RecurrenceFrequency.MONTHLY,
    )
    compensation_bucket = models.CharField(
        max_length=30,
        choices=CompensationBucket.choices,
        default=CompensationBucket.FIXED_PAY,
    )
    ctc_treatment = models.CharField(
        max_length=20,
        choices=CTCTreatment.choices,
        default=CTCTreatment.INCLUDED,
    )
    gross_treatment = models.CharField(
        max_length=20,
        choices=GrossTreatment.choices,
        default=GrossTreatment.INCLUDED,
    )
    rule_json = models.JSONField(null=True, blank=True, default=None)

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


class ContractPayrollProfile(TimeStampedModel):
    class PayrollStatus(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        ACTIVE = "ACTIVE", "Active"
        HOLD = "HOLD", "Hold"
        ENDED = "ENDED", "Ended"

    class TaxRegime(models.TextChoices):
        OLD = "OLD", "Old Regime"
        NEW = "NEW", "New Regime"
        NOT_SET = "", "Not Set"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, related_name="contract_payroll_profiles")
    hrms_contract = models.ForeignKey("hrms.HrEmploymentContract", on_delete=models.PROTECT, related_name="payroll_profiles")
    pay_frequency = models.CharField(max_length=20, default="MONTHLY")
    payroll_status = models.CharField(max_length=20, choices=PayrollStatus.choices, default=PayrollStatus.DRAFT)
    tax_regime = models.CharField(max_length=20, choices=TaxRegime.choices, blank=True, default="")
    payment_mode = models.CharField(max_length=30, blank=True, default="")
    bank_account = models.ForeignKey(
        account,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="contract_payroll_profiles",
    )
    bank_account_details = models.JSONField(default=dict, blank=True)
    payroll_start_date = models.DateField(default=timezone.localdate)
    payroll_end_date = models.DateField(null=True, blank=True)
    pf_applicable = models.BooleanField(default=False)
    esi_applicable = models.BooleanField(default=False)
    pt_applicable = models.BooleanField(default=False)
    tds_applicable = models.BooleanField(default=False)
    lwf_applicable = models.BooleanField(default=False)
    overtime_eligible = models.BooleanField(default=False)
    attendance_required = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["hrms_contract"],
                condition=Q(is_active=True),
                name="uq_contract_payroll_profile_active_contract",
            ),
            models.CheckConstraint(
                check=Q(payroll_end_date__isnull=True) | Q(payroll_end_date__gte=models.F("payroll_start_date")),
                name="ck_contract_payroll_profile_dates",
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "payroll_status"], name="ix_cpp_status"),
            models.Index(fields=["entity", "is_active"], name="ix_cpp_active"),
            models.Index(fields=["hrms_contract", "payroll_start_date"], name="ix_cpp_contract"),
        ]
        ordering = ["entity_id", "hrms_contract_id", "-payroll_start_date"]

    def __str__(self) -> str:
        return f"{self.entity_id}:{self.hrms_contract.contract_code}"

    @property
    def employee_code(self) -> str:
        return str(getattr(getattr(self.hrms_contract, "employee", None), "employee_number", "") or "")

    @property
    def employee_name(self) -> str:
        return str(getattr(getattr(self.hrms_contract, "employee", None), "display_name", "") or "")

    @property
    def employee_user_id(self) -> int | None:
        return getattr(getattr(self.hrms_contract, "employee", None), "linked_user_id", None)

    def clean(self):
        super().clean()
        if self.hrms_contract.entity_id != self.entity_id:
            raise ValidationError({"hrms_contract": "HRMS contract must belong to the selected entity."})
        if self.payroll_end_date and self.payroll_end_date < self.payroll_start_date:
            raise ValidationError({"payroll_end_date": "Payroll end date must be on or after payroll start date."})
        if self.bank_account_id and getattr(self.bank_account, "entity_id", None) not in (None, self.entity_id):
            raise ValidationError({"bank_account": "Bank account must belong to the same entity."})
        if self.hrms_contract.status not in {
            self.hrms_contract.ContractStatus.ACTIVE,
            self.hrms_contract.ContractStatus.SUSPENDED,
            self.hrms_contract.ContractStatus.NOTICE,
        }:
            raise ValidationError({"hrms_contract": "Only active, suspended, or notice-period contracts can be payroll-bound."})
        if not self.hrms_contract.is_payroll_eligible:
            raise ValidationError({"hrms_contract": "Selected HRMS contract is not payroll eligible."})


class ContractSalaryStructureAssignment(TimeStampedModel):
    class AssignmentStatus(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        ACTIVE = "ACTIVE", "Active"
        SUPERSEDED = "SUPERSEDED", "Superseded"
        ENDED = "ENDED", "Ended"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contract_payroll_profile = models.ForeignKey(
        ContractPayrollProfile,
        on_delete=models.CASCADE,
        related_name="salary_assignments",
    )
    salary_structure = models.ForeignKey(
        SalaryStructure,
        on_delete=models.PROTECT,
        related_name="contract_salary_assignments",
    )
    salary_structure_version = models.ForeignKey(
        SalaryStructureVersion,
        on_delete=models.PROTECT,
        related_name="contract_salary_assignments",
    )
    effective_from = models.DateField(default=timezone.localdate)
    effective_to = models.DateField(null=True, blank=True)
    assignment_status = models.CharField(max_length=20, choices=AssignmentStatus.choices, default=AssignmentStatus.ACTIVE)
    ctc_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    gross_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    metadata = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=Q(effective_to__isnull=True) | Q(effective_to__gte=models.F("effective_from")),
                name="ck_contract_salary_assignment_dates",
            ),
        ]
        indexes = [
            models.Index(fields=["contract_payroll_profile", "effective_from"], name="ix_csa_eff"),
            models.Index(fields=["contract_payroll_profile", "is_active"], name="ix_csa_active"),
            models.Index(fields=["salary_structure", "salary_structure_version"], name="ix_csa_struct"),
        ]
        ordering = ["contract_payroll_profile_id", "-effective_from", "-id"]

    def __str__(self) -> str:
        return f"{self.contract_payroll_profile_id}:{self.salary_structure.code}:v{self.salary_structure_version.version_no}"

    def clean(self):
        super().clean()
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError({"effective_to": "Effective end date must be on or after effective start date."})
        if self.salary_structure_version.salary_structure_id != self.salary_structure_id:
            raise ValidationError({"salary_structure_version": "Selected salary structure version must belong to the selected salary structure."})
        entity_id = self.contract_payroll_profile.entity_id
        if self.salary_structure.entity_id != entity_id:
            raise ValidationError({"salary_structure": "Salary structure must belong to the same entity as the contract payroll profile."})
        if self.salary_structure_version.salary_structure.entity_id != entity_id:
            raise ValidationError({"salary_structure_version": "Salary structure version must belong to the same entity as the contract payroll profile."})


class ContractAttendanceSummary(TimeStampedModel):
    class Source(models.TextChoices):
        MANUAL = "MANUAL", "Manual"
        IMPORT = "IMPORT", "Import"
        ATTENDANCE_ENGINE = "ATTENDANCE_ENGINE", "Attendance Engine"

    class ApprovalStatus(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SUBMITTED = "SUBMITTED", "Submitted"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, related_name="contract_attendance_summaries")
    contract_payroll_profile = models.ForeignKey(
        ContractPayrollProfile,
        on_delete=models.CASCADE,
        related_name="attendance_summaries",
    )
    payroll_period = models.ForeignKey(
        "payroll.PayrollPeriod",
        on_delete=models.PROTECT,
        related_name="contract_attendance_summaries",
    )
    attendance_days = models.DecimalField(max_digits=6, decimal_places=2, default=ZERO2)
    payable_days = models.DecimalField(max_digits=6, decimal_places=2, default=ZERO2)
    lop_days = models.DecimalField(max_digits=6, decimal_places=2, default=ZERO2)
    weekly_off_days = models.DecimalField(max_digits=6, decimal_places=2, default=ZERO2)
    holiday_days = models.DecimalField(max_digits=6, decimal_places=2, default=ZERO2)
    overtime_hours = models.DecimalField(max_digits=8, decimal_places=2, default=ZERO2)
    late_count = models.PositiveIntegerField(default=0)
    half_days = models.DecimalField(max_digits=6, decimal_places=2, default=ZERO2)
    source = models.CharField(max_length=30, choices=Source.choices, default=Source.MANUAL)
    approval_status = models.CharField(max_length=20, choices=ApprovalStatus.choices, default=ApprovalStatus.DRAFT)
    metadata = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["contract_payroll_profile", "payroll_period"],
                condition=Q(is_active=True),
                name="uq_contract_attendance_summary_active_period",
            ),
            models.CheckConstraint(check=Q(attendance_days__gte=ZERO2), name="ck_contract_att_sum_att_gte_zero"),
            models.CheckConstraint(check=Q(payable_days__gte=ZERO2), name="ck_contract_att_sum_payable_gte_zero"),
            models.CheckConstraint(check=Q(lop_days__gte=ZERO2), name="ck_contract_att_sum_lop_gte_zero"),
            models.CheckConstraint(check=Q(overtime_hours__gte=ZERO2), name="ck_contract_att_sum_ot_gte_zero"),
        ]
        indexes = [
            models.Index(fields=["entity", "payroll_period"], name="ix_cattsum_ent_period"),
            models.Index(fields=["contract_payroll_profile", "is_active"], name="ix_cattsum_active"),
        ]
        ordering = ["entity_id", "payroll_period_id", "contract_payroll_profile_id"]

    def __str__(self) -> str:
        return f"{self.contract_payroll_profile_id}:{self.payroll_period.code}"

    def clean(self):
        super().clean()
        if self.contract_payroll_profile.entity_id != self.entity_id:
            raise ValidationError({"contract_payroll_profile": "Contract payroll profile must belong to the selected entity."})
        if self.payroll_period.entity_id != self.entity_id:
            raise ValidationError({"payroll_period": "Payroll period must belong to the selected entity."})
        for field_name in ("attendance_days", "payable_days", "lop_days", "weekly_off_days", "holiday_days", "overtime_hours", "half_days"):
            value = getattr(self, field_name)
            if value is not None and value < ZERO2:
                raise ValidationError({field_name: "Value cannot be negative."})


class ContractAttendanceAdjustment(TimeStampedModel):
    class AdjustmentType(models.TextChoices):
        PAYABLE_DAY = "PAYABLE_DAY", "Payable Day"
        LOP = "LOP", "LOP"
        OVERTIME = "OVERTIME", "Overtime"
        LATE_DEDUCTION = "LATE_DEDUCTION", "Late Deduction"
        HALF_DAY = "HALF_DAY", "Half Day"

    class ApprovalStatus(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SUBMITTED = "SUBMITTED", "Submitted"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, related_name="contract_attendance_adjustments")
    contract_payroll_profile = models.ForeignKey(
        ContractPayrollProfile,
        on_delete=models.CASCADE,
        related_name="attendance_adjustments",
    )
    payroll_period = models.ForeignKey(
        "payroll.PayrollPeriod",
        on_delete=models.PROTECT,
        related_name="contract_attendance_adjustments",
    )
    adjustment_type = models.CharField(max_length=30, choices=AdjustmentType.choices)
    adjustment_value = models.DecimalField(max_digits=8, decimal_places=2)
    remarks = models.CharField(max_length=255, blank=True, default="")
    approval_status = models.CharField(max_length=20, choices=ApprovalStatus.choices, default=ApprovalStatus.DRAFT)
    metadata = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=~Q(adjustment_value=ZERO2),
                name="ck_contract_att_adj_non_zero",
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "payroll_period"], name="ix_cattadj_ent_period"),
            models.Index(fields=["contract_payroll_profile", "is_active"], name="ix_cattadj_active"),
        ]
        ordering = ["entity_id", "payroll_period_id", "contract_payroll_profile_id", "id"]

    def __str__(self) -> str:
        return f"{self.contract_payroll_profile_id}:{self.adjustment_type}:{self.adjustment_value}"

    def clean(self):
        super().clean()
        if self.contract_payroll_profile.entity_id != self.entity_id:
            raise ValidationError({"contract_payroll_profile": "Contract payroll profile must belong to the selected entity."})
        if self.payroll_period.entity_id != self.entity_id:
            raise ValidationError({"payroll_period": "Payroll period must belong to the selected entity."})
        if self.adjustment_value == ZERO2:
            raise ValidationError({"adjustment_value": "Adjustment value cannot be zero."})


class EntityPayrollPolicy(TimeStampedModel):
    class RoundingMode(models.TextChoices):
        HALF_UP = "HALF_UP", "Half Up"
        HALF_DOWN = "HALF_DOWN", "Half Down"
        UP = "UP", "Up"
        DOWN = "DOWN", "Down"
        NONE = "NONE", "None"

    class LOPCalculationMethod(models.TextChoices):
        ATTENDANCE_DAYS = "ATTENDANCE_DAYS", "Attendance Days"
        CALENDAR_DAYS = "CALENDAR_DAYS", "Calendar Days"
        FIXED_DAILY_RATE = "FIXED_DAILY_RATE", "Fixed Daily Rate"
        WORKING_DAYS = "WORKING_DAYS", "Working Days"

    class ArrearCalculationMethod(models.TextChoices):
        FULL_RECALCULATION = "FULL_RECALCULATION", "Full Recalculation"
        DIFFERENTIAL_ONLY = "DIFFERENTIAL_ONLY", "Differential Only"
        MANUAL_APPROVAL = "MANUAL_APPROVAL", "Manual Approval"

    class NegativeSalaryPolicy(models.TextChoices):
        BLOCK = "BLOCK", "Block Processing"
        CARRY_FORWARD = "CARRY_FORWARD", "Carry Forward"
        ALLOW_WITH_APPROVAL = "ALLOW_WITH_APPROVAL", "Allow With Approval"

    class PayslipPublishPolicy(models.TextChoices):
        ON_APPROVAL = "ON_APPROVAL", "On Approval"
        ON_POSTING = "ON_POSTING", "On Posting"
        ON_PAYMENT = "ON_PAYMENT", "On Payment"
        MANUAL = "MANUAL", "Manual"

    class PayrollLockPolicy(models.TextChoices):
        ON_CALCULATION = "ON_CALCULATION", "On Calculation"
        ON_APPROVAL = "ON_APPROVAL", "On Approval"
        ON_POSTING = "ON_POSTING", "On Posting"
        MANUAL = "MANUAL", "Manual"

    class PayFrequency(models.TextChoices):
        MONTHLY = "MONTHLY", "Monthly"
        WEEKLY = "WEEKLY", "Weekly"
        FORTNIGHTLY = "FORTNIGHTLY", "Fortnightly"
        BI_MONTHLY = "BI_MONTHLY", "Bi-Monthly"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, related_name="payroll_policies")
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=255, blank=True, default="")
    pay_frequency = models.CharField(max_length=20, choices=PayFrequency.choices, default=PayFrequency.MONTHLY)
    payroll_month_start_day = models.PositiveSmallIntegerField(default=1)
    payroll_month_end_day = models.PositiveSmallIntegerField(default=31)
    attendance_cutoff_day = models.PositiveSmallIntegerField(default=31)
    salary_disbursement_day = models.PositiveSmallIntegerField(default=1)
    rounding_mode = models.CharField(max_length=20, choices=RoundingMode.choices, default=RoundingMode.HALF_UP)
    net_pay_rounding = models.DecimalField(max_digits=8, decimal_places=2, default=ZERO2)
    component_rounding = models.DecimalField(max_digits=8, decimal_places=2, default=ZERO2)
    lop_calculation_method = models.CharField(
        max_length=30,
        choices=LOPCalculationMethod.choices,
        default=LOPCalculationMethod.ATTENDANCE_DAYS,
    )
    arrear_calculation_method = models.CharField(
        max_length=30,
        choices=ArrearCalculationMethod.choices,
        default=ArrearCalculationMethod.DIFFERENTIAL_ONLY,
    )
    negative_salary_policy = models.CharField(
        max_length=30,
        choices=NegativeSalaryPolicy.choices,
        default=NegativeSalaryPolicy.BLOCK,
    )
    payslip_publish_policy = models.CharField(
        max_length=20,
        choices=PayslipPublishPolicy.choices,
        default=PayslipPublishPolicy.ON_APPROVAL,
    )
    payroll_lock_policy = models.CharField(
        max_length=20,
        choices=PayrollLockPolicy.choices,
        default=PayrollLockPolicy.ON_APPROVAL,
    )
    approval_required = models.BooleanField(default=True)
    effective_from = models.DateField(default=timezone.localdate)
    effective_to = models.DateField(null=True, blank=True)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["entity", "code"], name="uq_entity_payroll_policy_code"),
            models.UniqueConstraint(
                fields=["entity", "pay_frequency"],
                condition=Q(is_default=True, is_active=True),
                name="uq_entity_payroll_policy_default_frequency",
            ),
            models.CheckConstraint(
                check=Q(effective_to__isnull=True) | Q(effective_to__gte=models.F("effective_from")),
                name="ck_entity_payroll_policy_dates",
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "pay_frequency", "is_active"], name="ix_payroll_policy_freq_active"),
            models.Index(fields=["entity", "is_default", "is_active"], name="ix_payroll_policy_default"),
        ]
        ordering = ["entity_id", "pay_frequency", "code"]

    def __str__(self) -> str:
        return f"{self.entity_id}:{self.code}"

    def clean(self):
        super().clean()
        for field_name in (
            "payroll_month_start_day",
            "payroll_month_end_day",
            "attendance_cutoff_day",
            "salary_disbursement_day",
        ):
            value = getattr(self, field_name)
            if value < 1 or value > 31:
                raise ValidationError({field_name: "Day value must be between 1 and 31."})
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError({"effective_to": "Effective end date must be on or after effective start date."})


class PayrollPolicyRule(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    policy = models.ForeignKey(EntityPayrollPolicy, on_delete=models.CASCADE, related_name="rules")
    rule_type = models.CharField(max_length=40)
    rule_key = models.CharField(max_length=60)
    rule_value_json = models.JSONField(default=dict, blank=True)
    effective_from = models.DateField(default=timezone.localdate)
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=Q(effective_to__isnull=True) | Q(effective_to__gte=models.F("effective_from")),
                name="ck_payroll_policy_rule_dates",
            ),
        ]
        indexes = [
            models.Index(fields=["policy", "is_active"], name="ix_policy_rule_active"),
            models.Index(fields=["policy", "rule_type", "rule_key"], name="ix_policy_rule_type_key"),
        ]
        ordering = ["policy_id", "rule_type", "rule_key", "effective_from", "id"]

    def __str__(self) -> str:
        return f"{self.policy.code}:{self.rule_type}:{self.rule_key}"

    def clean(self):
        super().clean()
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError({"effective_to": "Effective end date must be on or after effective start date."})
        if self.effective_from < self.policy.effective_from:
            raise ValidationError({"effective_from": "Rule effective start cannot be earlier than the policy effective start."})
        if self.policy.effective_to and self.effective_to and self.effective_to > self.policy.effective_to:
            raise ValidationError({"effective_to": "Rule effective end cannot be later than the policy effective end."})
        if self.policy.effective_to and self.effective_from > self.policy.effective_to:
            raise ValidationError({"effective_from": "Rule effective start must fall within the policy effective window."})


class RecurringPayItem(TimeStampedModel):
    class ItemType(models.TextChoices):
        EARNING = "EARNING", "Earning"
        DEDUCTION = "DEDUCTION", "Deduction"
        REIMBURSEMENT = "REIMBURSEMENT", "Reimbursement"
        RECOVERY = "RECOVERY", "Recovery"

    class RecurrenceFrequency(models.TextChoices):
        MONTHLY = "MONTHLY", "Monthly"
        WEEKLY = "WEEKLY", "Weekly"
        FORTNIGHTLY = "FORTNIGHTLY", "Fortnightly"
        BI_MONTHLY = "BI_MONTHLY", "Bi-Monthly"
        QUARTERLY = "QUARTERLY", "Quarterly"
        YEARLY = "YEARLY", "Yearly"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, related_name="recurring_pay_items")
    contract_payroll_profile = models.ForeignKey(
        ContractPayrollProfile,
        on_delete=models.CASCADE,
        related_name="recurring_pay_items",
    )
    payroll_component = models.ForeignKey(
        PayrollComponent,
        on_delete=models.PROTECT,
        related_name="recurring_pay_items",
    )
    item_type = models.CharField(max_length=20, choices=ItemType.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2, validators=[MinValueValidator(ZERO2)])
    percentage = models.DecimalField(max_digits=8, decimal_places=4, default=ZERO2, validators=[MinValueValidator(ZERO2)])
    formula_override = models.TextField(blank=True, default="")
    recurrence_frequency = models.CharField(max_length=20, choices=RecurrenceFrequency.choices, default=RecurrenceFrequency.MONTHLY)
    effective_from = models.DateField(default=timezone.localdate)
    effective_to = models.DateField(null=True, blank=True)
    priority = models.PositiveIntegerField(default=100)
    remarks = models.CharField(max_length=255, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=Q(effective_to__isnull=True) | Q(effective_to__gte=models.F("effective_from")),
                name="ck_recurring_pay_item_dates",
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "is_active"], name="ix_rpi_active"),
            models.Index(fields=["contract_payroll_profile", "effective_from"], name="ix_rpi_prof_eff"),
            models.Index(fields=["contract_payroll_profile", "payroll_component"], name="ix_rpi_prof_comp"),
        ]
        ordering = ["contract_payroll_profile_id", "priority", "effective_from", "id"]

    def __str__(self) -> str:
        return f"{self.contract_payroll_profile_id}:{self.payroll_component.code}:{self.item_type}"

    def clean(self):
        super().clean()
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError({"effective_to": "Effective end date must be on or after effective start date."})
        if self.contract_payroll_profile.entity_id != self.entity_id:
            raise ValidationError({"contract_payroll_profile": "Contract payroll profile must belong to the selected entity."})
        if self.payroll_component.entity_id != self.entity_id:
            raise ValidationError({"payroll_component": "Payroll component must belong to the selected entity."})


class OneTimePayItem(TimeStampedModel):
    class ItemType(models.TextChoices):
        EARNING = "EARNING", "Earning"
        DEDUCTION = "DEDUCTION", "Deduction"
        REIMBURSEMENT = "REIMBURSEMENT", "Reimbursement"
        RECOVERY = "RECOVERY", "Recovery"

    class ApprovalStatus(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        CANCELLED = "CANCELLED", "Cancelled"

    class SourceType(models.TextChoices):
        MANUAL = "MANUAL", "Manual"
        ARREAR = "ARREAR", "Arrear"
        INCENTIVE = "INCENTIVE", "Incentive"
        REIMBURSEMENT = "REIMBURSEMENT", "Reimbursement"
        RECOVERY = "RECOVERY", "Recovery"
        ADJUSTMENT = "ADJUSTMENT", "Adjustment"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, related_name="one_time_pay_items")
    contract_payroll_profile = models.ForeignKey(
        ContractPayrollProfile,
        on_delete=models.CASCADE,
        related_name="one_time_pay_items",
    )
    payroll_component = models.ForeignKey(
        PayrollComponent,
        on_delete=models.PROTECT,
        related_name="one_time_pay_items",
    )
    item_type = models.CharField(max_length=20, choices=ItemType.choices)
    payroll_period = models.ForeignKey(
        "payroll.PayrollPeriod",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="one_time_pay_items",
    )
    requested_date = models.DateField(default=timezone.localdate)
    effective_date = models.DateField(default=timezone.localdate)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2, validators=[MinValueValidator(ZERO2)])
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("1.00"), validators=[MinValueValidator(ZERO2)])
    remarks = models.CharField(max_length=255, blank=True, default="")
    approval_status = models.CharField(max_length=20, choices=ApprovalStatus.choices, default=ApprovalStatus.DRAFT)
    source_type = models.CharField(max_length=20, choices=SourceType.choices, default=SourceType.MANUAL)
    metadata = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=["entity", "is_active"], name="ix_otpi_active"),
            models.Index(fields=["contract_payroll_profile", "effective_date"], name="ix_otpi_prof_eff"),
            models.Index(fields=["payroll_period", "approval_status"], name="ix_otpi_period_stat"),
        ]
        ordering = ["contract_payroll_profile_id", "-effective_date", "-requested_date", "-id"]

    def __str__(self) -> str:
        return f"{self.contract_payroll_profile_id}:{self.payroll_component.code}:{self.source_type}"

    def clean(self):
        super().clean()
        if self.contract_payroll_profile.entity_id != self.entity_id:
            raise ValidationError({"contract_payroll_profile": "Contract payroll profile must belong to the selected entity."})
        if self.payroll_component.entity_id != self.entity_id:
            raise ValidationError({"payroll_component": "Payroll component must belong to the selected entity."})
        if self.payroll_period_id:
            if self.payroll_period.entity_id != self.entity_id:
                raise ValidationError({"payroll_period": "Payroll period must belong to the selected entity."})
            if self.payroll_period.subentity_id and self.contract_payroll_profile.hrms_contract.subentity_id not in (None, self.payroll_period.subentity_id):
                raise ValidationError({"payroll_period": "Payroll period subentity must match the contract scope."})
        if self.quantity < ZERO2:
            raise ValidationError({"quantity": "Quantity cannot be negative."})


class StatutoryScheme(TimeStampedModel):
    class SchemeType(models.TextChoices):
        PF = "PF", "PF"
        ESI = "ESI", "ESI"
        PT = "PT", "Professional Tax"
        TDS = "TDS", "TDS"
        LWF = "LWF", "LWF"
        BONUS = "BONUS", "Bonus"
        GRATUITY = "GRATUITY", "Gratuity"
        OTHER = "OTHER", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=120)
    scheme_type = models.CharField(max_length=20, choices=SchemeType.choices, default=SchemeType.OTHER)
    country_code = models.CharField(max_length=2, default="IN")
    state_code = models.CharField(max_length=10, blank=True, default="")
    description = models.CharField(max_length=255, blank=True, default="")
    is_system = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["code", "country_code"],
                condition=Q(state_code=""),
                name="uq_stat_scheme_country",
            ),
            models.UniqueConstraint(
                fields=["code", "country_code", "state_code"],
                condition=~Q(state_code=""),
                name="uq_stat_scheme_country_state",
            ),
        ]
        indexes = [
            models.Index(fields=["scheme_type", "is_active"], name="ix_stat_scheme_type"),
            models.Index(fields=["country_code", "state_code", "is_active"], name="ix_stat_scheme_geo"),
        ]
        ordering = ["country_code", "state_code", "scheme_type", "code"]

    def __str__(self) -> str:
        return f"{self.code}:{self.country_code}:{self.state_code or 'ALL'}"


class StatutoryRule(TimeStampedModel):
    class RuleType(models.TextChoices):
        PERCENTAGE = "PERCENTAGE", "Percentage"
        SLAB = "SLAB", "Slab"
        FIXED = "FIXED", "Fixed"
        FORMULA = "FORMULA", "Formula"
        THRESHOLD = "THRESHOLD", "Threshold"
        ELIGIBILITY = "ELIGIBILITY", "Eligibility"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entity = models.ForeignKey(
        "entity.Entity",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="statutory_rules",
    )
    scheme = models.ForeignKey(StatutoryScheme, on_delete=models.PROTECT, related_name="rules")
    rule_code = models.CharField(max_length=50)
    rule_name = models.CharField(max_length=140)
    rule_type = models.CharField(max_length=20, choices=RuleType.choices)
    effective_from = models.DateField(default=timezone.localdate)
    effective_to = models.DateField(null=True, blank=True)
    rule_json = models.JSONField(default=dict, blank=True)
    applicability_json = models.JSONField(default=dict, blank=True)
    priority = models.PositiveIntegerField(default=100)
    is_system = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=Q(effective_to__isnull=True) | Q(effective_to__gte=models.F("effective_from")),
                name="ck_stat_rule_dates",
            ),
        ]
        indexes = [
            models.Index(fields=["scheme", "is_active"], name="ix_stat_rule_scheme"),
            models.Index(fields=["entity", "scheme", "effective_from"], name="ix_stat_rule_entity"),
            models.Index(fields=["scheme", "rule_type", "priority"], name="ix_stat_rule_type_pri"),
        ]
        ordering = ["scheme_id", "priority", "effective_from", "rule_code"]

    def __str__(self) -> str:
        return f"{self.scheme.code}:{self.rule_code}"

    def clean(self):
        super().clean()
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError({"effective_to": "Effective end date must be on or after effective start date."})


class StatutorySlab(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rule = models.ForeignKey(StatutoryRule, on_delete=models.CASCADE, related_name="slabs")
    slab_from = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2, validators=[MinValueValidator(ZERO2)])
    slab_to = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(ZERO2)])
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2, validators=[MinValueValidator(ZERO2)])
    percentage = models.DecimalField(max_digits=8, decimal_places=4, default=ZERO2, validators=[MinValueValidator(ZERO2)])
    formula = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=Q(slab_to__isnull=True) | Q(slab_to__gte=models.F("slab_from")),
                name="ck_stat_slab_range",
            ),
        ]
        indexes = [
            models.Index(fields=["rule", "is_active"], name="ix_stat_slab_rule"),
            models.Index(fields=["rule", "slab_from"], name="ix_stat_slab_from"),
        ]
        ordering = ["rule_id", "slab_from", "id"]

    def __str__(self) -> str:
        return f"{self.rule.rule_code}:{self.slab_from}-{self.slab_to or 'INF'}"

    def clean(self):
        super().clean()
        if self.slab_to is not None and self.slab_to < self.slab_from:
            raise ValidationError({"slab_to": "Slab end must be on or after slab start."})


class EntityStatutoryRegistration(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, related_name="statutory_registrations")
    scheme = models.ForeignKey(StatutoryScheme, on_delete=models.PROTECT, related_name="entity_registrations")
    registration_number = models.CharField(max_length=80)
    registration_state = models.CharField(max_length=10, blank=True, default="")
    effective_from = models.DateField(default=timezone.localdate)
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "scheme", "registration_number"],
                name="uq_entity_stat_reg_number",
            ),
            models.CheckConstraint(
                check=Q(effective_to__isnull=True) | Q(effective_to__gte=models.F("effective_from")),
                name="ck_entity_stat_reg_dates",
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "scheme", "is_active"], name="ix_stat_reg_active"),
            models.Index(fields=["entity", "registration_state"], name="ix_stat_reg_state"),
        ]
        ordering = ["entity_id", "scheme_id", "registration_state", "registration_number"]

    def __str__(self) -> str:
        return f"{self.entity_id}:{self.scheme.code}:{self.registration_number}"

    def clean(self):
        super().clean()
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError({"effective_to": "Effective end date must be on or after effective start date."})
        if self.scheme.state_code and self.registration_state and self.scheme.state_code != self.registration_state:
            raise ValidationError({"registration_state": "Registration state must match the statutory scheme state."})


class ContractStatutoryProfile(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contract_payroll_profile = models.ForeignKey(
        ContractPayrollProfile,
        on_delete=models.CASCADE,
        related_name="statutory_profiles",
    )
    scheme = models.ForeignKey(StatutoryScheme, on_delete=models.PROTECT, related_name="contract_profiles")
    is_applicable = models.BooleanField(default=True)
    override_rule_json = models.JSONField(default=dict, blank=True)
    effective_from = models.DateField(default=timezone.localdate)
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=Q(effective_to__isnull=True) | Q(effective_to__gte=models.F("effective_from")),
                name="ck_contract_stat_prof_dates",
            ),
        ]
        indexes = [
            models.Index(fields=["contract_payroll_profile", "scheme", "is_active"], name="ix_csp_active"),
            models.Index(fields=["contract_payroll_profile", "effective_from"], name="ix_csp_eff"),
        ]
        ordering = ["contract_payroll_profile_id", "scheme_id", "-effective_from", "-id"]

    def __str__(self) -> str:
        return f"{self.contract_payroll_profile_id}:{self.scheme.code}"

    def clean(self):
        super().clean()
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError({"effective_to": "Effective end date must be on or after effective start date."})


class ContractTaxDeclaration(TimeStampedModel):
    class DeclarationStatus(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SUBMITTED = "SUBMITTED", "Submitted"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    class ApprovalStatus(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SUBMITTED = "SUBMITTED", "Submitted"
        PENDING_APPROVAL = "PENDING_APPROVAL", "Pending Approval"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        CANCELLED = "CANCELLED", "Cancelled"
        LOCKED = "LOCKED", "Locked"

    class TaxRegime(models.TextChoices):
        OLD = "OLD", "Old Regime"
        NEW = "NEW", "New Regime"
        NOT_SET = "", "Not Set"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, related_name="contract_tax_declarations")
    contract_payroll_profile = models.ForeignKey(
        ContractPayrollProfile,
        on_delete=models.CASCADE,
        related_name="tax_declarations",
    )
    financial_year = models.ForeignKey(
        "entity.EntityFinancialYear",
        on_delete=models.PROTECT,
        related_name="contract_tax_declarations",
    )
    approval_status = models.CharField(max_length=20, choices=ApprovalStatus.choices, default=ApprovalStatus.DRAFT)
    tax_regime = models.CharField(max_length=20, choices=TaxRegime.choices, blank=True, default="")
    declaration_status = models.CharField(
        max_length=20,
        choices=DeclarationStatus.choices,
        default=DeclarationStatus.DRAFT,
    )
    declared_annual_income = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    annual_other_income = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    previous_employer_income = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    previous_employer_tds = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    standard_deduction_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    professional_tax_declared = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    annual_gross_projection = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    annual_exemption_total = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    annual_deduction_total = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    projected_taxable_income = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    projected_annual_tax = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    projected_monthly_tds = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    tax_already_deducted = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    balance_tax = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    requested_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="requested_contract_tax_declarations",
    )
    approved_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approved_contract_tax_declarations",
    )
    rejected_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="rejected_contract_tax_declarations",
    )
    cancelled_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="cancelled_contract_tax_declarations",
    )
    locked_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="locked_contract_tax_declarations",
    )
    metadata = models.JSONField(default=dict, blank=True)
    requested_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["contract_payroll_profile", "financial_year"],
                name="uq_contract_tax_declaration_contract_year",
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "financial_year", "is_active"], name="ix_ctd_entity_year"),
            models.Index(fields=["contract_payroll_profile", "declaration_status"], name="ix_ctd_prof_status"),
        ]
        ordering = ["entity_id", "financial_year_id", "contract_payroll_profile_id"]

    def __str__(self) -> str:
        return f"{self.contract_payroll_profile_id}:{self.financial_year_id}"

    def clean(self):
        super().clean()
        if self.contract_payroll_profile.entity_id != self.entity_id:
            raise ValidationError({"contract_payroll_profile": "Contract payroll profile must belong to the selected entity."})
        if self.financial_year.entity_id != self.entity_id:
            raise ValidationError({"financial_year": "Financial year must belong to the selected entity."})


class ContractTaxDeclarationLine(TimeStampedModel):
    class DeclarationCategory(models.TextChoices):
        DEDUCTION = "DEDUCTION", "Deduction"
        EXEMPTION = "EXEMPTION", "Exemption"
        OTHER_INCOME = "OTHER_INCOME", "Other Income"
        INFORMATIONAL = "INFORMATIONAL", "Informational"

    class SectionCode(models.TextChoices):
        SECTION_80C = "80C", "80C"
        SECTION_80D = "80D", "80D"
        HRA = "HRA", "HRA"
        LTA = "LTA", "LTA"
        HOME_LOAN_INTEREST = "HOME_LOAN_INTEREST", "Home Loan Interest"
        OTHER = "OTHER", "Other"

    class EvidenceStatus(models.TextChoices):
        NOT_REQUIRED = "NOT_REQUIRED", "Not Required"
        PENDING = "PENDING", "Pending"
        VERIFIED = "VERIFIED", "Verified"
        REJECTED = "REJECTED", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    declaration = models.ForeignKey(
        ContractTaxDeclaration,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    section_code = models.CharField(max_length=30, choices=SectionCode.choices, default=SectionCode.OTHER)
    declaration_category = models.CharField(
        max_length=20,
        choices=DeclarationCategory.choices,
        default=DeclarationCategory.DEDUCTION,
    )
    declaration_code = models.CharField(max_length=60, blank=True, default="")
    description = models.CharField(max_length=255, blank=True, default="")
    declared_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    approved_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    evidence_required = models.BooleanField(default=False)
    evidence_status = models.CharField(
        max_length=20,
        choices=EvidenceStatus.choices,
        default=EvidenceStatus.PENDING,
    )
    metadata = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=["declaration", "section_code", "is_active"], name="ix_ctdl_decl_section"),
        ]
        ordering = ["declaration_id", "section_code", "id"]

    def __str__(self) -> str:
        return f"{self.declaration_id}:{self.section_code}"


class ContractPayrollInputSnapshot(TimeStampedModel):
    class InputType(models.TextChoices):
        TAX_PROJECTION = "TAX_PROJECTION", "Tax Projection"
        MONTHLY_TDS_PROJECTION = "MONTHLY_TDS_PROJECTION", "Monthly TDS Projection"
        ATTENDANCE_SUMMARY = "ATTENDANCE_SUMMARY", "Attendance Summary"
        MANUAL_PAYROLL_INPUT = "MANUAL_PAYROLL_INPUT", "Manual Payroll Input"

    class SourceType(models.TextChoices):
        MANUAL = "MANUAL", "Manual"
        IMPORT = "IMPORT", "Import"
        SYSTEM = "SYSTEM", "System"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, related_name="contract_payroll_input_snapshots")
    contract_payroll_profile = models.ForeignKey(
        ContractPayrollProfile,
        on_delete=models.CASCADE,
        related_name="input_snapshots",
    )
    payroll_period = models.ForeignKey(
        "payroll.PayrollPeriod",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="contract_input_snapshots",
    )
    input_type = models.CharField(max_length=30, choices=InputType.choices)
    input_json = models.JSONField(default=dict, blank=True)
    source = models.CharField(max_length=20, choices=SourceType.choices, default=SourceType.MANUAL)
    effective_from = models.DateField(default=timezone.localdate)
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=Q(effective_to__isnull=True) | Q(effective_to__gte=models.F("effective_from")),
                name="ck_contract_input_snapshot_dates",
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "input_type", "is_active"], name="ix_cpis_entity_type"),
            models.Index(fields=["contract_payroll_profile", "input_type", "effective_from"], name="ix_cpis_prof_type"),
            models.Index(fields=["payroll_period", "input_type"], name="ix_cpis_period_type"),
        ]
        ordering = ["contract_payroll_profile_id", "input_type", "-effective_from", "-id"]

    def __str__(self) -> str:
        return f"{self.contract_payroll_profile_id}:{self.input_type}"

    def clean(self):
        super().clean()
        if self.contract_payroll_profile.entity_id != self.entity_id:
            raise ValidationError({"contract_payroll_profile": "Contract payroll profile must belong to the selected entity."})
        if self.payroll_period_id:
            if self.payroll_period.entity_id != self.entity_id:
                raise ValidationError({"payroll_period": "Payroll period must belong to the selected entity."})
            if self.payroll_period.subentity_id and self.contract_payroll_profile.hrms_contract.subentity_id not in (None, self.payroll_period.subentity_id):
                raise ValidationError({"payroll_period": "Payroll period subentity must match the contract scope."})
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError({"effective_to": "Effective end date must be on or after effective start date."})


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

    class ApprovalStatus(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SUBMITTED = "SUBMITTED", "Submitted"
        PENDING_APPROVAL = "PENDING_APPROVAL", "Pending Approval"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        CANCELLED = "CANCELLED", "Cancelled"
        LOCKED = "LOCKED", "Locked"

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
    approval_status = models.CharField(max_length=20, choices=ApprovalStatus.choices, default=ApprovalStatus.DRAFT)
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
    rejected_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name="rejected_payroll_runs")
    approved_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
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
            "approval_status",
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
            "requested_by",
            "requested_at",
            "rejected_by",
            "rejected_at",
            "locked_by",
            "locked_at",
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
    contract_payroll_profile = models.ForeignKey(
        ContractPayrollProfile,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payroll_run_rows",
    )
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
                fields=["payroll_run", "contract_payroll_profile"],
                name="uq_payroll_run_contract_employee",
            ),
        ]
        indexes = [
            models.Index(fields=["payroll_run", "status"], name="ix_payroll_run_employee_status"),
            models.Index(fields=["contract_payroll_profile", "status"], name="ix_prun_emp_contract"),
        ]
        ordering = ["contract_payroll_profile__hrms_contract__employee__employee_number", "id"]

    def __str__(self) -> str:
        return f"{self.payroll_run_id}:{self.employee_code or self.contract_payroll_profile_id}"

    @property
    def employee_code(self) -> str:
        return str((self.contract_payroll_profile.employee_code if self.contract_payroll_profile else "") or "")

    @property
    def employee_name(self) -> str:
        return str((self.contract_payroll_profile.employee_name if self.contract_payroll_profile else "") or "")

    @property
    def employee_user_id(self) -> int | None:
        return self.contract_payroll_profile.employee_user_id if self.contract_payroll_profile else None

    @property
    def payment_account_id(self) -> int | None:
        return self.contract_payroll_profile.bank_account_id if self.contract_payroll_profile else None

    def clean(self):
        super().clean()
        if not self.contract_payroll_profile_id:
            raise ValidationError({"contract_payroll_profile": "Contract payroll profile is required for payroll run rows."})
        if self.contract_payroll_profile.entity_id != self.payroll_run.entity_id:
            raise ValidationError({"contract_payroll_profile": "Contract payroll profile must belong to the payroll run entity."})
        if self.payroll_run.subentity_id != getattr(self.contract_payroll_profile.hrms_contract, "subentity_id", None):
            raise ValidationError({"contract_payroll_profile": "Contract payroll profile subentity must match the payroll run scope."})
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
    one_time_pay_item = models.ForeignKey(
        OneTimePayItem,
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


class PayrollPaymentBatch(TimeStampedModel):
    class SourceType(models.TextChoices):
        PAYROLL_RUN = "PAYROLL_RUN", "Payroll Run"
        FNF_SETTLEMENT = "FNF_SETTLEMENT", "FnF Settlement"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        VALIDATED = "VALIDATED", "Validated"
        APPROVED = "APPROVED", "Approved"
        EXPORTED = "EXPORTED", "Exported"
        PAID = "PAID", "Paid"
        FAILED = "FAILED", "Failed"
        CANCELLED = "CANCELLED", "Cancelled"

    class ExportFormat(models.TextChoices):
        GENERIC_CSV = "GENERIC_CSV", "Generic CSV"
        BANK_UPLOAD_PLACEHOLDER = "BANK_UPLOAD_PLACEHOLDER", "Bank Upload Placeholder"

    class ApprovalStatus(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SUBMITTED = "SUBMITTED", "Submitted"
        PENDING_APPROVAL = "PENDING_APPROVAL", "Pending Approval"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        CANCELLED = "CANCELLED", "Cancelled"
        LOCKED = "LOCKED", "Locked"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, related_name="payroll_payment_batches")
    entityfinid = models.ForeignKey(
        "entity.EntityFinancialYear",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payroll_payment_batches",
    )
    subentity = models.ForeignKey(
        "entity.SubEntity",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payroll_payment_batches",
    )
    source_type = models.CharField(max_length=30, choices=SourceType.choices, default=SourceType.PAYROLL_RUN)
    payroll_run = models.ForeignKey(
        PayrollRun,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payment_batches",
    )
    fnf_settlement = models.ForeignKey(
        "payroll.FnFSettlement",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payment_batches",
    )
    batch_number = models.CharField(max_length=60)
    batch_name = models.CharField(max_length=160, blank=True, default="")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    approval_status = models.CharField(max_length=20, choices=ApprovalStatus.choices, default=ApprovalStatus.DRAFT)
    payout_date = models.DateField(null=True, blank=True)
    export_format = models.CharField(
        max_length=40,
        choices=ExportFormat.choices,
        default=ExportFormat.GENERIC_CSV,
    )
    allow_non_positive_amounts = models.BooleanField(default=False)
    total_lines = models.PositiveIntegerField(default=0)
    payable_line_count = models.PositiveIntegerField(default=0)
    skipped_line_count = models.PositiveIntegerField(default=0)
    invalid_line_count = models.PositiveIntegerField(default=0)
    warning_line_count = models.PositiveIntegerField(default=0)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    validation_summary_json = models.JSONField(default=dict, blank=True)
    config_json = models.JSONField(default=dict, blank=True)
    export_reference = models.CharField(max_length=80, blank=True, default="")
    payment_reference = models.CharField(max_length=100, blank=True, default="")
    failure_reason = models.CharField(max_length=255, blank=True, default="")
    cancellation_reason = models.CharField(max_length=255, blank=True, default="")
    approval_remarks = models.CharField(max_length=255, blank=True, default="")
    requested_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="requested_payroll_payment_batches",
    )
    approved_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approved_payroll_payment_batches",
    )
    rejected_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="rejected_payroll_payment_batches",
    )
    exported_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="exported_payroll_payment_batches",
    )
    paid_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="paid_payroll_payment_batches",
    )
    failed_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="failed_payroll_payment_batches",
    )
    cancelled_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="cancelled_payroll_payment_batches",
    )
    locked_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="locked_payroll_payment_batches",
    )
    requested_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    exported_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["entity", "batch_number"], name="uq_payroll_payment_batch_number"),
            models.UniqueConstraint(
                fields=["payroll_run"],
                condition=Q(payroll_run__isnull=False, status__in=["DRAFT", "VALIDATED", "APPROVED", "EXPORTED"]),
                name="uq_payroll_payment_batch_active_run",
            ),
            models.UniqueConstraint(
                fields=["fnf_settlement"],
                condition=Q(fnf_settlement__isnull=False, status__in=["DRAFT", "VALIDATED", "APPROVED", "EXPORTED"]),
                name="uq_payroll_payment_batch_active_fnf",
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "status"], name="ix_pay_payment_batch_status"),
            models.Index(fields=["entity", "source_type"], name="ix_pay_payment_batch_source"),
            models.Index(fields=["payroll_run", "status"], name="ix_pay_payment_batch_run"),
        ]
        ordering = ["-created_at", "batch_number"]

    def __str__(self) -> str:
        return self.batch_number

    def clean(self):
        super().clean()
        if not self.payroll_run_id and not self.fnf_settlement_id:
            raise ValidationError("Payment batch must be linked to either a payroll run or an FnF settlement.")
        if self.payroll_run_id and self.fnf_settlement_id:
            raise ValidationError("Payment batch cannot be linked to both payroll run and FnF settlement.")
        if self.payroll_run_id:
            if self.source_type != self.SourceType.PAYROLL_RUN:
                raise ValidationError({"source_type": "Source type must be payroll run when payroll_run is set."})
            if self.payroll_run.entity_id != self.entity_id:
                raise ValidationError({"payroll_run": "Payroll run must belong to the selected entity."})
            if self.subentity_id != self.payroll_run.subentity_id:
                raise ValidationError({"subentity": "Batch subentity must match the payroll run scope."})
        if self.fnf_settlement_id:
            if self.source_type != self.SourceType.FNF_SETTLEMENT:
                raise ValidationError({"source_type": "Source type must be FnF settlement when fnf_settlement is set."})
            if self.fnf_settlement.entity_id != self.entity_id:
                raise ValidationError({"fnf_settlement": "FnF settlement must belong to the selected entity."})
            if self.subentity_id != self.fnf_settlement.subentity_id:
                raise ValidationError({"subentity": "Batch subentity must match the FnF settlement scope."})


class PayrollPaymentBatchLine(TimeStampedModel):
    class LineStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        VALID = "VALID", "Valid"
        INVALID = "INVALID", "Invalid"
        PAID = "PAID", "Paid"
        FAILED = "FAILED", "Failed"
        SKIPPED = "SKIPPED", "Skipped"
        CANCELLED = "CANCELLED", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(
        PayrollPaymentBatch,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    payroll_run_employee = models.ForeignKey(
        PayrollRunEmployee,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payment_batch_lines",
    )
    fnf_settlement = models.ForeignKey(
        "payroll.FnFSettlement",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payment_batch_lines",
    )
    contract_payroll_profile = models.ForeignKey(
        ContractPayrollProfile,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payment_batch_lines",
    )
    sequence = models.PositiveIntegerField(default=100)
    employee_code = models.CharField(max_length=40, blank=True, default="")
    employee_name = models.CharField(max_length=120, blank=True, default="")
    employee_user_id = models.IntegerField(null=True, blank=True)
    payment_account = models.ForeignKey(
        account,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payroll_payment_batch_lines",
    )
    account_holder_name = models.CharField(max_length=140, blank=True, default="")
    bank_name = models.CharField(max_length=120, blank=True, default="")
    branch_name = models.CharField(max_length=120, blank=True, default="")
    account_number = models.CharField(max_length=64, blank=True, default="")
    ifsc_code = models.CharField(max_length=20, blank=True, default="")
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    narration = models.CharField(max_length=255, blank=True, default="")
    line_status = models.CharField(max_length=20, choices=LineStatus.choices, default=LineStatus.PENDING)
    has_duplicate_account_warning = models.BooleanField(default=False)
    validation_errors_json = models.JSONField(default=list, blank=True)
    validation_warnings_json = models.JSONField(default=list, blank=True)
    source_snapshot_json = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["batch", "payroll_run_employee"],
                condition=Q(payroll_run_employee__isnull=False),
                name="uq_payroll_payment_batch_line_run_employee",
            ),
            models.UniqueConstraint(
                fields=["batch", "fnf_settlement"],
                condition=Q(fnf_settlement__isnull=False),
                name="uq_payroll_payment_batch_line_fnf",
            ),
        ]
        indexes = [
            models.Index(fields=["batch", "line_status"], name="ix_pay_payment_line_status"),
            models.Index(fields=["batch", "sequence"], name="ix_pay_payment_line_seq"),
        ]
        ordering = ["sequence", "created_at", "id"]

    def __str__(self) -> str:
        return f"{self.batch_id}:{self.employee_code or self.employee_name or self.id}"

    def clean(self):
        super().clean()
        if not self.payroll_run_employee_id and not self.fnf_settlement_id:
            raise ValidationError("Payment batch line must be linked to a payroll employee row or an FnF settlement.")
        if self.payroll_run_employee_id and self.fnf_settlement_id:
            raise ValidationError("Payment batch line cannot be linked to both payroll employee row and FnF settlement.")
        if self.payroll_run_employee_id and self.payroll_run_employee.payroll_run_id != self.batch.payroll_run_id:
            raise ValidationError({"payroll_run_employee": "Selected payroll employee row must belong to the batch payroll run."})
        if self.contract_payroll_profile_id and self.batch.entity_id != self.contract_payroll_profile.entity_id:
            raise ValidationError({"contract_payroll_profile": "Contract payroll profile must belong to the batch entity."})


class PayrollPaymentFileExport(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(
        PayrollPaymentBatch,
        on_delete=models.CASCADE,
        related_name="exports",
    )
    export_format = models.CharField(max_length=40, choices=PayrollPaymentBatch.ExportFormat.choices)
    file_name = models.CharField(max_length=160)
    content_type = models.CharField(max_length=80, default="text/csv")
    row_count = models.PositiveIntegerField(default=0)
    file_content = models.TextField(blank=True, default="")
    export_metadata_json = models.JSONField(default=dict, blank=True)
    exported_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payroll_payment_file_exports",
    )
    exported_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["batch", "exported_at"], name="ix_pay_payment_exported"),
        ]
        ordering = ["-exported_at", "-created_at"]

    def __str__(self) -> str:
        return self.file_name


class PayrollPaymentStatusLog(TimeStampedModel):
    batch = models.ForeignKey(
        PayrollPaymentBatch,
        on_delete=models.CASCADE,
        related_name="status_logs",
    )
    old_status = models.CharField(max_length=20, blank=True, default="")
    new_status = models.CharField(max_length=20)
    acted_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payroll_payment_status_logs",
    )
    comment = models.CharField(max_length=255, blank=True, default="")
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["batch", "created_at"], name="ix_pay_payment_log_batch"),
        ]
        ordering = ["created_at", "id"]

    def clean(self):
        super().clean()
        if self.pk:
            raise ValidationError("Payroll payment status logs are immutable and cannot be edited.")

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Payroll payment status logs are immutable and cannot be edited.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Payroll payment status logs are immutable and cannot be deleted.")


class FnFSettlement(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        CALCULATED = "CALCULATED", "Calculated"
        APPROVED = "APPROVED", "Approved"
        POSTED = "POSTED", "Posted"
        PAID = "PAID", "Paid"
        CANCELLED = "CANCELLED", "Cancelled"

    class ApprovalStatus(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SUBMITTED = "SUBMITTED", "Submitted"
        PENDING_APPROVAL = "PENDING_APPROVAL", "Pending Approval"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        CANCELLED = "CANCELLED", "Cancelled"
        LOCKED = "LOCKED", "Locked"

    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, related_name="fnf_settlements")
    entityfinid = models.ForeignKey(
        "entity.EntityFinancialYear",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="fnf_settlements",
    )
    subentity = models.ForeignKey(
        "entity.SubEntity",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="fnf_settlements",
    )
    hrms_contract = models.ForeignKey(
        "hrms.HrEmploymentContract",
        on_delete=models.PROTECT,
        related_name="fnf_settlements",
    )
    contract_payroll_profile = models.ForeignKey(
        ContractPayrollProfile,
        on_delete=models.PROTECT,
        related_name="fnf_settlements",
    )
    salary_structure = models.ForeignKey(
        SalaryStructure,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="fnf_settlements",
    )
    salary_structure_version = models.ForeignKey(
        SalaryStructureVersion,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="fnf_settlements",
    )
    payroll_period = models.ForeignKey(
        "payroll.PayrollPeriod",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="fnf_settlements",
    )
    settlement_number = models.CharField(max_length=50, blank=True, default="")
    separation_date = models.DateField()
    last_working_day = models.DateField()
    settlement_date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    approval_status = models.CharField(max_length=20, choices=ApprovalStatus.choices, default=ApprovalStatus.DRAFT)
    earned_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    deduction_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    recovery_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    reimbursement_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    net_payable_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    net_recoverable_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    calculation_payload = models.JSONField(default=dict, blank=True)
    settlement_snapshot = models.JSONField(default=dict, blank=True)
    approval_note = models.CharField(max_length=255, blank=True, default="")
    post_reference = models.CharField(max_length=100, blank=True, default="")
    payment_reference = models.CharField(max_length=100, blank=True, default="")
    is_recalculation_unlocked = models.BooleanField(default=False)
    requested_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="requested_fnf_settlements",
    )
    approved_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approved_fnf_settlements",
    )
    rejected_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="rejected_fnf_settlements",
    )
    posted_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="posted_fnf_settlements",
    )
    paid_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="paid_fnf_settlements",
    )
    cancelled_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="cancelled_fnf_settlements",
    )
    locked_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="locked_fnf_settlements",
    )
    requested_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    posted_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["hrms_contract"],
                condition=Q(status__in=["DRAFT", "CALCULATED", "APPROVED", "POSTED"]),
                name="uq_fnf_active_contract",
            ),
            models.CheckConstraint(
                check=Q(last_working_day__gte=models.F("separation_date")),
                name="ck_fnf_last_working_day_gte_separation",
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "status"], name="ix_fnf_entity_status"),
            models.Index(fields=["contract_payroll_profile", "status"], name="ix_fnf_profile_status"),
            models.Index(fields=["settlement_date"], name="ix_fnf_settlement_date"),
        ]
        ordering = ["-settlement_date", "-id"]

    def __str__(self) -> str:
        return self.settlement_number or f"FNF-{self.id}"

    def clean(self):
        super().clean()
        if self.contract_payroll_profile.hrms_contract_id != self.hrms_contract_id:
            raise ValidationError({"contract_payroll_profile": "Contract payroll profile must belong to the selected contract."})
        if self.contract_payroll_profile.entity_id != self.entity_id:
            raise ValidationError({"contract_payroll_profile": "Contract payroll profile must belong to the selected entity."})
        if self.hrms_contract.entity_id != self.entity_id:
            raise ValidationError({"hrms_contract": "Employment contract must belong to the selected entity."})
        if self.subentity_id != getattr(self.hrms_contract, "subentity_id", None):
            raise ValidationError({"subentity": "Settlement subentity must match the contract scope."})
        if self.last_working_day < self.separation_date:
            raise ValidationError({"last_working_day": "Last working day must be on or after separation date."})
        if self.payroll_period_id:
            if self.payroll_period.entity_id != self.entity_id:
                raise ValidationError({"payroll_period": "Payroll period must belong to the selected entity."})
            if self.payroll_period.subentity_id != self.subentity_id:
                raise ValidationError({"payroll_period": "Payroll period must match the settlement subentity."})
        if self.salary_structure_version_id and self.salary_structure_id:
            if self.salary_structure_version.salary_structure_id != self.salary_structure_id:
                raise ValidationError({"salary_structure_version": "Salary structure version must belong to the selected salary structure."})
        original = _load_original(self)
        if not original:
            return
        protected = original.status in {self.Status.APPROVED, self.Status.POSTED, self.Status.PAID}
        if not protected:
            return
        allowed_fields = {
            "approval_status",
            "status",
            "post_reference",
            "payment_reference",
            "is_recalculation_unlocked",
            "requested_by",
            "requested_at",
            "approved_by",
            "rejected_by",
            "rejected_at",
            "locked_by",
            "locked_at",
            "posted_by",
            "paid_by",
            "cancelled_by",
            "approved_at",
            "posted_at",
            "paid_at",
            "cancelled_at",
            "approval_note",
            "updated_at",
        }
        changed = _changed_fields(self, original=original)
        if changed and not changed.issubset(allowed_fields):
            raise ValidationError("Approved or finalized FnF settlements cannot be modified directly.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class FnFSettlementComponent(TimeStampedModel):
    class SourceType(models.TextChoices):
        SALARY_LINE = "SALARY_LINE", "Salary Line"
        NOTICE_PAY_RECOVERY = "NOTICE_PAY_RECOVERY", "Notice Pay Recovery"
        NOTICE_PAY_PAYOUT = "NOTICE_PAY_PAYOUT", "Notice Pay Payout"
        LEAVE_ENCASHMENT = "LEAVE_ENCASHMENT", "Leave Encashment"
        GRATUITY_HOOK = "GRATUITY_HOOK", "Gratuity Hook"
        BONUS_PAYOUT = "BONUS_PAYOUT", "Bonus Payout"
        INCENTIVE_PAYOUT = "INCENTIVE_PAYOUT", "Incentive Payout"
        REIMBURSEMENT_PAYABLE = "REIMBURSEMENT_PAYABLE", "Reimbursement Payable"
        LOAN_RECOVERY = "LOAN_RECOVERY", "Loan Recovery"
        ADVANCE_RECOVERY = "ADVANCE_RECOVERY", "Advance Recovery"
        ASSET_RECOVERY = "ASSET_RECOVERY", "Asset Recovery"
        STATUTORY = "STATUTORY", "Statutory"
        TDS_HOOK = "TDS_HOOK", "TDS Hook"
        MANUAL = "MANUAL", "Manual"

    settlement = models.ForeignKey(
        FnFSettlement,
        on_delete=models.CASCADE,
        related_name="components",
    )
    component = models.ForeignKey(
        PayrollComponent,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="fnf_components",
    )
    source_structure_line = models.ForeignKey(
        SalaryStructureLine,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="fnf_components",
    )
    source_type = models.CharField(max_length=30, choices=SourceType.choices)
    component_code = models.CharField(max_length=40, blank=True, default="")
    component_name = models.CharField(max_length=120, blank=True, default="")
    component_type = models.CharField(max_length=30, blank=True, default="")
    posting_behavior = models.CharField(max_length=30, blank=True, default="")
    sequence = models.PositiveIntegerField(default=100)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    base_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO2)
    days = models.DecimalField(max_digits=8, decimal_places=2, default=ZERO2)
    rate = models.DecimalField(max_digits=12, decimal_places=4, default=ZERO2)
    metadata = models.JSONField(default=dict, blank=True)
    calculation_trace = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["settlement", "sequence"], name="ix_fnf_comp_settle_seq"),
            models.Index(fields=["source_type"], name="ix_fnf_comp_source"),
        ]
        ordering = ["sequence", "id"]

    def __str__(self) -> str:
        return f"{self.settlement_id}:{self.source_type}:{self.component_code or self.component_name}"

    def clean(self):
        super().clean()
        original = _load_original(self)
        if not original:
            return
        if original.settlement.status in {
            original.settlement.Status.APPROVED,
            original.settlement.Status.POSTED,
            original.settlement.Status.PAID,
        }:
            raise ValidationError("Finalized FnF settlement components cannot be modified directly.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class GlobalPayrollComponentGroup(TimeStampedModel):
    class GroupType(models.TextChoices):
        EARNINGS = "EARNINGS", "Earnings"
        DEDUCTIONS = "DEDUCTIONS", "Deductions"
        EMPLOYER_CONTRIBUTIONS = "EMPLOYER_CONTRIBUTIONS", "Employer Contributions"
        REIMBURSEMENTS = "REIMBURSEMENTS", "Reimbursements"
        RECOVERIES = "RECOVERIES", "Recoveries"
        INFORMATIONAL = "INFORMATIONAL", "Informational"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=255, blank=True, default="")
    group_type = models.CharField(max_length=40, choices=GroupType.choices)
    sort_order = models.PositiveIntegerField(default=100)
    is_system = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["code"], name="uq_global_payroll_component_group_code"),
        ]
        indexes = [
            models.Index(fields=["group_type", "is_active"], name="ix_glb_pay_comp_group_type_act"),
            models.Index(fields=["sort_order"], name="ix_glb_pay_comp_group_sort"),
        ]
        ordering = ["sort_order", "code"]

    def __str__(self) -> str:
        return self.code


class GlobalPayrollComponent(TimeStampedModel):
    class ComponentType(models.TextChoices):
        EARNING = "EARNING", "Earning"
        DEDUCTION = "DEDUCTION", "Deduction"
        EMPLOYER_CONTRIBUTION = "EMPLOYER_CONTRIBUTION", "Employer Contribution"
        REIMBURSEMENT = "REIMBURSEMENT", "Reimbursement"
        RECOVERY = "RECOVERY", "Recovery"
        INFORMATIONAL = "INFORMATIONAL", "Informational"

    class CalculationType(models.TextChoices):
        FIXED = "FIXED", "Fixed"
        PERCENTAGE = "PERCENTAGE", "Percentage"
        FORMULA = "FORMULA", "Formula"
        SLAB = "SLAB", "Slab"
        MANUAL = "MANUAL", "Manual"
        DERIVED = "DERIVED", "Derived"

    class StatutoryCode(models.TextChoices):
        PF = "PF", "PF"
        ESI = "ESI", "ESI"
        PT = "PT", "PT"
        TDS = "TDS", "TDS"
        LWF = "LWF", "LWF"
        BONUS = "BONUS", "Bonus"
        GRATUITY = "GRATUITY", "Gratuity"
        OTHER = "OTHER", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    group = models.ForeignKey(
        GlobalPayrollComponentGroup,
        on_delete=models.PROTECT,
        related_name="components",
    )
    code = models.CharField(max_length=60)
    name = models.CharField(max_length=140)
    description = models.CharField(max_length=255, blank=True, default="")
    component_type = models.CharField(max_length=40, choices=ComponentType.choices)
    calculation_type = models.CharField(max_length=20, choices=CalculationType.choices)
    default_sequence = models.PositiveIntegerField(default=100)
    default_formula = models.TextField(blank=True, default="")
    default_rule_json = models.JSONField(default=dict, blank=True)
    taxable = models.BooleanField(default=True)
    affects_gross = models.BooleanField(default=True)
    affects_net = models.BooleanField(default=True)
    affects_ctc = models.BooleanField(default=True)
    attendance_dependent = models.BooleanField(default=False)
    lop_dependent = models.BooleanField(default=False)
    overtime_dependent = models.BooleanField(default=False)
    pro_rata = models.BooleanField(default=True)
    statutory_code = models.CharField(max_length=20, choices=StatutoryCode.choices, blank=True, default="")
    country_code = models.CharField(max_length=2, blank=True, default="")
    state_code = models.CharField(max_length=10, blank=True, default="")
    effective_from = models.DateField(default=timezone.localdate)
    effective_to = models.DateField(null=True, blank=True)
    is_system = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["code"], name="uq_global_payroll_component_code"),
            models.CheckConstraint(
                check=Q(effective_to__isnull=True) | Q(effective_to__gte=models.F("effective_from")),
                name="ck_global_pay_component_effective_dates",
            ),
        ]
        indexes = [
            models.Index(fields=["component_type", "is_active"], name="ix_glb_pay_comp_type_act"),
            models.Index(fields=["statutory_code", "is_active"], name="ix_glb_pay_comp_stat_act"),
            models.Index(fields=["default_sequence"], name="ix_glb_pay_comp_seq"),
            models.Index(fields=["effective_from", "effective_to"], name="ix_glb_pay_comp_eff"),
        ]
        ordering = ["default_sequence", "code"]

    def __str__(self) -> str:
        return self.code

    def clean(self):
        super().clean()
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError({"effective_to": "Effective to date cannot be earlier than effective from."})


class GlobalSalaryStructureTemplate(TimeStampedModel):
    class TemplateType(models.TextChoices):
        MONTHLY_STAFF = "MONTHLY_STAFF", "Monthly Staff"
        CTC_BASED = "CTC_BASED", "CTC Based"
        FACTORY_WORKER = "FACTORY_WORKER", "Factory Worker"
        EXECUTIVE = "EXECUTIVE", "Executive"
        SALES_INCENTIVE = "SALES_INCENTIVE", "Sales Incentive"
        CONTRACTOR = "CONTRACTOR", "Contractor"
        INTERN_STIPEND = "INTERN_STIPEND", "Intern Stipend"
        CUSTOM = "CUSTOM", "Custom"

    class PayFrequency(models.TextChoices):
        MONTHLY = "MONTHLY", "Monthly"
        WEEKLY = "WEEKLY", "Weekly"
        FORTNIGHTLY = "FORTNIGHTLY", "Fortnightly"
        BI_MONTHLY = "BI_MONTHLY", "Bi-Monthly"
        QUARTERLY = "QUARTERLY", "Quarterly"
        YEARLY = "YEARLY", "Yearly"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=60)
    name = models.CharField(max_length=160)
    description = models.CharField(max_length=255, blank=True, default="")
    template_type = models.CharField(max_length=40, choices=TemplateType.choices)
    country_code = models.CharField(max_length=2, default="IN")
    state_code = models.CharField(max_length=10, blank=True, default="")
    industry_type = models.CharField(max_length=60, blank=True, default="")
    pay_frequency = models.CharField(max_length=20, choices=PayFrequency.choices, default=PayFrequency.MONTHLY)
    is_default = models.BooleanField(default=False)
    is_system = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    effective_from = models.DateField(default=timezone.localdate)
    effective_to = models.DateField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["code"], name="uq_global_salary_template_code"),
            models.CheckConstraint(
                check=Q(effective_to__isnull=True) | Q(effective_to__gte=models.F("effective_from")),
                name="ck_global_salary_template_effective_dates",
            ),
        ]
        indexes = [
            models.Index(fields=["template_type", "is_active"], name="ix_glb_sal_tpl_type_act"),
            models.Index(fields=["pay_frequency", "is_active"], name="ix_glb_sal_tpl_freq_act"),
            models.Index(fields=["effective_from", "effective_to"], name="ix_glb_sal_tpl_eff"),
        ]
        ordering = ["code"]

    def __str__(self) -> str:
        return self.code

    def clean(self):
        super().clean()
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError({"effective_to": "Effective to date cannot be earlier than effective from."})


class GlobalSalaryStructureTemplateLine(TimeStampedModel):
    class CalculationType(models.TextChoices):
        FIXED = "FIXED", "Fixed"
        PERCENTAGE = "PERCENTAGE", "Percentage"
        FORMULA = "FORMULA", "Formula"
        SLAB = "SLAB", "Slab"
        MANUAL = "MANUAL", "Manual"
        DERIVED = "DERIVED", "Derived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    template = models.ForeignKey(
        GlobalSalaryStructureTemplate,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    component = models.ForeignKey(
        GlobalPayrollComponent,
        on_delete=models.PROTECT,
        related_name="template_lines",
    )
    sequence = models.PositiveIntegerField(default=100)
    calculation_type = models.CharField(max_length=20, choices=CalculationType.choices)
    formula = models.TextField(blank=True, default="")
    rule_json = models.JSONField(default=dict, blank=True)
    amount_default = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    percentage_default = models.DecimalField(max_digits=9, decimal_places=4, default=ZERO2)
    basis_components = models.JSONField(default=list, blank=True)
    min_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    max_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    taxable_override = models.BooleanField(null=True, blank=True)
    affects_gross_override = models.BooleanField(null=True, blank=True)
    affects_net_override = models.BooleanField(null=True, blank=True)
    affects_ctc_override = models.BooleanField(null=True, blank=True)
    pro_rata = models.BooleanField(default=True)
    attendance_dependent = models.BooleanField(default=False)
    lop_dependent = models.BooleanField(default=False)
    applicability_json = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["template", "component"],
                name="uq_global_salary_template_line_component",
            ),
        ]
        indexes = [
            models.Index(fields=["template", "sequence"], name="ix_glb_sal_tpl_line_seq"),
            models.Index(fields=["is_active"], name="ix_glb_sal_tpl_line_active"),
        ]
        ordering = ["sequence", "created_at"]

    def __str__(self) -> str:
        return f"{self.template.code}:{self.component.code}"

    def clean(self):
        super().clean()
        if self.min_amount is not None and self.max_amount is not None and self.max_amount < self.min_amount:
            raise ValidationError({"max_amount": "Maximum amount cannot be smaller than minimum amount."})
