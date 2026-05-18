from __future__ import annotations

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from hrms.base import EntityScopedHrmsModel

code_validator = RegexValidator(
    regex=r"^[A-Z0-9][A-Z0-9/_-]{1,59}$",
    message="Use 2-60 uppercase letters, numbers, slash, underscore, or hyphen.",
)


class LeaveType(EntityScopedHrmsModel):
    class Category(models.TextChoices):
        CASUAL = "casual", "Casual Leave"
        SICK = "sick", "Sick Leave"
        EARNED = "earned", "Earned Leave"
        LOP = "lop", "Leave Without Pay"
        MATERNITY = "maternity", "Maternity Leave"
        PATERNITY = "paternity", "Paternity Leave"
        COMP_OFF = "comp_off", "Comp Off"
        OPTIONAL_HOLIDAY = "optional_holiday", "Optional Holiday"
        OTHER = "other", "Other"

    code = models.CharField(max_length=60, validators=[code_validator])
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=30, choices=Category.choices, default=Category.OTHER)
    description = models.CharField(max_length=255, blank=True, default="")
    color_hex = models.CharField(max_length=7, blank=True, default="")
    is_paid = models.BooleanField(default=True)
    requires_balance = models.BooleanField(default=True)
    allow_negative_balance = models.BooleanField(default=False)
    counts_towards_attendance = models.BooleanField(default=True)
    payroll_impact_code = models.CharField(max_length=40, blank=True, default="")
    is_system = models.BooleanField(default=False)
    effective_from = models.DateField(default=timezone.localdate)
    effective_to = models.DateField(null=True, blank=True)
    source_global_leave_type = models.ForeignKey(
        "hrms.GlobalLeaveType",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="adopted_leave_types",
    )

    class Meta:
        ordering = ["entity_id", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "code"],
                condition=Q(deleted_at__isnull=True),
                name="uq_hrms_leave_type_entity_code",
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "category", "is_active"], name="ix_hrms_leave_type_category"),
        ]

    def clean(self):
        if self.subentity_id and self.subentity and self.subentity.entity_id != self.entity_id:
            raise ValidationError({"subentity": "Subentity must belong to the selected entity."})
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError({"effective_to": "Effective end date must be on or after effective start date."})

    def save(self, *args, **kwargs):
        self.code = (self.code or "").strip().upper()
        self.name = (self.name or "").strip()
        self.description = (self.description or "").strip()
        self.color_hex = (self.color_hex or "").strip().upper()
        self.payroll_impact_code = (self.payroll_impact_code or "").strip().upper()
        self.full_clean()
        return super().save(*args, **kwargs)


