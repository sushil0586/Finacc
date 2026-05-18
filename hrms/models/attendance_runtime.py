from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from hrms.base import EntityScopedHrmsModel

ZERO2 = Decimal("0.00")
User = settings.AUTH_USER_MODEL


class AttendanceImportBatch(EntityScopedHrmsModel):
    class ImportStatus(models.TextChoices):
        DRAFT = "draft", "Draft"
        UPLOADED = "uploaded", "Uploaded"
        PROCESSED = "processed", "Processed"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    class ImportMode(models.TextChoices):
        PLACEHOLDER = "placeholder", "Placeholder"
        CSV = "csv", "CSV"
        XLSX = "xlsx", "XLSX"
        API = "api", "API"
        DEVICE = "device", "Device"

    batch_code = models.CharField(max_length=60)
    import_mode = models.CharField(max_length=20, choices=ImportMode.choices, default=ImportMode.PLACEHOLDER)
    import_status = models.CharField(max_length=20, choices=ImportStatus.choices, default=ImportStatus.DRAFT)
    file_name = models.CharField(max_length=255, blank=True, default="")
    processed_rows = models.PositiveIntegerField(default=0)
    successful_rows = models.PositiveIntegerField(default=0)
    failed_rows = models.PositiveIntegerField(default=0)
    uploaded_at = models.DateTimeField(default=timezone.now)
    processed_at = models.DateTimeField(null=True, blank=True)
    payload_json = models.JSONField(default=dict, blank=True)
    result_json = models.JSONField(default=dict, blank=True)
    remarks = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["-uploaded_at", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "batch_code"],
                condition=Q(deleted_at__isnull=True),
                name="uq_hrms_att_import_batch_code",
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "import_status", "uploaded_at"], name="ix_hr_att_import_status"),
        ]

    def clean(self):
        super().clean()
        if self.subentity_id and self.subentity and self.subentity.entity_id != self.entity_id:
            raise ValidationError({"subentity": "Subentity must belong to the selected entity."})

    def save(self, *args, **kwargs):
        self.batch_code = (self.batch_code or "").strip().upper()
        self.file_name = (self.file_name or "").strip()
        self.remarks = (self.remarks or "").strip()
        self.full_clean()
        return super().save(*args, **kwargs)


class AttendanceMonthlyClose(EntityScopedHrmsModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        APPROVED = "approved", "Approved"
        CLOSED = "closed", "Closed"
        REOPENED = "reopened", "Reopened"

    payroll_period_code = models.CharField(max_length=30)
    period_start = models.DateField()
    period_end = models.DateField()
    attendance_policy = models.ForeignKey(
        "hrms.AttendancePolicy",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="monthly_closes",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    summary_json = models.JSONField(default=dict, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    submitted_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="submitted_attendance_monthly_closes",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approved_attendance_monthly_closes",
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="closed_attendance_monthly_closes",
    )
    reopened_at = models.DateTimeField(null=True, blank=True)
    reopened_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reopened_attendance_monthly_closes",
    )
    close_note = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["-period_start", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "subentity", "payroll_period_code"],
                condition=Q(deleted_at__isnull=True),
                name="uq_hrms_att_monthly_close_scope_period",
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "status"], name="ix_hr_att_close_status"),
            models.Index(fields=["entity", "payroll_period_code"], name="ix_hr_att_close_period"),
        ]

    def clean(self):
        super().clean()
        if self.period_end < self.period_start:
            raise ValidationError({"period_end": "Period end must be on or after period start."})
        if self.attendance_policy_id:
            if self.attendance_policy.entity_id != self.entity_id:
                raise ValidationError({"attendance_policy": "Attendance policy must belong to the selected entity."})
            if self.attendance_policy.subentity_id not in (None, self.subentity_id):
                raise ValidationError({"attendance_policy": "Attendance policy must be shared or belong to the same subentity."})

    def save(self, *args, **kwargs):
        self.payroll_period_code = (self.payroll_period_code or "").strip().upper()
        self.close_note = (self.close_note or "").strip()
        self.full_clean()
        return super().save(*args, **kwargs)


