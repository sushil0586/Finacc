from datetime import date, time

from django.core.exceptions import ValidationError
from django.test import TestCase

from Authentication.models import User
from entity.models import Entity
from geography.models import Country, State
from hrms.models import HrEmployee, HrEmploymentContract, HrHoliday, HrHolidayCalendar, HrShift


class HrmsFoundationModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="hrms-owner@example.com",
            username="hrms-owner@example.com",
            password="testpass123",
        )
        self.entity = Entity.objects.create(entityname="HRMS Entity", createdby=self.user)
        self.country = Country.objects.create(countryname="India", countrycode="IN")
        self.state = State.objects.create(statename="Maharashtra", statecode="27", country=self.country)
        self.employee = HrEmployee.objects.create(
            entity=self.entity,
            employee_number="EMP-0001",
            legal_first_name="Aarav",
            legal_last_name="Sharma",
            display_name="Aarav Sharma",
            work_email="aarav@example.com",
            created_by=self.user,
            updated_by=self.user,
        )

    def test_employment_contract_rejects_overlap_for_same_employee(self):
        HrEmploymentContract.objects.create(
            entity=self.entity,
            employee=self.employee,
            contract_code="CTR-001",
            start_date=date(2026, 4, 1),
            payroll_effective_from=date(2026, 4, 1),
            created_by=self.user,
            updated_by=self.user,
        )
        overlapping = HrEmploymentContract(
            entity=self.entity,
            employee=self.employee,
            contract_code="CTR-002",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 12, 31),
            payroll_effective_from=date(2026, 6, 1),
            created_by=self.user,
            updated_by=self.user,
        )
        with self.assertRaises(ValidationError):
            overlapping.full_clean()

    def test_employment_contract_allows_only_one_active_contract_per_employee(self):
        HrEmploymentContract.objects.create(
            entity=self.entity,
            employee=self.employee,
            contract_code="CTR-010",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 6, 30),
            payroll_effective_from=date(2026, 4, 1),
            status=HrEmploymentContract.ContractStatus.ACTIVE,
            created_by=self.user,
            updated_by=self.user,
        )
        second_active = HrEmploymentContract(
            entity=self.entity,
            employee=self.employee,
            contract_code="CTR-011",
            start_date=date(2026, 7, 1),
            payroll_effective_from=date(2026, 7, 1),
            status=HrEmploymentContract.ContractStatus.ACTIVE,
            created_by=self.user,
            updated_by=self.user,
        )
        with self.assertRaises(ValidationError):
            second_active.full_clean()

    def test_employment_contract_rejects_end_date_before_start_date(self):
        contract = HrEmploymentContract(
            entity=self.entity,
            employee=self.employee,
            contract_code="CTR-020",
            start_date=date(2026, 8, 1),
            end_date=date(2026, 7, 31),
            payroll_effective_from=date(2026, 8, 1),
            created_by=self.user,
            updated_by=self.user,
        )
        with self.assertRaises(ValidationError):
            contract.full_clean()

    def test_holiday_must_match_calendar_period(self):
        calendar = HrHolidayCalendar.objects.create(
            entity=self.entity,
            code="FY2026",
            name="FY 2026 Calendar",
            calendar_year=2026,
            period_start=date(2026, 4, 1),
            period_end=date(2027, 3, 31),
            created_by=self.user,
            updated_by=self.user,
        )
        holiday = HrHoliday(
            entity=self.entity,
            holiday_calendar=calendar,
            holiday_date=date(2027, 4, 1),
            name="Outside Period Holiday",
            created_by=self.user,
            updated_by=self.user,
        )
        with self.assertRaises(ValidationError):
            holiday.full_clean()

    def test_fixed_shift_requires_start_and_end_time(self):
        shift = HrShift(
            entity=self.entity,
            code="SHIFT-A",
            name="Morning Shift",
            shift_type=HrShift.ShiftType.FIXED,
            start_time=time(9, 0),
            end_time=time(18, 0),
            created_by=self.user,
            updated_by=self.user,
        )
        shift.full_clean()

    def test_non_midnight_fixed_shift_requires_start_before_end(self):
        shift = HrShift(
            entity=self.entity,
            code="SHIFT-B",
            name="Invalid Day Shift",
            shift_type=HrShift.ShiftType.FIXED,
            start_time=time(18, 0),
            end_time=time(9, 0),
            crosses_midnight=False,
            created_by=self.user,
            updated_by=self.user,
        )
        with self.assertRaises(ValidationError):
            shift.full_clean()

    def test_holiday_calendar_must_be_unique_per_entity_year_and_location_scope(self):
        HrHolidayCalendar.objects.create(
            entity=self.entity,
            code="FY2026-MH",
            name="FY 2026 Maharashtra",
            calendar_year=2026,
            period_start=date(2026, 4, 1),
            period_end=date(2027, 3, 31),
            country=self.country,
            state=self.state,
            created_by=self.user,
            updated_by=self.user,
        )
        duplicate = HrHolidayCalendar(
            entity=self.entity,
            code="FY2026-MH-2",
            name="FY 2026 Maharashtra Duplicate",
            calendar_year=2026,
            period_start=date(2026, 4, 1),
            period_end=date(2027, 3, 31),
            country=self.country,
            state=self.state,
            created_by=self.user,
            updated_by=self.user,
        )
        with self.assertRaises(ValidationError):
            duplicate.full_clean()
