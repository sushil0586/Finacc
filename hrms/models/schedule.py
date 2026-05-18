from __future__ import annotations

from datetime import date

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Q

from geography.models import Country, State
from hrms.base import EntityScopedHrmsModel

code_validator = RegexValidator(
    regex=r"^[A-Z0-9][A-Z0-9/_-]{1,39}$",
    message="Use 2-40 uppercase letters, numbers, slash, underscore, or hyphen.",
)


class HrShift(EntityScopedHrmsModel):
    class ShiftType(models.TextChoices):
        FIXED = "fixed", "Fixed"
        FLEXIBLE = "flexible", "Flexible"
        ROTATIONAL = "rotational", "Rotational"
        OPEN = "open", "Open"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        ARCHIVED = "archived", "Archived"

    code = models.CharField(max_length=40, validators=[code_validator])
    name = models.CharField(max_length=120)
    shift_type = models.CharField(max_length=20, choices=ShiftType.choices, default=ShiftType.FIXED)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    timezone = models.CharField(max_length=50, default="Asia/Kolkata")
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    crosses_midnight = models.BooleanField(default=False)
    break_minutes = models.PositiveIntegerField(default=0, validators=[MaxValueValidator(1440)])
    grace_in_minutes = models.PositiveIntegerField(default=0, validators=[MaxValueValidator(240)])
    grace_out_minutes = models.PositiveIntegerField(default=0, validators=[MaxValueValidator(240)])
    minimum_half_day_minutes = models.PositiveIntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(1440)])
    minimum_full_day_minutes = models.PositiveIntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(1440)])
    weekly_off_pattern = models.JSONField(default=list, blank=True)
    description = models.CharField(max_length=255, blank=True, default="")
    source_global_shift_template = models.ForeignKey(
        "hrms.GlobalShiftTemplate",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="adopted_shifts",
    )

    class Meta:
        ordering = ["entity_id", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "code"],
                condition=Q(deleted_at__isnull=True),
                name="uq_hrms_shift_entity_code",
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "subentity", "status"], name="ix_hrms_shift_scope_status"),
            models.Index(fields=["entity", "shift_type", "is_active"], name="ix_hrms_shift_type"),
        ]

    def clean(self):
        if self.subentity_id and self.subentity and self.subentity.entity_id != self.entity_id:
            raise ValidationError({"subentity": "Subentity must belong to the selected entity."})
        if self.shift_type != self.ShiftType.OPEN and (self.start_time is None or self.end_time is None):
            raise ValidationError({"start_time": "Start and end time are required for non-open shifts."})
        if self.start_time and self.end_time and self.shift_type != self.ShiftType.OPEN:
            if not self.crosses_midnight and self.start_time >= self.end_time:
                raise ValidationError({"end_time": "End time must be after start time unless the shift crosses midnight."})
            if self.crosses_midnight and self.start_time == self.end_time:
                raise ValidationError({"end_time": "End time cannot match start time for a shift that crosses midnight."})
        if self.minimum_half_day_minutes and self.minimum_full_day_minutes and self.minimum_half_day_minutes > self.minimum_full_day_minutes:
            raise ValidationError({"minimum_half_day_minutes": "Half day minutes cannot exceed full day minutes."})

    def save(self, *args, **kwargs):
        self.code = (self.code or "").strip().upper()
        self.name = (self.name or "").strip()
        self.description = (self.description or "").strip()
        self.full_clean()
        super().save(*args, **kwargs)