class AttendanceApproval(EntityScopedHrmsModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    contract = models.ForeignKey(
        "hrms.HrEmploymentContract",
        on_delete=models.CASCADE,
        related_name="attendance_approvals",
    )
    payroll_period_code = models.CharField(max_length=30)
    period_start = models.DateField()
    period_end = models.DateField()
    monthly_close = models.ForeignKey(
        AttendanceMonthlyClose,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approvals",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    summary_json = models.JSONField(default=dict, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    submitted_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="submitted_attendance_approvals",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approved_attendance_approvals",
    )
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="rejected_attendance_approvals",
    )
    review_note = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["-period_start", "contract__contract_code"]
        constraints = [
            models.UniqueConstraint(
                fields=["contract", "payroll_period_code"],
                condition=Q(deleted_at__isnull=True),
                name="uq_hrms_att_approval_contract_period",
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "status"], name="ix_hr_att_approval_status"),
            models.Index(fields=["entity", "payroll_period_code"], name="ix_hr_att_approval_period"),
        ]

    def clean(self):
        super().clean()
        if self.contract.entity_id != self.entity_id:
            raise ValidationError({"contract": "Contract must belong to the selected entity."})
        if self.contract.subentity_id != self.subentity_id:
            raise ValidationError({"subentity": "Approval subentity must match the contract scope."})
        if self.period_end < self.period_start:
            raise ValidationError({"period_end": "Period end must be on or after period start."})
        if self.monthly_close_id:
            if self.monthly_close.entity_id != self.entity_id:
                raise ValidationError({"monthly_close": "Monthly close must belong to the selected entity."})
            if self.monthly_close.payroll_period_code != self.payroll_period_code:
                raise ValidationError({"monthly_close": "Monthly close must belong to the same payroll period."})

    def save(self, *args, **kwargs):
        self.payroll_period_code = (self.payroll_period_code or "").strip().upper()
        self.review_note = (self.review_note or "").strip()
        self.full_clean()
        return super().save(*args, **kwargs)


