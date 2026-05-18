from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from entity.models import UserNotification
from financial.models import AccountBankDetails
from hrms.models import AttendancePolicy, ContractLeaveBalanceSnapshot, DailyAttendance, LeavePolicy, LeaveType
from hrms.services import AttendanceCaptureService, HrmsGlobalAdoptionService, LeaveApplicationService, LeaveApprovalService
from hrms.services.hrms_global_seed_service import HrmsGlobalSeedService
from payroll.models import (
    ContractTaxDeclaration,
    PayrollComponentPosting,
    PayrollRun,
    SalaryStructure,
    SalaryStructureLine,
    StatutoryScheme,
)
from payroll.services import (
    ContractSalaryAssignmentService,
    ContractStatutoryProfileService,
    ContractTaxDeclarationService,
    EntityPayrollPolicyService,
    EntityStatutoryRegistrationService,
    EntitySalaryTemplateAdoptionService,
    PayrollPaymentBatchService,
    PayrollRunService,
    PayslipService,
    StatutorySchemeService,
)
from payroll.services.payroll_global_seed_service import PayrollGlobalSeedService
from payroll.tests.factories import PayrollFactory

User = get_user_model()


@override_settings(PAYROLL_USE_CONTRACT_READINESS=True)
class HrmsPayrollProductionReadinessSmokeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="prod-readiness-admin",
            email="prod-readiness-admin@example.com",
            password="pass123",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.scope_patcher = patch("core.entitlements.SubscriptionService.assert_entity_access")
        self.scope_patcher.start()
        self.addCleanup(self.scope_patcher.stop)

        self.setup = PayrollFactory.full_payroll_setup()
        self.entity = self.setup["entity"]
        self.entityfinid = self.setup["entityfinid"]
        self.subentity = self.setup["subentity"]
        self.contract_profile = self.setup["contract_profile"]
        self.hrms_contract = self.setup["hrms_contract"]
        self.hrms_employee = self.setup["hrms_employee"]
        self.period = self.setup["period"]
        self.ledger_policy = self.setup["ledger_policy"]
        self.expense_account = self.setup["expense_account"]
        self.liability_account = self.setup["liability_account"]
        self.payable_account = self.setup["payable_account"]

        self.hrms_employee.linked_user = self.user
        self.hrms_employee.save(update_fields=["linked_user"])
        self.contract_profile.bank_account = self.payable_account
        self.contract_profile.attendance_required = True
        self.contract_profile.save(update_fields=["bank_account", "attendance_required", "updated_at"])
        AccountBankDetails.objects.create(
            account=self.payable_account,
            entity=self.entity,
            createdby=self.user,
            bankname="Axis Bank",
            banKAcno="123456789012",
            ifsc="UTIB0000001",
            branch="Main Branch",
            isprimary=True,
            isactive=True,
        )

    def _adopt_hrms_templates(self):
        HrmsGlobalSeedService.seed_default_catalog()
        adoption = HrmsGlobalAdoptionService.adopt_recommended_templates(
            entity=self.entity,
            subentity=self.subentity,
            industry_type="services",
            employee_category="sme_office",
            year=2025,
        )
        self.assertGreaterEqual(adoption["summary"]["counts"]["leave_policies"], 1)
        self.assertGreaterEqual(adoption["summary"]["counts"]["attendance_policies"], 1)
        attendance_policy = AttendancePolicy.objects.filter(
            entity=self.entity,
            deleted_at__isnull=True,
        ).order_by("-is_default", "code").first()
        self.assertIsNotNone(attendance_policy)
        attendance_policy.is_default = True
        attendance_policy.status = AttendancePolicy.Status.ACTIVE
        attendance_policy.policy_json = {
            **(attendance_policy.policy_json or {}),
            "payroll_attendance_requirement": "CLOSED",
        }
        attendance_policy.save(update_fields=["is_default", "status", "policy_json", "updated_at"])
        leave_policy = LeavePolicy.objects.filter(entity=self.entity, deleted_at__isnull=True).order_by("-is_default", "code").first()
        leave_type = LeaveType.objects.filter(entity=self.entity, deleted_at__isnull=True).order_by("code").first()
        self.assertIsNotNone(leave_policy)
        self.assertIsNotNone(leave_type)
        return leave_policy, leave_type

    def _adopt_payroll_template(self):
        PayrollGlobalSeedService.seed_default_catalog()
        template_code = "INDIA_SME_MONTHLY_STAFF"
        from payroll.models import GlobalSalaryStructureTemplate

        template = GlobalSalaryStructureTemplate.objects.get(code=template_code)
        result = EntitySalaryTemplateAdoptionService.adopt(
            entity_id=self.entity.id,
            entity_financial_year_id=self.entityfinid.id,
            subentity_id=self.subentity.id,
            global_template_id=template.id,
            effective_from=date(2025, 4, 15),
        )
        self.assertTrue(result["adopted"])
        structure = SalaryStructure.objects.get(entity=self.entity, code=template_code)
        version = structure.current_version
        self.assertIsNotNone(version)
        for line in SalaryStructureLine.objects.filter(salary_structure_version=version).select_related("component"):
            PayrollComponentPosting.objects.get_or_create(
                entity=self.entity,
                entityfinid=self.entityfinid,
                subentity=self.subentity,
                component=line.component,
                version_no=1,
                defaults={
                    "expense_account": self.expense_account,
                    "liability_account": self.liability_account,
                    "payable_account": self.payable_account,
                    "effective_from": date(2025, 4, 1),
                    "is_active": True,
                },
            )
        assignment = ContractSalaryAssignmentService.assign_salary_structure(
            {
                "contract_payroll_profile": self.contract_profile,
                "salary_structure": structure,
                "salary_structure_version": version,
                "effective_from": date(2025, 4, 15),
                "assignment_status": "ACTIVE",
                "ctc_amount": "120000.00",
                "gross_amount": "10000.00",
                "is_active": True,
            },
            close_previous_active=True,
        )
        self.assertEqual(assignment.salary_structure_id, structure.id)
        return structure, version

    def _configure_statutory_and_tax(self):
        EntityPayrollPolicyService.create_or_update_policy(
            {
                "entity": self.entity,
                "code": "MONTHLY_SMOKE",
                "name": "Monthly Smoke Policy",
                "pay_frequency": self.contract_profile.pay_frequency,
                "effective_from": date(2025, 4, 1),
                "is_default": True,
                "is_active": True,
            }
        )

        schemes = (
            StatutorySchemeService.create_or_update_scheme(
                {
                    "code": "PF_IN_SMOKE",
                    "name": "Provident Fund Smoke",
                    "scheme_type": StatutoryScheme.SchemeType.PF,
                    "country_code": "IN",
                    "state_code": "",
                    "is_system": True,
                    "is_active": True,
                }
            ),
            StatutorySchemeService.create_or_update_scheme(
                {
                    "code": "TDS_IN_SMOKE",
                    "name": "Tax Deducted at Source Smoke",
                    "scheme_type": StatutoryScheme.SchemeType.TDS,
                    "country_code": "IN",
                    "state_code": "",
                    "is_system": True,
                    "is_active": True,
                }
            ),
        )
        for scheme in schemes:
            ContractStatutoryProfileService.create_or_update_profile(
                {
                    "contract_payroll_profile": self.contract_profile,
                    "scheme": scheme,
                    "is_applicable": True,
                    "effective_from": date(2025, 4, 1),
                    "is_active": True,
                }
            )
            EntityStatutoryRegistrationService.create_or_update_registration(
                {
                    "entity": self.entity,
                    "scheme": scheme,
                    "registration_number": f"{scheme.scheme_type}-SMOKE-001",
                    "registration_state": "",
                    "effective_from": date(2025, 4, 1),
                    "is_active": True,
                }
            )

        declaration = PayrollFactory.contract_tax_declaration(
            entity=self.entity,
            contract_payroll_profile=self.contract_profile,
            financial_year=self.entityfinid,
            declaration_status=ContractTaxDeclaration.DeclarationStatus.DRAFT,
            approval_status=ContractTaxDeclaration.ApprovalStatus.DRAFT,
            tax_regime=ContractTaxDeclaration.TaxRegime.NEW,
            declared_annual_income="600000.00",
            projected_monthly_tds="2500.00",
        )
        ContractTaxDeclarationService.submit_for_approval(
            declaration=declaration,
            actor_id=self.user.id,
            remarks="submit tax declaration",
        )
        declaration = ContractTaxDeclarationService.approve(
            declaration=declaration,
            actor_id=self.user.id,
            remarks="approve tax declaration",
        )
        self.assertEqual(declaration.declaration_status, ContractTaxDeclaration.DeclarationStatus.APPROVED)

    def _run_leave_and_attendance_flow(self, *, leave_policy, leave_type):
        ContractLeaveBalanceSnapshot.objects.create(
            entity=self.entity,
            subentity=self.subentity,
            contract=self.hrms_contract,
            leave_policy=leave_policy,
            leave_type=leave_type,
            payroll_period_code=self.period.code,
            snapshot_date=self.period.period_start,
            snapshot_source=ContractLeaveBalanceSnapshot.SnapshotSource.OPENING,
            opening_balance=Decimal("5.00"),
            closing_balance=Decimal("5.00"),
            attendance_percentage=Decimal("100.00"),
        )
        leave_application = LeaveApplicationService.create_application(
            attrs={
                "contract": self.hrms_contract,
                "leave_type": leave_type,
                "leave_policy": leave_policy,
                "start_date": date(2025, 4, 10),
                "end_date": date(2025, 4, 10),
                "requested_days": "1.00",
                "reason": "Smoke test leave",
                "created_via": "qa-smoke",
            },
            actor=self.user,
        )
        leave_application = LeaveApprovalService.approve(
            application=leave_application,
            approver=self.user,
            approved_days=Decimal("1.00"),
            manager_note="approved in smoke flow",
        )
        self.assertEqual(leave_application.status, leave_application.Status.APPROVED)

        AttendanceCaptureService.bulk_upsert_entries(
            contract=self.hrms_contract,
            actor=self.user,
            rows=[
                {"attendance_date": date(2025, 4, 1), "status": DailyAttendance.AttendanceStatus.PRESENT},
                {"attendance_date": date(2025, 4, 2), "status": DailyAttendance.AttendanceStatus.PRESENT},
                {"attendance_date": date(2025, 4, 3), "status": DailyAttendance.AttendanceStatus.PRESENT, "overtime_hours": "2.00"},
                {"attendance_date": date(2025, 4, 4), "status": DailyAttendance.AttendanceStatus.HALF_DAY},
                {"attendance_date": date(2025, 4, 5), "status": DailyAttendance.AttendanceStatus.WEEKLY_OFF},
            ],
            source=DailyAttendance.EntrySource.MANUAL,
        )
        summary = AttendanceCaptureService.generate_monthly_summary(
            contract=self.hrms_contract,
            payroll_period=self.period,
        )
        self.assertGreater(Decimal(str(summary["payable_days"])), Decimal("0.00"))
        monthly_close = AttendanceCaptureService.get_or_create_monthly_close(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            payroll_period=self.period,
        )
        monthly_close = AttendanceCaptureService.submit_monthly_close(monthly_close=monthly_close, actor=self.user)
        monthly_close = AttendanceCaptureService.approve_monthly_close(monthly_close=monthly_close, actor=self.user)
        monthly_close = AttendanceCaptureService.close_monthly_close(
            monthly_close=monthly_close,
            actor=self.user,
            close_note="close month for readiness smoke",
        )
        self.assertEqual(monthly_close.status, monthly_close.Status.CLOSED)

    def test_full_hrms_payroll_smoke_flow(self):
        leave_policy, leave_type = self._adopt_hrms_templates()
        structure, version = self._adopt_payroll_template()
        self._configure_statutory_and_tax()
        self._run_leave_and_attendance_flow(leave_policy=leave_policy, leave_type=leave_type)

        readiness_response = self.client.get(
            f"/api/payroll/runtime/readiness-detail/?entity={self.entity.id}&contract={self.hrms_contract.id}&payroll_period={self.period.id}"
        )
        self.assertEqual(readiness_response.status_code, 200, readiness_response.content)
        self.assertEqual(readiness_response.json()["summary"]["readiness_status"], "READY")

        run_result = PayrollRunService.create_run(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfinid.id,
            subentity_id=self.subentity.id,
            payroll_period_id=self.period.id,
            run_type=PayrollRun.RunType.REGULAR,
            posting_date=self.period.period_end,
            payout_date=self.period.payout_date,
            created_by_id=self.user.id,
        )
        run = PayrollRunService.calculate_run(run_result.run).run
        self.assertEqual(run.status, PayrollRun.Status.CALCULATED)
        self.assertIn("contract_readiness", run.calculation_payload)
        row = run.employee_runs.select_related("contract_payroll_profile__hrms_contract__employee").get(
            contract_payroll_profile=self.contract_profile
        )
        self.assertEqual(row.salary_structure_id, structure.id)
        self.assertEqual(row.salary_structure_version_id, version.id)

        PayrollRunService.submit_run(run, submitted_by_id=self.user.id, note="submit smoke payroll", reason_code="READY")
        run = PayrollRunService.approve_run(run, approved_by_id=self.user.id, note="approve smoke payroll").run
        self.assertEqual(run.status, PayrollRun.Status.APPROVED)
        self.assertEqual(run.approval_status, PayrollRun.ApprovalStatus.LOCKED)

        payslip = PayslipService.build_for_run_employee(row)
        self.assertEqual(payslip.payroll_run_employee_id, row.id)

        with patch(
            "payroll.services.payroll_run_service.PayrollPostingService.post_run",
            return_value=SimpleNamespace(id=501, voucher_no="JV-501"),
        ):
            run = PayrollRunService.post_run(run, posted_by_id=self.user.id).run
        self.assertEqual(run.status, PayrollRun.Status.POSTED)
        self.assertEqual(run.post_reference, "JV-501")

        batch = PayrollPaymentBatchService.create_from_payroll_run(run=run, user_id=self.user.id)
        batch = PayrollPaymentBatchService.validate_batch(batch=batch, user_id=self.user.id)
        batch = PayrollPaymentBatchService.approve_batch(batch=batch, user_id=self.user.id, comment="approve payout batch")
        export_result = PayrollPaymentBatchService.export_batch(batch=batch, user_id=self.user.id)
        batch = PayrollPaymentBatchService.mark_paid(
            batch=export_result.batch,
            user_id=self.user.id,
            payment_reference="UTR-SMOKE-001",
            comment="paid in smoke flow",
        )
        run.refresh_from_db()
        self.assertEqual(batch.status, batch.Status.PAID)
        self.assertEqual(run.payment_status, PayrollRun.PaymentStatus.DISBURSED)

        payroll_register = self.client.get(
            f"/api/payroll/reports/payroll-register/?entity={self.entity.id}&entityfinid={self.entityfinid.id}&subentity={self.subentity.id}"
        )
        self.assertEqual(payroll_register.status_code, 200, payroll_register.content)
        self.assertEqual(payroll_register.json()["row_count"], 1)

        salary_sheet = self.client.get(
            f"/api/payroll/reports/salary-sheet/?entity={self.entity.id}&entityfinid={self.entityfinid.id}"
        )
        self.assertEqual(salary_sheet.status_code, 200, salary_sheet.content)
        self.assertEqual(salary_sheet.json()["row_count"], 1)

        payslip_list = self.client.get("/api/payroll/ess/payslips/")
        self.assertEqual(payslip_list.status_code, 200, payslip_list.content)
        payslip_payload = payslip_list.json()
        payslip_results = payslip_payload.get("results", payslip_payload) if isinstance(payslip_payload, dict) else payslip_payload
        self.assertEqual(len(payslip_results), 1)

        payslip_detail = self.client.get(f"/api/payroll/ess/payslips/{payslip.id}/")
        self.assertEqual(payslip_detail.status_code, 200, payslip_detail.content)
        self.assertEqual(payslip_detail.json()["payslip_number"], payslip.payslip_number)

        tax_summary = self.client.get("/api/payroll/ess/tax-declaration-summary/")
        self.assertEqual(tax_summary.status_code, 200, tax_summary.content)
        self.assertEqual(tax_summary.json()["status"], "available")

        attendance_placeholder = self.client.get("/api/payroll/ess/attendance-summary/placeholder/")
        self.assertEqual(attendance_placeholder.status_code, 200, attendance_placeholder.content)
        self.assertEqual(attendance_placeholder.json()["status"], "available")

        leave_mine = self.client.get(
            f"/api/hrms/leave-applications/?entity={self.entity.id}&subentity={self.subentity.id}&mine=true"
        )
        self.assertEqual(leave_mine.status_code, 200, leave_mine.content)
        self.assertEqual(len(leave_mine.json()), 1)

        unread_count = self.client.get(
            "/api/entity/notifications/unread-count/",
            {"entity": self.entity.id},
        )
        self.assertEqual(unread_count.status_code, 200, unread_count.content)
        self.assertGreater(unread_count.json()["count"], 0)

        notifications = self.client.get("/api/entity/notifications/", {"entity": self.entity.id})
        self.assertEqual(notifications.status_code, 200, notifications.content)
        notification_payload = notifications.json()
        notification_results = (
            notification_payload.get("results", notification_payload)
            if isinstance(notification_payload, dict)
            else notification_payload
        )
        self.assertTrue(notification_results)
        self.assertTrue(any(item.get("target_url") for item in notification_results))

        mark_target = UserNotification.objects.filter(user=self.user, is_read=False).latest("id")
        mark_read = self.client.post(f"/api/entity/notifications/{mark_target.id}/mark-read/", data={}, content_type="application/json")
        self.assertEqual(mark_read.status_code, 200, mark_read.content)
        mark_target.refresh_from_db()
        self.assertTrue(mark_target.is_read)

        event_codes = set(
            UserNotification.objects.filter(user=self.user).values_list("event__event_code", flat=True)
        )
        self.assertTrue(
            {
                "LEAVE_APPROVED",
                "ATTENDANCE_CLOSE_CLOSED",
                "CONTRACT_TAX_DECLARATION_APPROVED",
                "PAYROLL_RUN_APPROVED",
                "PAYSLIP_RELEASED",
                "PAYROLL_RUN_POSTED",
                "PAYMENT_BATCH_PAID",
            }.issubset(event_codes)
        )
