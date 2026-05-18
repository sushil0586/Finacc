from datetime import date

from django.test import TestCase

from Authentication.models import User
from entity.models import Entity
from hrms.models import HrEmployee, HrEmploymentContract, HrOrganizationUnit
from hrms.services import EmployeeService, EmploymentContractService, OrganizationUnitService


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