class DailyAttendance(EntityScopedHrmsModel):
    class AttendanceStatus(models.TextChoices):
        PRESENT = "present", "Present"
        ABSENT = "absent", "Absent"
        HALF_DAY = "half_day", "Half Day"
        WEEKLY_OFF = "weekly_off", "Weekly Off"
        HOLIDAY = "holiday", "Holiday"
        LEAVE = "leave", "Leave"

    class EntrySource(models.TextChoices):
        MANUAL = "manual", "Manual"
        IMPORT = "import", "Import"
        LEAVE_SYNC = "leave_sync", "Leave Sync"
        DEVICE = "device", "Device"
        SYSTEM = "system", "System"

    contract = models.ForeignKey(
        "hrms.HrEmploymentContract",
        on_delete=models.CASCADE,
        related_name="daily_attendance_entries",
    )
    attendance_date = models.DateField()
    status = models.CharField(max_length=20, choices=AttendanceStatus.choices, default=AttendanceStatus.PRESENT)
    leave_application = models.ForeignKey(
        "hrms.LeaveApplication",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="daily_attendance_entries",
    )
    import_batch = models.ForeignKey(
        AttendanceImportBatch,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="daily_entries",
    )
    monthly_close = models.ForeignKey(
        AttendanceMonthlyClose,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="daily_entries",
    )
    source = models.CharField(max_length=20, choices=EntrySource.choices, default=EntrySource.MANUAL)
    overtime_hours = models.DecimalField(max_digits=8, decimal_places=2, default=ZERO2, validators=[MinValueValidator(ZERO2)])
    late_mark = models.BooleanField(default=False)
    attendance_fraction = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("1.00"),
        validators=[MinValueValidator(ZERO2), MaxValueValidator(Decimal("1.00"))],
    )
    payable_fraction = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("1.00"),
        validators=[MinValueValidator(ZERO2), MaxValueValidator(Decimal("1.00"))],
    )
    lop_fraction = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=ZERO2,
        validators=[MinValueValidator(ZERO2), MaxValueValidator(Decimal("1.00"))],
    )
    remarks = models.CharField(max_length=255, blank=True, default="")
    trace_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["contract_id", "attendance_date", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["contract", "attendance_date"],
                condition=Q(deleted_at__isnull=True),
                name="uq_hrms_daily_attendance_contract_date",
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "attendance_date", "status"], name="ix_hr_daily_att_status"),
            models.Index(fields=["entity", "contract", "attendance_date"], name="ix_hr_daily_att_contract"),
        ]

    def clean(self):
        super().clean()
        if self.contract.entity_id != self.entity_id:
            raise ValidationError({"contract": "Contract must belong to the selected entity."})
        if self.contract.subentity_id != self.subentity_id:
            raise ValidationError({"subentity": "Attendance subentity must match the contract scope."})
        if self.leave_application_id:
            if self.leave_application.entity_id != self.entity_id:
                raise ValidationError({"leave_application": "Leave application must belong to the selected entity."})
            if self.leave_application.contract_id != self.contract_id:
                raise ValidationError({"leave_application": "Leave application must belong to the same contract."})
        if self.import_batch_id:
            if self.import_batch.entity_id != self.entity_id:
                raise ValidationError({"import_batch": "Import batch must belong to the selected entity."})
            if self.import_batch.subentity_id not in (None, self.subentity_id):
                raise ValidationError({"import_batch": "Import batch must be shared or belong to the same subentity."})
        if self.monthly_close_id:
            if self.monthly_close.entity_id != self.entity_id:
                raise ValidationError({"monthly_close": "Monthly close must belong to the selected entity."})
            if self.monthly_close.subentity_id != self.subentity_id:
                raise ValidationError({"monthly_close": "Monthly close must match the attendance scope."})
            if self.monthly_close.status == AttendanceMonthlyClose.Status.CLOSED:
                raise ValidationError({"monthly_close": "Closed attendance months cannot be edited."})

    def save(self, *args, **kwargs):
        self.remarks = (self.remarks or "").strip()
        self.full_clean()
        return super().save(*args, **kwargs)


class AttendanceDeviceLog(EntityScopedHrmsModel):
    class PunchType(models.TextChoices):
        IN = "in", "In"
        OUT = "out", "Out"
        RAW = "raw", "Raw"

    contract = models.ForeignKey(
        "hrms.HrEmploymentContract",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="attendance_device_logs",
    )
    attendance_date = models.DateField()
    punch_time = models.DateTimeField()
    device_employee_code = models.CharField(max_length=60, blank=True, default="")
    device_identifier = models.CharField(max_length=80, blank=True, default="")
    punch_type = models.CharField(max_length=10, choices=PunchType.choices, default=PunchType.RAW)
    raw_payload = models.JSONField(default=dict, blank=True)
    processed = models.BooleanField(default=False)
    linked_daily_attendance = models.ForeignKey(
        DailyAttendance,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="device_logs",
    )

    class Meta:
        ordering = ["-punch_time", "-created_at"]
        indexes = [
            models.Index(fields=["entity", "attendance_date"], name="ix_hr_att_device_date"),
            models.Index(fields=["entity", "device_employee_code"], name="ix_hr_att_device_emp"),
        ]

    def clean(self):
        super().clean()
        if self.contract_id:
            if self.contract.entity_id != self.entity_id:
                raise ValidationError({"contract": "Contract must belong to the selected entity."})
            if self.contract.subentity_id != self.subentity_id:
                raise ValidationError({"subentity": "Device log subentity must match the contract scope."})
        self.device_employee_code = (self.device_employee_code or "").strip().upper()
        self.device_identifier = (self.device_identifier or "").strip()
