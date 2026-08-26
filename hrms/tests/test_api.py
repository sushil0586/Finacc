from datetime import date, datetime

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from Authentication.models import User
from entity.models import Entity, EntityFinancialYear
from hrms.models import (
    AttendanceApproval,
    AttendanceImportBatch,
    AttendanceMonthlyClose,
    ContractLeaveLedgerEntry,
    ContractLeaveBalanceSnapshot,
    DailyAttendance,
    HrEmployee,
    HrEmploymentContract,
    HrHoliday,
    HrHolidayCalendar,
    HrOrganizationUnit,
    HrShift,
    LeaveApplication,
    LeavePolicy,
    LeavePolicyRule,
    LeaveType,
)
from payroll.models import PayrollPeriod


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
        self.entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="HRMS API FY 2026-27",
            finstartyear=timezone.make_aware(datetime(2026, 4, 1)),
            finendyear=timezone.make_aware(datetime(2027, 3, 31)),
            createdby=self.user,
        )
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

    def test_entity_setup_patch_updates_leave_type_and_policy_used_by_ui(self):
        leave_type_response = self.client.patch(
            f"/api/hrms/onboarding/entity-setup/leave-type/{self.leave_type.id}/",
            {
                "name": "Casual Leave Browser API",
                "payroll_impact_code": "PAID_RUNTIME",
                "requires_balance": True,
                "counts_towards_attendance": True,
            },
            format="json",
        )
        self.assertEqual(leave_type_response.status_code, status.HTTP_200_OK)
        self.assertEqual(leave_type_response.data["name"], "Casual Leave Browser API")
        self.assertEqual(leave_type_response.data["payroll_impact_code"], "PAID_RUNTIME")

        summary_response = self.client.get(
            f"/api/hrms/onboarding/entity-setup-summary/?entity={self.entity.id}",
        )
        self.assertEqual(summary_response.status_code, status.HTTP_200_OK)
        summary_leave_type = next(
            item for item in summary_response.data["leave_types"] if item["id"] == str(self.leave_type.id)
        )
        self.assertEqual(summary_leave_type["payroll_impact_code"], "PAID_RUNTIME")
        self.assertTrue(summary_leave_type["requires_balance"])
        self.assertTrue(summary_leave_type["counts_towards_attendance"])

        policy_response = self.client.patch(
            f"/api/hrms/onboarding/entity-setup/leave-policy/{self.leave_policy.id}/",
            {
                "name": "Corporate Standard Browser API",
                "leave_year_type": LeavePolicy.LeaveYearType.CUSTOM_RANGE,
                "year_start_month": 4,
                "year_start_day": 1,
                "year_end_month": 3,
                "year_end_day": 31,
            },
            format="json",
        )
        self.assertEqual(policy_response.status_code, status.HTTP_200_OK)
        self.assertEqual(policy_response.data["name"], "Corporate Standard Browser API")
        self.assertEqual(policy_response.data["leave_year_type"], LeavePolicy.LeaveYearType.CUSTOM_RANGE)
        self.assertEqual(policy_response.data["year_start_month"], 4)
        self.assertEqual(policy_response.data["year_end_day"], 31)

    def test_master_crud_lifecycle_matches_browser_master_pages(self):
        org_create = self.client.post(
            "/api/hrms/organization-units/",
            {
                "entity": self.entity.id,
                "code": "TEAM-X",
                "name": "Team X",
                "unit_type": HrOrganizationUnit.UnitType.TEAM,
                "status": HrOrganizationUnit.Status.ACTIVE,
                "parent": self.org_active.id,
            },
            format="json",
        )
        self.assertEqual(org_create.status_code, status.HTTP_201_CREATED)
        org_id = org_create.data["id"]
        org_patch = self.client.patch(
            f"/api/hrms/organization-units/{org_id}/",
            {"name": "Team X Updated", "status": HrOrganizationUnit.Status.INACTIVE},
            format="json",
        )
        self.assertEqual(org_patch.status_code, status.HTTP_200_OK)
        self.assertEqual(org_patch.data["name"], "Team X Updated")
        self.assertEqual(org_patch.data["parent_name"], "Admin Department")
        org_delete = self.client.delete(f"/api/hrms/organization-units/{org_id}/")
        self.assertEqual(org_delete.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(HrOrganizationUnit.objects.filter(pk=org_id).exists())

        employee_create = self.client.post(
            "/api/hrms/employees/",
            {
                "entity": self.entity.id,
                "employee_number": "EMP-3001",
                "legal_first_name": "Browser",
                "legal_last_name": "Employee",
                "work_email": "browser.employee@example.com",
                "mobile_number": "9998887776",
                "lifecycle_status": HrEmployee.LifecycleStatus.ACTIVE,
            },
            format="json",
        )
        self.assertEqual(employee_create.status_code, status.HTTP_201_CREATED)
        employee_id = employee_create.data["id"]
        self.assertEqual(employee_create.data["display_name"], "Browser Employee")
        employee_patch = self.client.patch(
            f"/api/hrms/employees/{employee_id}/",
            {"display_name": "Browser Employee Updated", "lifecycle_status": HrEmployee.LifecycleStatus.INACTIVE, "is_active": False},
            format="json",
        )
        self.assertEqual(employee_patch.status_code, status.HTTP_200_OK)
        self.assertEqual(employee_patch.data["display_name"], "Browser Employee Updated")
        self.assertFalse(employee_patch.data["is_active"])
        employee_delete = self.client.delete(f"/api/hrms/employees/{employee_id}/")
        self.assertEqual(employee_delete.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(HrEmployee.objects.filter(pk=employee_id).exists())

    def test_contract_shift_and_holiday_calendar_crud_match_browser_master_pages(self):
        shift_create = self.client.post(
            "/api/hrms/shifts/",
            {
                "entity": self.entity.id,
                "code": "GEN2",
                "name": "General Shift 2",
                "shift_type": HrShift.ShiftType.FIXED,
                "status": HrShift.Status.ACTIVE,
                "timezone": "Asia/Kolkata",
                "start_time": "09:30:00",
                "end_time": "18:30:00",
                "break_minutes": 45,
                "weekly_off_pattern": ["Saturday", "Sunday"],
            },
            format="json",
        )
        self.assertEqual(shift_create.status_code, status.HTTP_201_CREATED)
        shift_id = shift_create.data["id"]
        shift_patch = self.client.patch(
            f"/api/hrms/shifts/{shift_id}/",
            {"name": "General Shift Updated", "crosses_midnight": True, "start_time": "22:00:00", "end_time": "06:00:00"},
            format="json",
        )
        self.assertEqual(shift_patch.status_code, status.HTTP_200_OK)
        self.assertEqual(shift_patch.data["name"], "General Shift Updated")
        self.assertTrue(shift_patch.data["crosses_midnight"])

        calendar_create = self.client.post(
            "/api/hrms/holiday-calendars/",
            {
                "entity": self.entity.id,
                "code": "HC-2028",
                "name": "FY 2028",
                "calendar_year": 2028,
                "period_start": "2028-01-01",
                "period_end": "2028-12-31",
                "status": HrHolidayCalendar.Status.ACTIVE,
                "is_default": False,
            },
            format="json",
        )
        self.assertEqual(calendar_create.status_code, status.HTTP_201_CREATED)
        calendar_id = calendar_create.data["id"]
        holiday_create = self.client.post(
            f"/api/hrms/holiday-calendars/{calendar_id}/holidays/",
            {
                "holiday_date": "2028-01-26",
                "name": "Republic Day 2028",
                "holiday_type": HrHoliday.HolidayType.PUBLIC,
                "is_paid": True,
            },
            format="json",
        )
        self.assertEqual(holiday_create.status_code, status.HTTP_201_CREATED)
        holiday_id = holiday_create.data["id"]
        calendar_patch = self.client.patch(
            f"/api/hrms/holiday-calendars/{calendar_id}/",
            {"name": "FY 2028 Updated", "status": HrHolidayCalendar.Status.ARCHIVED},
            format="json",
        )
        self.assertEqual(calendar_patch.status_code, status.HTTP_200_OK)
        self.assertEqual(calendar_patch.data["name"], "FY 2028 Updated")
        holiday_patch = self.client.patch(
            f"/api/hrms/holidays/{holiday_id}/",
            {"name": "Republic Day Observed"},
            format="json",
        )
        self.assertEqual(holiday_patch.status_code, status.HTTP_200_OK)
        self.assertEqual(holiday_patch.data["name"], "Republic Day Observed")

        contract_create = self.client.post(
            "/api/hrms/contracts/",
            {
                "entity": self.entity.id,
                "employee": self.second_employee.id,
                "contract_code": "CTR-3001",
                "start_date": "2026-05-01",
                "payroll_effective_from": "2026-05-01",
                "status": HrEmploymentContract.ContractStatus.DRAFT,
                "contract_type": HrEmploymentContract.ContractType.CONSULTING,
                "work_model": HrEmploymentContract.WorkModel.HYBRID,
                "compensation_basis": HrEmploymentContract.CompensationBasis.MONTHLY,
                "default_shift": shift_id,
                "holiday_calendar": calendar_id,
                "is_payroll_eligible": False,
                "pay_group_code": "MONTHLY-HQ",
            },
            format="json",
        )
        self.assertEqual(contract_create.status_code, status.HTTP_201_CREATED)
        contract_id = contract_create.data["id"]
        self.assertEqual(contract_create.data["employee_display_name"], "Vikram Bose")
        self.assertEqual(contract_create.data["default_shift_name"], "General Shift Updated")
        contract_patch = self.client.patch(
            f"/api/hrms/contracts/{contract_id}/",
            {"contract_code": "CTR-3001A", "status": HrEmploymentContract.ContractStatus.ACTIVE, "is_payroll_eligible": True},
            format="json",
        )
        self.assertEqual(contract_patch.status_code, status.HTTP_200_OK)
        self.assertEqual(contract_patch.data["contract_code"], "CTR-3001A")
        self.assertTrue(contract_patch.data["is_payroll_eligible"])

        contract_delete = self.client.delete(f"/api/hrms/contracts/{contract_id}/")
        self.assertEqual(contract_delete.status_code, status.HTTP_204_NO_CONTENT)
        shift_delete = self.client.delete(f"/api/hrms/shifts/{shift_id}/")
        self.assertEqual(shift_delete.status_code, status.HTTP_204_NO_CONTENT)
        holiday_delete = self.client.delete(f"/api/hrms/holidays/{holiday_id}/")
        self.assertEqual(holiday_delete.status_code, status.HTTP_204_NO_CONTENT)
        calendar_delete = self.client.delete(f"/api/hrms/holiday-calendars/{calendar_id}/")
        self.assertEqual(calendar_delete.status_code, status.HTTP_204_NO_CONTENT)

    def test_daily_attendance_and_import_batch_api_match_browser_runtime_contract(self):
        payroll_period = PayrollPeriod.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            code="APR-2026-ATT",
            period_start=date(2026, 4, 1),
            period_end=date(2026, 4, 30),
            pay_frequency=PayrollPeriod.PayFrequency.MONTHLY,
        )
        import_response = self.client.post(
            "/api/hrms/attendance-import-batches/",
            {
                "entity": self.entity.id,
                "batch_code": "ATT-JUN-2026",
                "file_name": "attendance-jun.csv",
                "import_mode": AttendanceImportBatch.ImportMode.PLACEHOLDER,
                "remarks": "Browser parity import",
            },
            format="json",
        )
        self.assertEqual(import_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(import_response.data["batch_code"], "ATT-JUN-2026")
        self.assertEqual(import_response.data["import_status"], AttendanceImportBatch.ImportStatus.UPLOADED)

        bulk_response = self.client.post(
            "/api/hrms/daily-attendance/bulk-upsert/",
            {
                "entity": self.entity.id,
                "contract": self.contract.id,
                "rows": [
                    {
                        "attendance_date": "2026-04-02",
                        "status": DailyAttendance.AttendanceStatus.HALF_DAY,
                        "overtime_hours": "1.25",
                        "late_mark": True,
                        "remarks": "Late arrival",
                    },
                    {
                        "attendance_date": "2026-04-03",
                        "status": DailyAttendance.AttendanceStatus.PRESENT,
                        "overtime_hours": "0.00",
                    },
                ],
            },
            format="json",
        )
        self.assertEqual(bulk_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(bulk_response.data), 2)

        list_response = self.client.get(
            "/api/hrms/daily-attendance/",
            {
                "entity": self.entity.id,
                "contract": self.contract.id,
                "start_date": "2026-04-01",
                "end_date": "2026-04-30",
            },
        )
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list_response.data), 2)
        self.assertEqual(list_response.data[0]["remarks"], "Late arrival")
        self.assertTrue(list_response.data[0]["late_mark"])

        summary_response = self.client.get(
            "/api/hrms/attendance-monthly-summaries/",
            {"entity": self.entity.id, "payroll_period": payroll_period.id, "contract": self.contract.id},
        )
        self.assertEqual(summary_response.status_code, status.HTTP_200_OK)
        self.assertEqual(summary_response.data["payroll_period_code"], "APR-2026-ATT")
        self.assertEqual(summary_response.data["items"][0]["contract_code"], "CTR-2001")
        self.assertEqual(summary_response.data["items"][0]["late_count"], 1)

        import_list = self.client.get("/api/hrms/attendance-import-batches/", {"entity": self.entity.id})
        self.assertEqual(import_list.status_code, status.HTTP_200_OK)
        self.assertEqual(import_list.data[0]["batch_code"], "ATT-JUN-2026")

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

    def test_attendance_monthly_close_api_requires_approved_contract_summaries(self):
        payroll_period = PayrollPeriod.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            code="APR-2026-CLOSE",
            period_start=date(2026, 4, 1),
            period_end=date(2026, 4, 30),
            pay_frequency=PayrollPeriod.PayFrequency.MONTHLY,
        )
        approval = AttendanceApproval.objects.create(
            entity=self.entity,
            subentity=None,
            contract=self.contract,
            payroll_period_code=payroll_period.code,
            period_start=payroll_period.period_start,
            period_end=payroll_period.period_end,
            status=AttendanceApproval.Status.SUBMITTED,
            summary_json={"payable_days": "26.00", "lop_days": "1.00"},
            created_by=self.user,
            updated_by=self.user,
        )

        create_close_response = self.client.post(
            "/api/hrms/attendance-monthly-closes/",
            {"entity": self.entity.id, "payroll_period": payroll_period.id},
            format="json",
        )
        self.assertEqual(create_close_response.status_code, status.HTTP_201_CREATED)

        list_close_response = self.client.get(
            "/api/hrms/attendance-monthly-closes/",
            {"entity": self.entity.id},
        )
        self.assertEqual(list_close_response.status_code, status.HTTP_200_OK)
        self.assertEqual(list_close_response.data[0]["payroll_period_code"], payroll_period.code)

        blocked_submit_response = self.client.post(
            f"/api/hrms/attendance-monthly-closes/{create_close_response.data['id']}/submit/",
            {},
            format="json",
        )
        self.assertEqual(blocked_submit_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("approval_counts", blocked_submit_response.data)

        approve_contract_response = self.client.post(
            f"/api/hrms/attendance-approvals/{approval.id}/approve/",
            {"review_note": "Approved for close"},
            format="json",
        )
        self.assertEqual(approve_contract_response.status_code, status.HTTP_200_OK)

        submit_response = self.client.post(
            f"/api/hrms/attendance-monthly-closes/{create_close_response.data['id']}/submit/",
            {},
            format="json",
        )
        self.assertEqual(submit_response.status_code, status.HTTP_200_OK)
        self.assertEqual(submit_response.data["status"], AttendanceMonthlyClose.Status.SUBMITTED)
        self.assertEqual(submit_response.data["summary_json"]["approval_counts"], {AttendanceApproval.Status.APPROVED: 1})

        approve_close_response = self.client.post(
            f"/api/hrms/attendance-monthly-closes/{create_close_response.data['id']}/approve/",
            {},
            format="json",
        )
        self.assertEqual(approve_close_response.status_code, status.HTTP_200_OK)
        self.assertEqual(approve_close_response.data["status"], AttendanceMonthlyClose.Status.APPROVED)

        close_response = self.client.post(
            f"/api/hrms/attendance-monthly-closes/{create_close_response.data['id']}/close/",
            {"close_note": "Closed for payroll API regression"},
            format="json",
        )
        self.assertEqual(close_response.status_code, status.HTTP_200_OK)
        self.assertEqual(close_response.data["status"], AttendanceMonthlyClose.Status.CLOSED)
        self.assertEqual(close_response.data["close_note"], "Closed for payroll API regression")

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

    def test_leave_application_approval_api_consumes_balance_and_writes_ledger(self):
        ContractLeaveBalanceSnapshot.objects.create(
            entity=self.entity,
            contract=self.contract,
            leave_policy=self.leave_policy,
            leave_type=self.leave_type,
            snapshot_date=date(2026, 8, 1),
            snapshot_source=ContractLeaveBalanceSnapshot.SnapshotSource.OPENING,
            opening_balance="5.00",
            closing_balance="5.00",
            attendance_percentage="100.00",
        )

        create_response = self.client.post(
            "/api/hrms/leave-applications/",
            {
                "entity": self.entity.id,
                "contract": self.contract.id,
                "leave_type": self.leave_type.id,
                "start_date": "2026-08-20",
                "end_date": "2026-08-21",
                "requested_days": "2.00",
                "reason": "API lifecycle leave",
            },
            format="json",
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(create_response.data["status"], LeaveApplication.Status.SUBMITTED)
        self.assertEqual(create_response.data["approval_status"], LeaveApplication.ApprovalStatus.PENDING_APPROVAL)

        approve_response = self.client.post(
            f"/api/hrms/leave-applications/{create_response.data['id']}/approve/",
            {"approved_days": "2.00", "manager_note": "Approved by API test"},
            format="json",
        )

        self.assertEqual(approve_response.status_code, status.HTTP_200_OK)
        self.assertEqual(approve_response.data["status"], LeaveApplication.Status.APPROVED)
        self.assertEqual(approve_response.data["approval_status"], LeaveApplication.ApprovalStatus.APPROVED)
        self.assertEqual(str(approve_response.data["paid_days"]), "2.00")
        self.assertEqual(str(approve_response.data["unpaid_days"]), "0.00")

        balance_response = self.client.get(
            "/api/hrms/leave-balances/",
            {"entity": self.entity.id, "contract": self.contract.id},
        )
        self.assertEqual(balance_response.status_code, status.HTTP_200_OK)
        balance_item = next(item for item in balance_response.data["items"] if item["leave_type_id"] == str(self.leave_type.id))
        self.assertEqual(balance_item["balance_days"], "3.00")

        ledger = ContractLeaveLedgerEntry.objects.get(reference_id=create_response.data["id"])
        self.assertEqual(ledger.entry_type, ContractLeaveLedgerEntry.EntryType.CONSUMPTION)
        self.assertEqual(str(ledger.quantity_days), "-2.00")
        self.assertEqual(str(ledger.balance_after_days), "3.00")

    def test_leave_application_reject_and_cancel_api_keep_timeline_auditable(self):
        reject_create_response = self.client.post(
            "/api/hrms/leave-applications/",
            {
                "entity": self.entity.id,
                "contract": self.contract.id,
                "leave_type": self.leave_type.id,
                "start_date": "2026-09-01",
                "end_date": "2026-09-01",
                "requested_days": "1.00",
                "reason": "Reject lifecycle leave",
            },
            format="json",
        )
        self.assertEqual(reject_create_response.status_code, status.HTTP_201_CREATED)

        reject_response = self.client.post(
            f"/api/hrms/leave-applications/{reject_create_response.data['id']}/reject/",
            {"manager_note": "Rejected by API parity test"},
            format="json",
        )
        self.assertEqual(reject_response.status_code, status.HTTP_200_OK)
        self.assertEqual(reject_response.data["status"], LeaveApplication.Status.REJECTED)
        self.assertEqual(reject_response.data["approval_status"], LeaveApplication.ApprovalStatus.REJECTED)
        self.assertEqual(reject_response.data["manager_note"], "Rejected by API parity test")
        self.assertFalse(ContractLeaveLedgerEntry.objects.filter(reference_id=reject_create_response.data["id"]).exists())

        cancel_create_response = self.client.post(
            "/api/hrms/leave-applications/",
            {
                "entity": self.entity.id,
                "contract": self.contract.id,
                "leave_type": self.leave_type.id,
                "start_date": "2026-09-05",
                "end_date": "2026-09-05",
                "requested_days": "0.50",
                "reason": "Cancel lifecycle leave",
            },
            format="json",
        )
        self.assertEqual(cancel_create_response.status_code, status.HTTP_201_CREATED)

        cancel_response = self.client.post(
            f"/api/hrms/leave-applications/{cancel_create_response.data['id']}/cancel/",
            {"manager_note": "Cancelled by API parity test"},
            format="json",
        )
        self.assertEqual(cancel_response.status_code, status.HTTP_200_OK)
        self.assertEqual(cancel_response.data["status"], LeaveApplication.Status.CANCELLED)
        self.assertEqual(cancel_response.data["approval_status"], LeaveApplication.ApprovalStatus.CANCELLED)
        self.assertEqual(cancel_response.data["manager_note"], "Cancelled by API parity test")

        list_response = self.client.get(
            "/api/hrms/leave-applications/",
            {"entity": self.entity.id, "contract": self.contract.id},
        )
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        timeline_statuses = {item["reason"]: item["approval_status"] for item in list_response.data}
        self.assertEqual(timeline_statuses["Reject lifecycle leave"], LeaveApplication.ApprovalStatus.REJECTED)
        self.assertEqual(timeline_statuses["Cancel lifecycle leave"], LeaveApplication.ApprovalStatus.CANCELLED)

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
