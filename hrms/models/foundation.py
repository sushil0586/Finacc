from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Q

from geography.models import Country, State
from hrms.base import EntityScopedHrmsModel

User = settings.AUTH_USER_MODEL

employee_code_validator = RegexValidator(
    regex=r"^[A-Z0-9][A-Z0-9/_-]{1,39}$",
    message="Use 2-40 uppercase letters, numbers, slash, underscore, or hyphen.",
)
pan_validator = RegexValidator(
    regex=r"^[A-Z]{5}[0-9]{4}[A-Z]$",
    message="Enter a valid PAN.",
)
uan_validator = RegexValidator(
    regex=r"^[0-9]{12}$",
    message="Enter a valid 12 digit UAN.",
)


class HrOrganizationUnit(EntityScopedHrmsModel):
    class UnitType(models.TextChoices):
        BUSINESS_UNIT = "business_unit", "Business Unit"
        DEPARTMENT = "department", "Department"
        TEAM = "team", "Team"
        DESIGNATION = "designation", "Designation"
        GRADE = "grade", "Grade"
        COST_CENTER = "cost_center", "Cost Center"
        WORK_LOCATION = "work_location", "Work Location"
        DIVISION = "division", "Division"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        ARCHIVED = "archived", "Archived"

    code = models.CharField(max_length=40, validators=[employee_code_validator])
    name = models.CharField(max_length=150)
    short_name = models.CharField(max_length=80, blank=True, default="")
    unit_type = models.CharField(max_length=30, choices=UnitType.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",
    )
    description = models.CharField(max_length=255, blank=True, default="")
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)
    sort_order = models.PositiveIntegerField(default=100)
    country = models.ForeignKey(Country, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    state = models.ForeignKey(State, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    external_ref = models.CharField(max_length=80, blank=True, default="")

    class Meta:
        ordering = ["entity_id", "unit_type", "sort_order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "unit_type", "code"],
                condition=Q(deleted_at__isnull=True, subentity__isnull=True),
                name="uq_hrms_orgunit_entity_type_code",
            ),
            models.UniqueConstraint(
                fields=["entity", "subentity", "unit_type", "code"],
                condition=Q(deleted_at__isnull=True, subentity__isnull=False),
                name="uq_hrms_orgunit_subentity_type_code",
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "unit_type", "is_active"], name="ix_hrms_orgunit_entity_type"),
            models.Index(fields=["entity", "subentity", "status"], name="ix_hrms_orgunit_scope_status"),
            models.Index(fields=["entity", "parent"], name="ix_hrms_orgunit_parent"),
        ]

    def __str__(self):
        return f"{self.entity_id}:{self.unit_type}:{self.code}"

    def clean(self):
        if self.subentity_id and self.subentity and self.subentity.entity_id != self.entity_id:
            raise ValidationError({"subentity": "Subentity must belong to the selected entity."})
        if self.parent_id and self.parent:
            if self.parent.entity_id != self.entity_id:
                raise ValidationError({"parent": "Parent must belong to the same entity."})
            if self.parent_id == self.id:
                raise ValidationError({"parent": "Org unit cannot be its own parent."})
            if self.subentity_id and self.parent.subentity_id not in (None, self.subentity_id):
                raise ValidationError({"parent": "Parent must be shared or belong to the same subentity."})
        if self.effective_from and self.effective_to and self.effective_from > self.effective_to:
            raise ValidationError({"effective_to": "Effective end date must be on or after effective start date."})
        if self.state_id and self.country_id and self.state.country_id != self.country_id:
            raise ValidationError({"state": "State must belong to the selected country."})

    def save(self, *args, **kwargs):
        self.code = (self.code or "").strip().upper()
        self.name = (self.name or "").strip()
        self.short_name = (self.short_name or "").strip()
        self.description = (self.description or "").strip()
        self.external_ref = (self.external_ref or "").strip()
        self.full_clean()
        super().save(*args, **kwargs)


