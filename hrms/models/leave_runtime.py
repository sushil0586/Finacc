from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from hrms.base import EntityScopedHrmsModel

User = settings.AUTH_USER_MODEL
ZERO2 = Decimal("0.00")


class ContractLeaveBalanceSnapshot(EntityScopedHrmsModel):
    class SnapshotSource(models.TextChoices):
        OPENING = "opening", "Opening"
        ACCRUAL = "accrual", "Accrual"
        CONSUMPTION = "consumption", "Consumption"
        CARRY_FORWARD = "carry_forward", "Carry Forward"
        LAPSE = "lapse", "Lapse"
        ENCASHMENT = "encashment", "Encashment"
        ADJUSTMENT = "adjustment", "Adjustment"

    contract = models.ForeignKey(
        "hrms.HrEmploymentContract",
        on_delete=models.PROTECT,
        related_name="leave_balance_snapshots",
    )
    leave_policy = models.ForeignKey(
        "hrms.LeavePolicy",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="balance_snapshots",
    )
    leave_type = models.ForeignKey(
        "hrms.LeaveType",
        on_delete=models.PROTECT,
        related_name="balance_snapshots",
    )
    payroll_period_code = models.CharField(max_length=40, blank=True, default="")
    snapshot_date = models.DateField(default=timezone.localdate, db_index=True)
    snapshot_source = models.CharField(max_length=20, choices=SnapshotSource.choices, default=SnapshotSource.ADJUSTMENT)
    opening_balance = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO2, validators=[MinValueValidator(ZERO2)])
    accrued_days = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO2, validators=[MinValueValidator(ZERO2)])
    consumed_days = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO2, validators=[MinValueValidator(ZERO2)])
    carried_forward_days = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO2, validators=[MinValueValidator(ZERO2)])
    lapsed_days = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO2, validators=[MinValueValidator(ZERO2)])
    encashed_days = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO2, validators=[MinValueValidator(ZERO2)])
    closing_balance = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO2, validators=[MinValueValidator(ZERO2)])
    attendance_percentage = models.DecimalField(max_digits=6, decimal_places=2, default=ZERO2, validators=[MinValueValidator(ZERO2)])
    trace_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["contract_id", "leave_type_id", "-snapshot_date", "-created_at"]
        indexes = [
            models.Index(fields=["entity", "contract", "leave_type"], name="ix_hr_leave_bal_contract"),
            models.Index(fields=["entity", "snapshot_date", "snapshot_source"], name="ix_hr_leave_bal_date"),
        ]

    def clean(self):
        if self.contract.entity_id != self.entity_id:
            raise ValidationError({"contract": "Contract must belong to the selected entity."})
        if self.leave_type.entity_id != self.entity_id:
            raise ValidationError({"leave_type": "Leave type must belong to the selected entity."})
        if self.subentity_id != getattr(self.contract, "subentity_id", None):
            raise ValidationError({"subentity": "Snapshot subentity must match the contract scope."})
        if self.leave_policy_id:
            if self.leave_policy.entity_id != self.entity_id:
                raise ValidationError({"leave_policy": "Leave policy must belong to the selected entity."})
            if self.leave_policy.subentity_id not in (None, self.subentity_id):
                raise ValidationError({"leave_policy": "Leave policy must be shared or belong to the same subentity."})

    def save(self, *args, **kwargs):
        self.payroll_period_code = (self.payroll_period_code or "").strip()
        self.full_clean()
        return super().save(*args, **kwargs)


class ContractLeaveLedgerEntry(EntityScopedHrmsModel):
    class EntryType(models.TextChoices):
        OPENING = "opening", "Opening"
        ACCRUAL = "accrual", "Accrual"
        CONSUMPTION = "consumption", "Consumption"
        CARRY_FORWARD = "carry_forward", "Carry Forward"
        LAPSE = "lapse", "Lapse"
        ENCASHMENT = "encashment", "Encashment"
        ADJUSTMENT = "adjustment", "Adjustment"
        REVERSAL = "reversal", "Reversal"

    contract = models.ForeignKey(
        "hrms.HrEmploymentContract",
        on_delete=models.PROTECT,
        related_name="leave_ledger_entries",
    )
    leave_policy = models.ForeignKey(
        "hrms.LeavePolicy",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ledger_entries",
    )
    leave_type = models.ForeignKey(
        "hrms.LeaveType",
        on_delete=models.PROTECT,
        related_name="ledger_entries",
    )
    effective_date = models.DateField(default=timezone.localdate, db_index=True)
    entry_type = models.CharField(max_length=20, choices=EntryType.choices)
    quantity_days = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO2)
    balance_after_days = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO2, validators=[MinValueValidator(ZERO2)])
    reference_type = models.CharField(max_length=40, blank=True, default="")
    reference_id = models.CharField(max_length=80, blank=True, default="")
    payroll_period_code = models.CharField(max_length=40, blank=True, default="")
    trace_json = models.JSONField(default=dict, blank=True)
    remarks = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["contract_id", "leave_type_id", "effective_date", "created_at", "id"]
        indexes = [
            models.Index(fields=["entity", "contract", "leave_type", "effective_date"], name="ix_hr_leave_led_contract"),
            models.Index(fields=["entity", "entry_type", "effective_date"], name="ix_hr_leave_led_type"),
        ]

    def clean(self):
        if self.contract.entity_id != self.entity_id:
            raise ValidationError({"contract": "Contract must belong to the selected entity."})
        if self.leave_type.entity_id != self.entity_id:
            raise ValidationError({"leave_type": "Leave type must belong to the selected entity."})
        if self.subentity_id != getattr(self.contract, "subentity_id", None):
            raise ValidationError({"subentity": "Ledger entry subentity must match the contract scope."})
        if self.leave_policy_id:
            if self.leave_policy.entity_id != self.entity_id:
                raise ValidationError({"leave_policy": "Leave policy must belong to the selected entity."})
            if self.leave_policy.subentity_id not in (None, self.subentity_id):
                raise ValidationError({"leave_policy": "Leave policy must be shared or belong to the same subentity."})
        if self.balance_after_days < ZERO2:
            raise ValidationError({"balance_after_days": "Balance after entry cannot be negative."})

    def save(self, *args, **kwargs):
        self.reference_type = (self.reference_type or "").strip().upper()
        self.reference_id = (self.reference_id or "").strip()
        self.payroll_period_code = (self.payroll_period_code or "").strip()
        self.remarks = (self.remarks or "").strip()
        self.full_clean()
        return super().save(*args, **kwargs)