class LeavePolicy(EntityScopedHrmsModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        ARCHIVED = "archived", "Archived"

    class EmployeeCategory(models.TextChoices):
        SME_OFFICE = "sme_office", "SME Office"
        FACTORY = "factory", "Factory / Manufacturing"
        RETAIL = "retail", "Retail / Shop"
        SERVICES = "services", "Services Company"
        CONTRACTOR = "contractor", "Contractor Workforce"
        SCHOOL = "school", "School / Institute"
        CUSTOM = "custom", "Custom Setup"

    class LeaveYearType(models.TextChoices):
        CALENDAR_YEAR = "calendar_year", "Calendar Year"
        FINANCIAL_YEAR = "financial_year", "Financial Year"
        CUSTOM_RANGE = "custom_range", "Custom Range"

    code = models.CharField(max_length=60, validators=[code_validator])
    name = models.CharField(max_length=150)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    employee_category = models.CharField(max_length=30, choices=EmployeeCategory.choices, default=EmployeeCategory.CUSTOM)
    description = models.CharField(max_length=255, blank=True, default="")
    policy_json = models.JSONField(default=dict, blank=True)
    leave_year_type = models.CharField(max_length=30, choices=LeaveYearType.choices, default=LeaveYearType.FINANCIAL_YEAR)
    year_start_month = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(12)])
    year_start_day = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(31)])
    year_end_month = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(12)])
    year_end_day = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(31)])
    effective_from = models.DateField(default=timezone.localdate)
    effective_to = models.DateField(null=True, blank=True)
    is_default = models.BooleanField(default=False)
    source_global_leave_policy_template = models.ForeignKey(
        "hrms.GlobalLeavePolicyTemplate",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="adopted_leave_policies",
    )

    class Meta:
        ordering = ["entity_id", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "code"],
                condition=Q(deleted_at__isnull=True),
                name="uq_hrms_leave_policy_entity_code",
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "employee_category", "is_active"], name="ix_hrms_leave_policy_category"),
        ]

    def clean(self):
        if self.subentity_id and self.subentity and self.subentity.entity_id != self.entity_id:
            raise ValidationError({"subentity": "Subentity must belong to the selected entity."})
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError({"effective_to": "Effective end date must be on or after effective start date."})
        if self.leave_year_type == self.LeaveYearType.CUSTOM_RANGE:
            missing = {}
            for field in ("year_start_month", "year_start_day", "year_end_month", "year_end_day"):
                if getattr(self, field) in (None, ""):
                    missing[field] = "This field is required for a custom leave year."
            if missing:
                raise ValidationError(missing)
        try:
            self._validate_leave_year_day(month=self.year_start_month, day=self.year_start_day, field_prefix="year_start")
            self._validate_leave_year_day(month=self.year_end_month, day=self.year_end_day, field_prefix="year_end")
        except ValidationError:
            raise

    def save(self, *args, **kwargs):
        self.code = (self.code or "").strip().upper()
        self.name = (self.name or "").strip()
        self.description = (self.description or "").strip()
        self.full_clean()
        return super().save(*args, **kwargs)

    @staticmethod
    def _validate_leave_year_day(*, month, day, field_prefix: str):
        if month in (None, "") and day in (None, ""):
            return
        if month in (None, "") or day in (None, ""):
            raise ValidationError({
                f"{field_prefix}_month": "Month and day must both be provided.",
                f"{field_prefix}_day": "Month and day must both be provided.",
            })
        max_day_map = {
            1: 31,
            2: 28,
            3: 31,
            4: 30,
            5: 31,
            6: 30,
            7: 31,
            8: 31,
            9: 30,
            10: 31,
            11: 30,
            12: 31,
        }
        max_day = max_day_map.get(int(month))
        if max_day is None or int(day) > max_day:
            raise ValidationError({f"{field_prefix}_day": "Day is not valid for the selected month."})


class LeavePolicyRule(EntityScopedHrmsModel):
    leave_policy = models.ForeignKey(LeavePolicy, on_delete=models.CASCADE, related_name="rules")
    leave_type = models.ForeignKey(LeaveType, on_delete=models.PROTECT, null=True, blank=True, related_name="policy_rules")
    rule_code = models.CharField(max_length=60, validators=[code_validator])
    rule_name = models.CharField(max_length=150)
    sequence = models.PositiveIntegerField(default=100)
    rule_json = models.JSONField(default=dict, blank=True)
    effective_from = models.DateField(default=timezone.localdate)
    effective_to = models.DateField(null=True, blank=True)
    source_global_leave_policy_rule_template = models.ForeignKey(
        "hrms.GlobalLeavePolicyRuleTemplate",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="adopted_leave_policy_rules",
    )

    class Meta:
        ordering = ["leave_policy_id", "sequence", "rule_code"]
        constraints = [
            models.UniqueConstraint(
                fields=["leave_policy", "rule_code"],
                condition=Q(deleted_at__isnull=True),
                name="uq_hrms_leave_policy_rule_code",
            ),
        ]
        indexes = [
            models.Index(fields=["leave_policy", "leave_type", "is_active"], name="ix_hrms_leave_rule_leave_type"),
        ]

    def clean(self):
        if self.leave_policy.entity_id != self.entity_id:
            raise ValidationError({"leave_policy": "Leave policy must belong to the selected entity."})
        if self.leave_type_id and self.leave_type.entity_id != self.entity_id:
            raise ValidationError({"leave_type": "Leave type must belong to the selected entity."})
        if self.leave_type_id and self.leave_policy.subentity_id and self.leave_type.subentity_id not in (None, self.leave_policy.subentity_id):
            raise ValidationError({"leave_type": "Leave type must be shared or belong to the same subentity."})
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError({"effective_to": "Effective end date must be on or after effective start date."})

    def save(self, *args, **kwargs):
        self.rule_code = (self.rule_code or "").strip().upper()
        self.rule_name = (self.rule_name or "").strip()
        self.full_clean()
        return super().save(*args, **kwargs)


