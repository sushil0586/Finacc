from datetime import date

from rest_framework import status
from rest_framework.test import APITestCase

from Authentication.models import User
from entity.models import Entity
from hrms.models import (
    ContractLeaveBalanceSnapshot,
    HrEmployee,
    HrEmploymentContract,
    HrHoliday,
    HrHolidayCalendar,
    HrOrganizationUnit,
    LeavePolicy,
    LeavePolicyRule,
    LeaveType,
)


class HrmsApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="hrms-api@example.com",
            username="hrms-api@example.com",
            password="testpass123",
        )
        self.user.is_superuser = True
        self.user.is_staff = True
        self.user.save(update_fields=["is_superuser", "is_staff"])
        self.entity = Entity.objects.create(entityname="HRMS API Entity", createdby=self.user)
        self.client.force_authenticate(self.user)

        self.org_active = HrOrganizationUnit.objects.create(
            entity=self.entity,
            code="DEPT-A",
            name="Admin Department",
            unit_type=HrOrganizationUnit.UnitType.DEPARTMENT,
            status=HrOrganizationUnit.Status.ACTIVE,
            created_by=self.user,
            updated_by=self.user,
        )
        self.org_archived = HrOrganizationUnit.objects.create(
            entity=self.entity,
            code="DEPT-Z",
            name="Archive Department",
            unit_type=HrOrganizationUnit.UnitType.DEPARTMENT,
            status=HrOrganizationUnit.Status.ARCHIVED,
            created_by=self.user,
            updated_by=self.user,
        )

        self.employee = HrEmployee.objects.create(
            entity=self.entity,
            employee_number="EMP-2001",
            legal_first_name="Anya",
            legal_last_name="Rao",
            display_name="Anya Rao",
            work_email="anya@example.com",
            lifecycle_status=HrEmployee.LifecycleStatus.ACTIVE,
            created_by=self.user,
            updated_by=self.user,
        )
        self.second_employee = HrEmployee.objects.create(
            entity=self.entity,
            employee_number="EMP-2002",
            legal_first_name="Vikram",
            legal_last_name="Bose",
            display_name="Vikram Bose",
            work_email="vikram@example.com",
            lifecycle_status=HrEmployee.LifecycleStatus.INACTIVE,
            is_active=False,
            created_by=self.user,
            updated_by=self.user,
        )

        self.contract = HrEmploymentContract.objects.create(
            entity=self.entity,
            employee=self.employee,
            contract_code="CTR-2001",
            start_date=date(2026, 4, 1),
            payroll_effective_from=date(2026, 4, 1),
            status=HrEmploymentContract.ContractStatus.ACTIVE,
            is_payroll_eligible=True,
            created_by=self.user,
            updated_by=self.user,
        )
        HrEmploymentContract.objects.create(
            entity=self.entity,
            employee=self.second_employee,
            contract_code="CTR-2002",
            start_date=date(2025, 1, 1),
            end_date=date(2026, 3, 31),
            payroll_effective_from=date(2025, 1, 1),
            status=HrEmploymentContract.ContractStatus.CLOSED,
            is_payroll_eligible=False,
            created_by=self.user,
            updated_by=self.user,
        )

        self.holiday_calendar = HrHolidayCalendar.objects.create(
            entity=self.entity,
            code="HC-2026",
            name="FY 2026",
            calendar_year=2026,
            period_start=date(2026, 4, 1),
            period_end=date(2027, 3, 31),
            status=HrHolidayCalendar.Status.ACTIVE,
            created_by=self.user,
            updated_by=self.user,
        )
        self.holiday = HrHoliday.objects.create(
            entity=self.entity,
            holiday_calendar=self.holiday_calendar,
            holiday_date=date(2026, 10, 2),
            name="Gandhi Jayanti",
            holiday_type=HrHoliday.HolidayType.PUBLIC,
            is_paid=True,
            is_optional=False,
            created_by=self.user,
            updated_by=self.user,
        )
        self.leave_type = LeaveType.objects.create(
            entity=self.entity,
            code="CL",
            name="Casual Leave",
            category=LeaveType.Category.CASUAL,
            created_by=self.user,
            updated_by=self.user,
        )
        self.leave_policy = LeavePolicy.objects.create(
            entity=self.entity,
            code="CORP_STD",
            name="Corporate Standard",
            employee_category=LeavePolicy.EmployeeCategory.SERVICES,
            effective_from=date(2026, 4, 1),
            created_by=self.user,
            updated_by=self.user,
        )
        self.leave_policy_rule = LeavePolicyRule.objects.create(
            entity=self.entity,
            leave_policy=self.leave_policy,
            leave_type=self.leave_type,
            rule_code="CL_YEARLY",
            rule_name="Casual Leave yearly quota",
            rule_json={"accrual_frequency": "yearly", "annual_quota": 12},
            effective_from=date(2026, 4, 1),
            created_by=self.user,
            updated_by=self.user,
        )

    def test_organization_units_api_filters_by_status(self):
        response = self.client.get(
            "/api/hrms/organization-units/",
            {"entity": self.entity.id, "status": HrOrganizationUnit.Status.ARCHIVED, "active_only": "false"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["code"], "DEPT-Z")

    def test_employees_api_searches_by_name(self):
        response = self.client.get(
            "/api/hrms/employees/",
            {"entity": self.entity.id, "search": "anya"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["employee_number"], "EMP-2001")

    def test_contracts_api_filters_payroll_eligibility(self):
        response = self.client.get(
            "/api/hrms/contracts/",
            {"entity": self.entity.id, "payroll_eligible": "false", "active_only": "false"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["contract_code"], "CTR-2002")

    def test_holiday_calendars_api_filters_by_year(self):
        response = self.client.get(
            "/api/hrms/holiday-calendars/",
            {"entity": self.entity.id, "calendar_year": 2026},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["code"], "HC-2026")

    def test_holiday_detail_patch_updates_without_deleted_at_keyerror(self):
        response = self.client.patch(
            f"/api/hrms/holidays/{self.holiday.id}/",
            {"name": "National Holiday"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.holiday.refresh_from_db()
        self.assertEqual(self.holiday.name, "National Holiday")

    def test_holiday_can_be_saved_within_calendar_period_even_if_next_year(self):
        response = self.client.patch(
            f"/api/hrms/holidays/{self.holiday.id}/",
            {"holiday_date": "2027-01-01"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.holiday.refresh_from_db()
        self.assertEqual(self.holiday.holiday_date, date(2027, 1, 1))

    def test_leave_policy_rule_patch_updates_without_deleted_at_keyerror(self):
        response = self.client.patch(
            f"/api/hrms/leave-policy-rules/{self.leave_policy_rule.id}/",
            {"rule_name": "Casual Leave annual quota"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.leave_policy_rule.refresh_from_db()
        self.assertEqual(self.leave_policy_rule.rule_name, "Casual Leave annual quota")

    def test_leave_balance_bootstrap_creates_opening_snapshots_from_policy_defaults(self):
        response = self.client.post(
            f"/api/hrms/leave-balances/contracts/{self.contract.id}/bootstrap/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["created_count"], 1)
        snapshot = ContractLeaveBalanceSnapshot.objects.get(contract=self.contract, leave_type=self.leave_type)
        self.assertEqual(str(snapshot.closing_balance), "12.00")
        self.assertEqual(snapshot.snapshot_source, ContractLeaveBalanceSnapshot.SnapshotSource.OPENING)

        balance_response = self.client.get(
            "/api/hrms/leave-balances/",
            {"entity": self.entity.id, "contract": self.contract.id},
        )
        self.assertEqual(balance_response.status_code, status.HTTP_200_OK)
        self.assertIn("leave_year_start", balance_response.data)
        self.assertIn("leave_year_end", balance_response.data)

    def test_leave_balance_bootstrap_prorates_yearly_quota_for_mid_year_joiner(self):
        self.leave_policy.leave_year_type = LeavePolicy.LeaveYearType.CALENDAR_YEAR
        self.leave_policy.save(update_fields=["leave_year_type"])
        self.contract.start_date = date(2026, 4, 1)
        self.contract.payroll_effective_from = date(2026, 4, 1)
        self.contract.save(update_fields=["start_date", "payroll_effective_from"])

        response = self.client.post(
            f"/api/hrms/leave-balances/contracts/{self.contract.id}/bootstrap/",
            {"as_of_date": "2026-04-01"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        snapshot = ContractLeaveBalanceSnapshot.objects.get(contract=self.contract, leave_type=self.leave_type)
        self.assertEqual(str(snapshot.closing_balance), "9.00")

    def test_leave_balance_accrual_creates_periodic_balance_movement(self):
        self.leave_policy_rule.rule_json = {"accrual_frequency": "monthly", "monthly_quota": 1.5}
        self.leave_policy_rule.save(update_fields=["rule_json"])

        response = self.client.post(
            f"/api/hrms/leave-balances/contracts/{self.contract.id}/accrue/",
            {"as_of_date": "2026-04-30"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["created_count"], 1)
        snapshot = ContractLeaveBalanceSnapshot.objects.get(contract=self.contract, leave_type=self.leave_type)
        self.assertEqual(str(snapshot.closing_balance), "1.50")
        self.assertEqual(snapshot.snapshot_source, ContractLeaveBalanceSnapshot.SnapshotSource.ACCRUAL)