class LeaveApplication(EntityScopedHrmsModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    class ApprovalStatus(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SUBMITTED = "SUBMITTED", "Submitted"
        PENDING_APPROVAL = "PENDING_APPROVAL", "Pending Approval"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        CANCELLED = "CANCELLED", "Cancelled"
        LOCKED = "LOCKED", "Locked"

    contract = models.ForeignKey(
        "hrms.HrEmploymentContract",
        on_delete=models.PROTECT,
        related_name="leave_applications",
    )
    leave_policy = models.ForeignKey(
        "hrms.LeavePolicy",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="leave_applications",
    )
    leave_type = models.ForeignKey(
        "hrms.LeaveType",
        on_delete=models.PROTECT,
        related_name="applications",
    )
    start_date = models.DateField()
    end_date = models.DateField()
    requested_days = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO2, validators=[MinValueValidator(ZERO2)])
    approved_days = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO2, validators=[MinValueValidator(ZERO2)])
    paid_days = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO2, validators=[MinValueValidator(ZERO2)])
    unpaid_days = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO2, validators=[MinValueValidator(ZERO2)])
    attendance_percentage_snapshot = models.DecimalField(max_digits=6, decimal_places=2, default=ZERO2, validators=[MinValueValidator(ZERO2)])
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    approval_status = models.CharField(max_length=20, choices=ApprovalStatus.choices, default=ApprovalStatus.DRAFT, db_index=True)
    reason = models.CharField(max_length=255, blank=True, default="")
    manager_note = models.CharField(max_length=255, blank=True, default="")
    applied_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="applied_leave_requests",
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="approved_leave_requests",
    )
    rejected_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="rejected_leave_requests",
    )
    cancelled_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cancelled_leave_requests",
    )
    locked_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="locked_leave_requests",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    application_trace_json = models.JSONField(default=dict, blank=True)
    payroll_impact_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-start_date", "-created_at"]
        indexes = [
            models.Index(fields=["entity", "contract", "status"], name="ix_hr_leave_app_contract"),
            models.Index(fields=["entity", "leave_type", "status"], name="ix_hr_leave_app_type"),
            models.Index(fields=["entity", "start_date", "end_date"], name="ix_hr_leave_app_dates"),
        ]

    def clean(self):
        if self.contract.entity_id != self.entity_id:
            raise ValidationError({"contract": "Contract must belong to the selected entity."})
        if self.leave_type.entity_id != self.entity_id:
            raise ValidationError({"leave_type": "Leave type must belong to the selected entity."})
        if self.subentity_id != getattr(self.contract, "subentity_id", None):
            raise ValidationError({"subentity": "Application subentity must match the contract scope."})
        if self.leave_policy_id:
            if self.leave_policy.entity_id != self.entity_id:
                raise ValidationError({"leave_policy": "Leave policy must belong to the selected entity."})
            if self.leave_policy.subentity_id not in (None, self.subentity_id):
                raise ValidationError({"leave_policy": "Leave policy must be shared or belong to the same subentity."})
        if self.end_date < self.start_date:
            raise ValidationError({"end_date": "Leave end date must be on or after the start date."})
        if self.approved_days > self.requested_days:
            raise ValidationError({"approved_days": "Approved days cannot exceed requested days."})
        if (self.paid_days + self.unpaid_days) > self.approved_days:
            raise ValidationError({"paid_days": "Paid and unpaid split cannot exceed approved days."})

    def save(self, *args, **kwargs):
        self.reason = (self.reason or "").strip()
        self.manager_note = (self.manager_note or "").strip()
        self.full_clean()
        return super().save(*args, **kwargs)