class HrEmployee(EntityScopedHrmsModel):
    class LifecycleStatus(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        EXITED = "exited", "Exited"
        ARCHIVED = "archived", "Archived"

    class Gender(models.TextChoices):
        MALE = "male", "Male"
        FEMALE = "female", "Female"
        NON_BINARY = "non_binary", "Non-binary"
        UNDISCLOSED = "undisclosed", "Undisclosed"

    class MaritalStatus(models.TextChoices):
        SINGLE = "single", "Single"
        MARRIED = "married", "Married"
        DIVORCED = "divorced", "Divorced"
        WIDOWED = "widowed", "Widowed"
        UNDISCLOSED = "undisclosed", "Undisclosed"

    linked_user = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="hrms_employee_profiles",
    )
    employee_number = models.CharField(max_length=40, validators=[employee_code_validator])
    legal_first_name = models.CharField(max_length=80)
    legal_last_name = models.CharField(max_length=80, blank=True, default="")
    preferred_name = models.CharField(max_length=80, blank=True, default="")
    display_name = models.CharField(max_length=180, blank=True, default="")
    work_email = models.EmailField(blank=True, default="")
    personal_email = models.EmailField(blank=True, default="")
    mobile_number = models.CharField(max_length=20, blank=True, default="")
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=20, choices=Gender.choices, blank=True, default="")
    marital_status = models.CharField(max_length=20, choices=MaritalStatus.choices, blank=True, default="")
    nationality = models.ForeignKey(Country, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    pan = models.CharField(max_length=10, blank=True, default="", validators=[pan_validator])
    uan = models.CharField(max_length=12, blank=True, default="", validators=[uan_validator])
    lifecycle_status = models.CharField(max_length=20, choices=LifecycleStatus.choices, default=LifecycleStatus.ACTIVE, db_index=True)
    external_ref = models.CharField(max_length=80, blank=True, default="")

    class Meta:
        ordering = ["entity_id", "employee_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "employee_number"],
                condition=Q(deleted_at__isnull=True),
                name="uq_hrms_employee_entity_number",
            ),
            models.UniqueConstraint(
                fields=["entity", "work_email"],
                condition=Q(deleted_at__isnull=True) & ~Q(work_email=""),
                name="uq_hrms_employee_entity_work_email",
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "lifecycle_status", "is_active"], name="ix_hrms_emp_status"),
            models.Index(fields=["entity", "subentity", "is_active"], name="ix_hrms_emp_scope"),
            models.Index(fields=["entity", "display_name"], name="ix_hrms_emp_display"),
        ]

    def __str__(self):
        return f"{self.entity_id}:{self.employee_number}"

    def clean(self):
        if self.subentity_id and self.subentity and self.subentity.entity_id != self.entity_id:
            raise ValidationError({"subentity": "Subentity must belong to the selected entity."})

    def save(self, *args, **kwargs):
        self.employee_number = (self.employee_number or "").strip().upper()
        self.legal_first_name = (self.legal_first_name or "").strip()
        self.legal_last_name = (self.legal_last_name or "").strip()
        self.preferred_name = (self.preferred_name or "").strip()
        self.work_email = (self.work_email or "").strip().lower()
        self.personal_email = (self.personal_email or "").strip().lower()
        self.mobile_number = (self.mobile_number or "").strip()
        self.pan = (self.pan or "").strip().upper()
        self.uan = (self.uan or "").strip()
        self.external_ref = (self.external_ref or "").strip()
        if not self.display_name:
            base_name = " ".join(part for part in [self.preferred_name or self.legal_first_name, self.legal_last_name] if part)
            self.display_name = base_name.strip()
        self.full_clean()
        super().save(*args, **kwargs)


