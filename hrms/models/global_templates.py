from __future__ import annotations

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from hrms.base import HrmsBaseModel

template_code_validator = RegexValidator(
    regex=r"^[A-Z0-9][A-Z0-9/_-]{1,59}$",
    message="Use 2-60 uppercase letters, numbers, slash, underscore, or hyphen.",
)


class GlobalTemplateBase(HrmsBaseModel):
    class EmployeeCategory(models.TextChoices):
        SME_OFFICE = "sme_office", "SME Office"
        FACTORY = "factory", "Factory / Manufacturing"
        RETAIL = "retail", "Retail / Shop"
        SERVICES = "services", "Services Company"
        CONTRACTOR = "contractor", "Contractor Workforce"
        SCHOOL = "school", "School / Institute"
        CUSTOM = "custom", "Custom Setup"

    code = models.CharField(max_length=60, validators=[template_code_validator], unique=True)
    name = models.CharField(max_length=160)
    description = models.CharField(max_length=255, blank=True, default="")
    industry_type = models.CharField(max_length=60, blank=True, default="")
    employee_category = models.CharField(max_length=30, choices=EmployeeCategory.choices, default=EmployeeCategory.CUSTOM)
    country_code = models.CharField(max_length=2, default="IN")
    state_code = models.CharField(max_length=10, blank=True, default="")
    effective_from = models.DateField(default=timezone.localdate)
    effective_to = models.DateField(null=True, blank=True)
    is_system = models.BooleanField(default=True)
    is_recommended = models.BooleanField(default=True)

    class Meta:
        abstract = True
        ordering = ["employee_category", "code"]

    def clean(self):
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError({"effective_to": "Effective end date must be on or after effective start date."})

    def save(self, *args, **kwargs):
        self.code = (self.code or "").strip().upper()
        self.name = (self.name or "").strip()
        self.description = (self.description or "").strip()
        self.industry_type = (self.industry_type or "").strip().lower()
        self.country_code = (self.country_code or "").strip().upper()
        self.state_code = (self.state_code or "").strip().upper()
        self.full_clean()
        return super().save(*args, **kwargs)


class GlobalLeaveType(GlobalTemplateBase):
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

    category = models.CharField(max_length=30, choices=Category.choices, default=Category.OTHER)
    color_hex = models.CharField(max_length=7, blank=True, default="")
    is_paid = models.BooleanField(default=True)
    requires_balance = models.BooleanField(default=True)
    allow_negative_balance = models.BooleanField(default=False)
    counts_towards_attendance = models.BooleanField(default=True)
    payroll_impact_code = models.CharField(max_length=40, blank=True, default="")


class GlobalLeavePolicyTemplate(GlobalTemplateBase):
    policy_json = models.JSONField(default=dict, blank=True)


class GlobalLeavePolicyRuleTemplate(HrmsBaseModel):
    template = models.ForeignKey(GlobalLeavePolicyTemplate, on_delete=models.CASCADE, related_name="rules")
    leave_type = models.ForeignKey(GlobalLeaveType, on_delete=models.PROTECT, null=True, blank=True, related_name="policy_rule_templates")
    rule_code = models.CharField(max_length=60, validators=[template_code_validator])
    rule_name = models.CharField(max_length=150)
    sequence = models.PositiveIntegerField(default=100)
    rule_json = models.JSONField(default=dict, blank=True)
    effective_from = models.DateField(default=timezone.localdate)
    effective_to = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["template_id", "sequence", "rule_code"]
        constraints = [
            models.UniqueConstraint(
                fields=["template", "rule_code"],
                condition=Q(deleted_at__isnull=True),
                name="uq_glb_leave_policy_rule_template_code",
            ),
        ]

    def clean(self):
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError({"effective_to": "Effective end date must be on or after effective start date."})

    def save(self, *args, **kwargs):
        self.rule_code = (self.rule_code or "").strip().upper()
        self.rule_name = (self.rule_name or "").strip()
        self.full_clean()
        return super().save(*args, **kwargs)


class GlobalShiftTemplate(GlobalTemplateBase):
    shift_type = models.CharField(max_length=20, default="fixed")
    timezone = models.CharField(max_length=50, default="Asia/Kolkata")
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    crosses_midnight = models.BooleanField(default=False)
    break_minutes = models.PositiveIntegerField(default=0)
    grace_in_minutes = models.PositiveIntegerField(default=0)
    grace_out_minutes = models.PositiveIntegerField(default=0)
    minimum_half_day_minutes = models.PositiveIntegerField(null=True, blank=True)
    minimum_full_day_minutes = models.PositiveIntegerField(null=True, blank=True)
    weekly_off_pattern = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, default="active")


class GlobalHolidayCalendarTemplate(GlobalTemplateBase):
    template_year = models.PositiveIntegerField(default=timezone.localdate().year)
    holiday_json = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, default="active")


class GlobalAttendancePolicyTemplate(GlobalTemplateBase):
    policy_json = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, default="active")


class GlobalHRPolicyTemplate(GlobalTemplateBase):
    policy_area = models.CharField(max_length=30, default="general")
    policy_json = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, default="active")