class HrHolidayCalendar(EntityScopedHrmsModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        ARCHIVED = "archived", "Archived"

    code = models.CharField(max_length=40, validators=[code_validator])
    name = models.CharField(max_length=150)
    calendar_year = models.PositiveIntegerField(validators=[MinValueValidator(2000), MaxValueValidator(2100)])
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    country = models.ForeignKey(Country, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    state = models.ForeignKey(State, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    is_default = models.BooleanField(default=False)
    description = models.CharField(max_length=255, blank=True, default="")
    source_global_holiday_calendar_template = models.ForeignKey(
        "hrms.GlobalHolidayCalendarTemplate",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="adopted_holiday_calendars",
    )

    class Meta:
        ordering = ["entity_id", "-calendar_year", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "calendar_year", "code"],
                condition=Q(deleted_at__isnull=True),
                name="uq_hrms_holiday_calendar_code",
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "calendar_year", "status"], name="ix_hrms_cal_year_status"),
            models.Index(fields=["entity", "subentity", "is_default"], name="ix_hrms_cal_default"),
        ]

    def clean(self):
        if self.calendar_year:
            self.period_start = self.period_start or date(int(self.calendar_year), 1, 1)
            self.period_end = self.period_end or date(int(self.calendar_year), 12, 31)
        if self.subentity_id and self.subentity and self.subentity.entity_id != self.entity_id:
            raise ValidationError({"subentity": "Subentity must belong to the selected entity."})
        if self.state_id and self.country_id and self.state.country_id != self.country_id:
            raise ValidationError({"state": "State must belong to the selected country."})
        if self.period_end and self.period_start and self.period_end < self.period_start:
            raise ValidationError({"period_end": "Period end must be on or after period start."})
        overlapping = HrHolidayCalendar.all_objects.filter(
            entity_id=self.entity_id,
            calendar_year=self.calendar_year,
            deleted_at__isnull=True,
            country_id=self.country_id,
            state_id=self.state_id,
            subentity_id=self.subentity_id,
        ).exclude(pk=self.pk)
        if overlapping.exists():
            raise ValidationError({"calendar_year": "A holiday calendar already exists for this entity, year, and location scope."})

    def save(self, *args, **kwargs):
        self.code = (self.code or "").strip().upper()
        self.name = (self.name or "").strip()
        self.description = (self.description or "").strip()
        self.full_clean()
        super().save(*args, **kwargs)


class HrHoliday(EntityScopedHrmsModel):
    class HolidayType(models.TextChoices):
        PUBLIC = "public", "Public Holiday"
        OPTIONAL = "optional", "Optional Holiday"
        COMPANY = "company", "Company Holiday"
        REGIONAL = "regional", "Regional Holiday"

    holiday_calendar = models.ForeignKey(HrHolidayCalendar, on_delete=models.CASCADE, related_name="holidays")
    holiday_date = models.DateField()
    name = models.CharField(max_length=150)
    holiday_type = models.CharField(max_length=20, choices=HolidayType.choices, default=HolidayType.PUBLIC)
    is_paid = models.BooleanField(default=True)
    is_optional = models.BooleanField(default=False)
    description = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["holiday_date", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["holiday_calendar", "holiday_date", "name"],
                condition=Q(deleted_at__isnull=True),
                name="uq_hrms_holiday_calendar_date_name",
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "holiday_date"], name="ix_hrms_holiday_date"),
            models.Index(fields=["holiday_calendar", "holiday_type"], name="ix_hrms_holiday_type"),
        ]

    def clean(self):
        if self.holiday_calendar.entity_id != self.entity_id:
            raise ValidationError({"holiday_calendar": "Holiday calendar must belong to the selected entity."})
        if self.subentity_id and self.holiday_calendar.subentity_id not in (None, self.subentity_id):
            raise ValidationError({"holiday_calendar": "Holiday calendar must be shared or belong to the same subentity."})
        period_start = getattr(self.holiday_calendar, "period_start", None)
        period_end = getattr(self.holiday_calendar, "period_end", None)
        if period_start and period_end and not (period_start <= self.holiday_date <= period_end):
            raise ValidationError({"holiday_date": "Holiday date must fall within the selected calendar period."})

    def save(self, *args, **kwargs):
        self.name = (self.name or "").strip()
        self.description = (self.description or "").strip()
        self.full_clean()
        super().save(*args, **kwargs)