class AttendancePolicy(EntityScopedHrmsModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        ARCHIVED = "archived", "Archived"

    code = models.CharField(max_length=60, validators=[code_validator])
    name = models.CharField(max_length=150)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    description = models.CharField(max_length=255, blank=True, default="")
    policy_json = models.JSONField(default=dict, blank=True)
    effective_from = models.DateField(default=timezone.localdate)
    effective_to = models.DateField(null=True, blank=True)
    is_default = models.BooleanField(default=False)
    source_global_attendance_policy_template = models.ForeignKey(
        "hrms.GlobalAttendancePolicyTemplate",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="adopted_attendance_policies",
    )

    class Meta:
        ordering = ["entity_id", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "code"],
                condition=Q(deleted_at__isnull=True),
                name="uq_hrms_attendance_policy_entity_code",
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "is_default", "is_active"], name="ix_hr_att_pol_default"),
        ]

    def clean(self):
        if self.subentity_id and self.subentity and self.subentity.entity_id != self.entity_id:
            raise ValidationError({"subentity": "Subentity must belong to the selected entity."})
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError({"effective_to": "Effective end date must be on or after effective start date."})

    def save(self, *args, **kwargs):
        self.code = (self.code or "").strip().upper()
        self.name = (self.name or "").strip()
        self.description = (self.description or "").strip()
        self.full_clean()
        return super().save(*args, **kwargs)


class HRPolicy(EntityScopedHrmsModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        ARCHIVED = "archived", "Archived"

    class PolicyArea(models.TextChoices):
        GENERAL = "general", "General"
        PROBATION = "probation", "Probation"
        CONDUCT = "conduct", "Conduct"
        REMOTE_WORK = "remote_work", "Remote Work"
        NOTICE = "notice", "Notice / Separation"
        LEAVE = "leave", "Leave"
        ATTENDANCE = "attendance", "Attendance"
        OTHER = "other", "Other"

    code = models.CharField(max_length=60, validators=[code_validator])
    name = models.CharField(max_length=150)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    policy_area = models.CharField(max_length=30, choices=PolicyArea.choices, default=PolicyArea.OTHER)
    description = models.CharField(max_length=255, blank=True, default="")
    policy_json = models.JSONField(default=dict, blank=True)
    effective_from = models.DateField(default=timezone.localdate)
    effective_to = models.DateField(null=True, blank=True)
    source_global_hr_policy_template = models.ForeignKey(
        "hrms.GlobalHRPolicyTemplate",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="adopted_hr_policies",
    )

    class Meta:
        ordering = ["entity_id", "policy_area", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "code"],
                condition=Q(deleted_at__isnull=True),
                name="uq_hrms_hr_policy_entity_code",
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "policy_area", "is_active"], name="ix_hrms_hr_policy_area"),
        ]

    def clean(self):
        if self.subentity_id and self.subentity and self.subentity.entity_id != self.entity_id:
            raise ValidationError({"subentity": "Subentity must belong to the selected entity."})
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError({"effective_to": "Effective end date must be on or after effective start date."})

    def save(self, *args, **kwargs):
        self.code = (self.code or "").strip().upper()
        self.name = (self.name or "").strip()
        self.description = (self.description or "").strip()
        self.full_clean()
        return super().save(*args, **kwargs)