class HrEmploymentContract(EntityScopedHrmsModel):
    class ContractStatus(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        NOTICE = "notice", "Notice Period"
        TERMINATED = "terminated", "Terminated"
        EXPIRED = "expired", "Expired"
        CLOSED = "closed", "Closed"

    class ContractType(models.TextChoices):
        PERMANENT = "permanent", "Permanent"
        FIXED_TERM = "fixed_term", "Fixed Term"
        CONSULTING = "consulting", "Consulting"
        GIG = "gig", "Gig"
        INTERN = "intern", "Intern"
        APPRENTICE = "apprentice", "Apprentice"

    class WorkModel(models.TextChoices):
        ONSITE = "onsite", "Onsite"
        REMOTE = "remote", "Remote"
        HYBRID = "hybrid", "Hybrid"
        FIELD = "field", "Field"

    class CompensationBasis(models.TextChoices):
        ANNUAL = "annual", "Annual"
        MONTHLY = "monthly", "Monthly"
        HOURLY = "hourly", "Hourly"
        DAILY = "daily", "Daily"

    employee = models.ForeignKey(HrEmployee, on_delete=models.PROTECT, related_name="contracts")
    contract_code = models.CharField(max_length=40, validators=[employee_code_validator])
    status = models.CharField(max_length=20, choices=ContractStatus.choices, default=ContractStatus.DRAFT, db_index=True)
    contract_type = models.CharField(max_length=20, choices=ContractType.choices, default=ContractType.PERMANENT)
    work_model = models.CharField(max_length=20, choices=WorkModel.choices, default=WorkModel.ONSITE)
    compensation_basis = models.CharField(max_length=20, choices=CompensationBasis.choices, default=CompensationBasis.ANNUAL)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    payroll_effective_from = models.DateField()
    probation_end = models.DateField(null=True, blank=True)
    confirmation_date = models.DateField(null=True, blank=True)
    notice_period_days = models.PositiveIntegerField(default=0, validators=[MaxValueValidator(365)])
    standard_weekly_hours = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    business_unit = models.ForeignKey(
        HrOrganizationUnit,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="contracts_business_unit",
    )
    department = models.ForeignKey(
        HrOrganizationUnit,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="contracts_department",
    )
    team = models.ForeignKey(
        HrOrganizationUnit,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="contracts_team",
    )
    designation = models.ForeignKey(
        HrOrganizationUnit,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="contracts_designation",
    )
    grade = models.ForeignKey(
        HrOrganizationUnit,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="contracts_grade",
    )
    cost_center = models.ForeignKey(
        HrOrganizationUnit,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="contracts_cost_center",
    )
    work_location = models.ForeignKey(
        HrOrganizationUnit,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="contracts_work_location",
    )
    reports_to_contract = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="direct_reports",
    )
    default_shift = models.ForeignKey(
        "hrms.HrShift",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="default_for_contracts",
    )
    holiday_calendar = models.ForeignKey(
        "hrms.HrHolidayCalendar",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="contracts",
    )
    is_payroll_eligible = models.BooleanField(default=True, db_index=True)
    pay_group_code = models.CharField(max_length=40, blank=True, default="")
    vendor_reference = models.CharField(max_length=80, blank=True, default="")

    class Meta:
        ordering = ["entity_id", "employee_id", "-start_date", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "contract_code"],
                condition=Q(deleted_at__isnull=True),
                name="uq_hrms_contract_entity_code",
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "employee", "status"], name="ix_hrms_contract_employee"),
            models.Index(fields=["entity", "subentity", "is_payroll_eligible"], name="ix_hrms_contract_payroll"),
            models.Index(fields=["entity", "start_date", "end_date"], name="ix_hrms_contract_dates"),
        ]

    def __str__(self):
        return f"{self.entity_id}:{self.contract_code}"

    def _validate_org_unit(self, unit, *, expected_type: str, field_name: str):
        if unit is None:
            return
        if unit.entity_id != self.entity_id:
            raise ValidationError({field_name: "Org unit must belong to the selected entity."})
        if unit.unit_type != expected_type:
            raise ValidationError({field_name: f"Org unit must be of type '{expected_type}'."})
        if self.subentity_id and unit.subentity_id not in (None, self.subentity_id):
            raise ValidationError({field_name: "Org unit must be shared or belong to the selected subentity."})

    def clean(self):
        if self.employee.entity_id != self.entity_id:
            raise ValidationError({"employee": "Employee must belong to the selected entity."})
        if self.subentity_id and self.subentity and self.subentity.entity_id != self.entity_id:
            raise ValidationError({"subentity": "Subentity must belong to the selected entity."})
        if self.employee.subentity_id and self.subentity_id and self.employee.subentity_id != self.subentity_id:
            raise ValidationError({"subentity": "Employee and contract subentity must match when employee is branch-scoped."})
        if self.end_date and self.start_date > self.end_date:
            raise ValidationError({"end_date": "End date must be on or after start date."})
        if self.payroll_effective_from < self.start_date:
            raise ValidationError({"payroll_effective_from": "Payroll effective date cannot be before contract start date."})
        if self.probation_end and self.probation_end < self.start_date:
            raise ValidationError({"probation_end": "Probation end cannot be before contract start date."})
        if self.confirmation_date and self.probation_end and self.confirmation_date < self.probation_end:
            raise ValidationError({"confirmation_date": "Confirmation date cannot be before probation end date."})
        if self.reports_to_contract_id:
            if self.reports_to_contract_id == self.id:
                raise ValidationError({"reports_to_contract": "Contract cannot report to itself."})
            if self.reports_to_contract.entity_id != self.entity_id:
                raise ValidationError({"reports_to_contract": "Reporting contract must belong to the same entity."})
            if self.reports_to_contract.employee_id == self.employee_id:
                raise ValidationError({"reports_to_contract": "Employee cannot report to another contract of the same employee."})
        if self.default_shift_id:
            if self.default_shift.entity_id != self.entity_id:
                raise ValidationError({"default_shift": "Shift must belong to the same entity."})
            if self.subentity_id and self.default_shift.subentity_id not in (None, self.subentity_id):
                raise ValidationError({"default_shift": "Shift must be shared or belong to the same subentity."})
        if self.holiday_calendar_id:
            if self.holiday_calendar.entity_id != self.entity_id:
                raise ValidationError({"holiday_calendar": "Holiday calendar must belong to the same entity."})
            if self.subentity_id and self.holiday_calendar.subentity_id not in (None, self.subentity_id):
                raise ValidationError({"holiday_calendar": "Holiday calendar must be shared or belong to the same subentity."})

        self._validate_org_unit(self.business_unit, expected_type=HrOrganizationUnit.UnitType.BUSINESS_UNIT, field_name="business_unit")
        self._validate_org_unit(self.department, expected_type=HrOrganizationUnit.UnitType.DEPARTMENT, field_name="department")
        self._validate_org_unit(self.team, expected_type=HrOrganizationUnit.UnitType.TEAM, field_name="team")
        self._validate_org_unit(self.designation, expected_type=HrOrganizationUnit.UnitType.DESIGNATION, field_name="designation")
        self._validate_org_unit(self.grade, expected_type=HrOrganizationUnit.UnitType.GRADE, field_name="grade")
        self._validate_org_unit(self.cost_center, expected_type=HrOrganizationUnit.UnitType.COST_CENTER, field_name="cost_center")
        self._validate_org_unit(self.work_location, expected_type=HrOrganizationUnit.UnitType.WORK_LOCATION, field_name="work_location")

        overlapping = HrEmploymentContract.all_objects.filter(
            entity_id=self.entity_id,
            employee_id=self.employee_id,
            deleted_at__isnull=True,
        ).exclude(pk=self.pk)
        active_like_statuses = {
            self.ContractStatus.DRAFT,
            self.ContractStatus.ACTIVE,
            self.ContractStatus.SUSPENDED,
            self.ContractStatus.NOTICE,
        }
        if self.status in active_like_statuses:
            active_contract = overlapping.filter(status__in=active_like_statuses).first()
            if active_contract:
                raise ValidationError({"status": "Only one active employment contract is allowed per employee."})
        for candidate in overlapping:
            candidate_end = candidate.end_date
            current_end = self.end_date
            overlap = (
                candidate.start_date <= (current_end or candidate.start_date)
                and self.start_date <= (candidate_end or self.start_date)
            ) if candidate_end and current_end else (
                (candidate_end is None or self.start_date <= candidate_end)
                and (current_end is None or candidate.start_date <= current_end)
            )
            if overlap and candidate.status not in {self.ContractStatus.CLOSED, self.ContractStatus.TERMINATED, self.ContractStatus.EXPIRED}:
                raise ValidationError({"start_date": "Contract dates overlap with an existing employment contract for this employee."})

    def save(self, *args, **kwargs):
        self.contract_code = (self.contract_code or "").strip().upper()
        self.status = (self.status or self.ContractStatus.DRAFT).strip().lower()
        self.contract_type = (self.contract_type or self.ContractType.PERMANENT).strip().lower()
        self.work_model = (self.work_model or self.WorkModel.ONSITE).strip().lower()
        self.compensation_basis = (self.compensation_basis or self.CompensationBasis.ANNUAL).strip().lower()
        self.pay_group_code = (self.pay_group_code or "").strip().upper()
        self.vendor_reference = (self.vendor_reference or "").strip()
        self.full_clean()
        super().save(*args, **kwargs)
