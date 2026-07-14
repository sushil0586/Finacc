from datetime import date

from rest_framework import status
from rest_framework.test import APITestCase

from Authentication.models import User
from entity.models import Entity
from hrms.models import (
    AttendanceApproval,
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

    def test_attendance_approval_list_filters_by_payroll_period_id(self):
        AttendanceApproval.objects.create(
            entity=self.entity,
            subentity=None,
            contract=self.contract,
            payroll_period_code="APR-2026-APP",
            period_start=date(2026, 4, 1),
            period_end=date(2026, 4, 30),
            status=AttendanceApproval.Status.SUBMITTED,
            summary_json={"payable_days": "26.00", "lop_days": "1.00"},
            created_by=self.user,
            updated_by=self.user,
        )
        response = self.client.get(
            "/api/hrms/attendance-approvals/",
            {"entity": self.entity.id, "payroll_period_code": "APR-2026-APP"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["contract_code"], "CTR-2001")
        self.assertEqual(response.data[0]["payroll_period_code"], "APR-2026-APP")

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

    def test_create_organization_unit_rejects_oversized_fields(self):
        response = self.client.post(
            "/api/hrms/organization-units/",
            {
                "entity": self.entity.id,
                "code": "C" * 41,
                "name": "N" * 151,
                "short_name": "S" * 81,
                "unit_type": HrOrganizationUnit.UnitType.DEPARTMENT,
                "description": "D" * 256,
                "external_ref": "E" * 81,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("code", response.data)
        self.assertIn("name", response.data)
        self.assertIn("short_name", response.data)
        self.assertIn("description", response.data)
        self.assertIn("external_ref", response.data)

    def test_create_employee_rejects_oversized_fields(self):
        response = self.client.post(
            "/api/hrms/employees/",
            {
                "entity": self.entity.id,
                "employee_number": "E" * 41,
                "legal_first_name": "F" * 81,
                "legal_last_name": "L" * 81,
                "preferred_name": "P" * 81,
                "display_name": "D" * 181,
                "work_email": ("a" * 245) + "@example.com",
                "personal_email": ("b" * 245) + "@example.com",
                "mobile_number": "9" * 21,
                "external_ref": "R" * 81,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("employee_number", response.data)
        self.assertIn("legal_first_name", response.data)
        self.assertIn("legal_last_name", response.data)
        self.assertIn("preferred_name", response.data)
        self.assertIn("display_name", response.data)
        self.assertIn("work_email", response.data)
        self.assertIn("personal_email", response.data)
        self.assertIn("mobile_number", response.data)
        self.assertIn("external_ref", response.data)

    def test_create_contract_rejects_oversized_fields(self):
        response = self.client.post(
            "/api/hrms/contracts/",
            {
                "entity": self.entity.id,
                "employee": self.employee.id,
                "contract_code": "C" * 41,
                "start_date": "2026-04-01",
                "payroll_effective_from": "2026-04-01",
                "notice_period_days": 366,
                "pay_group_code": "P" * 41,
                "vendor_reference": "V" * 81,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("contract_code", response.data)
        self.assertIn("notice_period_days", response.data)
        self.assertIn("pay_group_code", response.data)
        self.assertIn("vendor_reference", response.data)

    def test_create_shift_rejects_oversized_fields(self):
        response = self.client.post(
            "/api/hrms/shifts/",
            {
                "entity": self.entity.id,
                "code": "S" * 41,
                "name": "N" * 121,
                "shift_type": "open",
                "timezone": "T" * 51,
                "break_minutes": 1441,
                "grace_in_minutes": 241,
                "grace_out_minutes": 241,
                "minimum_full_day_minutes": 1441,
                "description": "D" * 256,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("code", response.data)
        self.assertIn("name", response.data)
        self.assertIn("timezone", response.data)
        self.assertIn("break_minutes", response.data)
        self.assertIn("grace_in_minutes", response.data)
        self.assertIn("grace_out_minutes", response.data)
        self.assertIn("minimum_full_day_minutes", response.data)
        self.assertIn("description", response.data)

    def test_create_holiday_calendar_rejects_oversized_fields(self):
        response = self.client.post(
            "/api/hrms/holiday-calendars/",
            {
                "entity": self.entity.id,
                "code": "H" * 41,
                "name": "N" * 151,
                "calendar_year": 2101,
                "description": "D" * 256,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("code", response.data)
        self.assertIn("name", response.data)
        self.assertIn("calendar_year", response.data)
        self.assertIn("description", response.data)

    def test_create_holiday_rejects_oversized_fields(self):
        response = self.client.post(
            f"/api/hrms/holiday-calendars/{self.holiday_calendar.id}/holidays/",
            {
                "holiday_date": "2026-11-01",
                "name": "N" * 151,
                "description": "D" * 256,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("name", response.data)
        self.assertIn("description", response.data)
