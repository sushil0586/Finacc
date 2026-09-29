from datetime import date

from django.test import TestCase

from Authentication.models import User
from entity.models import Entity
from hrms.models import HrEmployee, HrEmploymentContract, HrHolidayCalendar, HrOrganizationUnit, HrShift
from hrms.services import EmployeeService, EmploymentContractService, HolidayCalendarService, OrganizationUnitService, ShiftService


class HrmsServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="hrms-services@example.com",
            username="hrms-services@example.com",
            password="testpass123",
        )
        self.entity = Entity.objects.create(entityname="HRMS Service Entity", createdby=self.user)
        self.department = HrOrganizationUnit.objects.create(
            entity=self.entity,
            code="DEPT-OPS",
            name="Operations",
            unit_type=HrOrganizationUnit.UnitType.DEPARTMENT,
            status=HrOrganizationUnit.Status.ACTIVE,
            created_by=self.user,
            updated_by=self.user,
        )
        self.employee = HrEmployee.objects.create(
            entity=self.entity,
            employee_number="EMP-1001",
            legal_first_name="Riya",
            legal_last_name="Shah",
            display_name="Riya Shah",
            work_email="riya@example.com",
            lifecycle_status=HrEmployee.LifecycleStatus.ACTIVE,
            created_by=self.user,
            updated_by=self.user,
        )
        self.inactive_employee = HrEmployee.objects.create(
            entity=self.entity,
            employee_number="EMP-1002",
            legal_first_name="Kabir",
            legal_last_name="Sen",
            display_name="Kabir Sen",
            work_email="kabir@example.com",
            lifecycle_status=HrEmployee.LifecycleStatus.INACTIVE,
            is_active=False,
            created_by=self.user,
            updated_by=self.user,
        )
        HrEmploymentContract.objects.create(
            entity=self.entity,
            employee=self.employee,
            contract_code="CTR-1001",
            start_date=date(2026, 4, 1),
            payroll_effective_from=date(2026, 4, 1),
            status=HrEmploymentContract.ContractStatus.ACTIVE,
            created_by=self.user,
            updated_by=self.user,
        )

    def test_employee_service_supports_search_and_status(self):
        rows = EmployeeService.list_employees(
            entity_id=self.entity.id,
            search="riya",
            status=HrEmployee.LifecycleStatus.ACTIVE,
            active_only=True,
        )
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.first().employee_number, "EMP-1001")

    def test_employee_service_excludes_deleted_when_including_inactive(self):
        deleted = HrEmployee.objects.create(
            entity=self.entity,
            employee_number="EMP-DEL",
            legal_first_name="Deleted",
            legal_last_name="Employee",
            display_name="Deleted Employee",
            work_email="deleted.employee@example.com",
            lifecycle_status=HrEmployee.LifecycleStatus.INACTIVE,
            created_by=self.user,
            updated_by=self.user,
        )
        deleted.soft_delete(user=self.user)

        rows = EmployeeService.list_employees(
            entity_id=self.entity.id,
            search="Deleted",
            active_only=False,
        )

        self.assertNotIn(deleted.id, set(rows.values_list("id", flat=True)))

    def test_organization_unit_service_filters_status(self):
        archived = HrOrganizationUnit.objects.create(
            entity=self.entity,
            code="DEPT-OLD",
            name="Archived Ops",
            unit_type=HrOrganizationUnit.UnitType.DEPARTMENT,
            status=HrOrganizationUnit.Status.ARCHIVED,
            created_by=self.user,
            updated_by=self.user,
        )
        rows = OrganizationUnitService.list_units(
            entity_id=self.entity.id,
            status=HrOrganizationUnit.Status.ARCHIVED,
            active_only=False,
        )
        self.assertEqual(list(rows.values_list("id", flat=True)), [archived.id])

    def test_organization_unit_service_excludes_deleted_when_including_inactive(self):
        deleted = HrOrganizationUnit.objects.create(
            entity=self.entity,
            code="DEPT-DEL",
            name="Deleted Ops",
            unit_type=HrOrganizationUnit.UnitType.DEPARTMENT,
            status=HrOrganizationUnit.Status.INACTIVE,
            created_by=self.user,
            updated_by=self.user,
        )
        deleted.soft_delete(user=self.user)

        rows = OrganizationUnitService.list_units(
            entity_id=self.entity.id,
            search="Ops",
            active_only=False,
        )

        self.assertNotIn(deleted.id, set(rows.values_list("id", flat=True)))

    def test_contract_service_supports_payroll_filter(self):
        HrEmploymentContract.objects.create(
            entity=self.entity,
            employee=self.inactive_employee,
            contract_code="CTR-1002",
            start_date=date(2025, 1, 1),
            end_date=date(2026, 3, 31),
            payroll_effective_from=date(2025, 1, 1),
            status=HrEmploymentContract.ContractStatus.CLOSED,
            is_payroll_eligible=False,
            created_by=self.user,
            updated_by=self.user,
        )
        rows = EmploymentContractService.list_contracts(
            entity_id=self.entity.id,
            payroll_eligible=False,
            active_only=False,
        )
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.first().contract_code, "CTR-1002")

    def test_contract_service_excludes_deleted_when_including_inactive(self):
        contract_employee = HrEmployee.objects.create(
            entity=self.entity,
            employee_number="EMP-CTR-DEL",
            legal_first_name="Contract",
            legal_last_name="Deleted",
            display_name="Contract Deleted",
            work_email="contract.deleted@example.com",
            lifecycle_status=HrEmployee.LifecycleStatus.ACTIVE,
            created_by=self.user,
            updated_by=self.user,
        )
        deleted = HrEmploymentContract.objects.create(
            entity=self.entity,
            employee=contract_employee,
            contract_code="CTR-DEL",
            start_date=date(2026, 5, 1),
            end_date=date(2026, 5, 31),
            payroll_effective_from=date(2026, 5, 1),
            status=HrEmploymentContract.ContractStatus.CLOSED,
            is_payroll_eligible=False,
            created_by=self.user,
            updated_by=self.user,
        )
        deleted.soft_delete(user=self.user)

        rows = EmploymentContractService.list_contracts(
            entity_id=self.entity.id,
            search="CTR-DEL",
            active_only=False,
        )

        self.assertNotIn(deleted.id, set(rows.values_list("id", flat=True)))

    def test_shift_service_excludes_deleted_when_including_inactive(self):
        deleted = HrShift.objects.create(
            entity=self.entity,
            code="SHIFT-DEL",
            name="Deleted Shift",
            shift_type=HrShift.ShiftType.FIXED,
            status=HrShift.Status.INACTIVE,
            start_time="09:00",
            end_time="18:00",
            created_by=self.user,
            updated_by=self.user,
        )
        deleted.soft_delete(user=self.user)

        rows = ShiftService.list_shifts(
            entity_id=self.entity.id,
            search="Deleted",
            active_only=False,
        )

        self.assertNotIn(deleted.id, set(rows.values_list("id", flat=True)))

    def test_holiday_calendar_service_excludes_deleted_when_including_inactive(self):
        deleted = HrHolidayCalendar.objects.create(
            entity=self.entity,
            code="CAL-DEL",
            name="Deleted Calendar",
            calendar_year=2030,
            period_start=date(2030, 1, 1),
            period_end=date(2030, 12, 31),
            status=HrHolidayCalendar.Status.ACTIVE,
            created_by=self.user,
            updated_by=self.user,
        )
        deleted.soft_delete(user=self.user)

        rows = HolidayCalendarService.list_calendars(
            entity_id=self.entity.id,
            search="Deleted",
            active_only=False,
        )

        self.assertNotIn(deleted.id, set(rows.values_list("id", flat=True)))
