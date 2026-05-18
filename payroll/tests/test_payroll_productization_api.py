from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from payroll.models import (
    ContractTaxDeclaration,
    ContractTaxDeclarationLine,
    FnFSettlement,
    OneTimePayItem,
    PayrollComponent,
    PayrollRun,
)
from payroll.services import (
    ContractPayrollProfileService,
    PayslipService,
    PayrollFnFEngine,
    PayrollRunService,
)
from payroll.tests.factories import PayrollFactory

User = get_user_model()


class PayrollProductizationApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="payroll-admin",
            email="payroll-admin@example.com",
            password="pass123",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.scope_patcher = patch("core.entitlements.SubscriptionService.assert_entity_access")
        self.scope_patcher.start()
        self.addCleanup(self.scope_patcher.stop)

        self.setup = PayrollFactory.full_payroll_setup()
        self.setup["hrms_employee"].linked_user = self.user
        self.setup["hrms_employee"].save(update_fields=["linked_user"])
        self.entity_id = self.setup["entity"].id
        self.entityfinid_id = self.setup["entityfinid"].id
        self.subentity_id = self.setup["subentity"].id

    def _create_run_with_payslip(self):
        result = PayrollRunService.create_run(
            entity_id=self.entity_id,
            entityfinid_id=self.entityfinid_id,
            subentity_id=self.subentity_id,
            payroll_period_id=self.setup["period"].id,
            run_type=PayrollRun.RunType.REGULAR,
            posting_date=self.setup["period"].period_end,
            payout_date=self.setup["period"].payout_date,
            created_by_id=self.user.id,
        )
        run = PayrollRunService.calculate_run(result.run).run
        row = run.employee_runs.select_related("contract_payroll_profile__hrms_contract__employee").prefetch_related("components__component").get()
        payslip = PayslipService.build_for_run_employee(row)
        return run, row, payslip

    def _add_statutory_component_row(self, row):
        pf_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="PF_EMPLOYEE",
            component_type=PayrollComponent.ComponentType.DEDUCTION,
            posting_behavior=PayrollComponent.PostingBehavior.EMPLOYEE_LIABILITY,
            semantic_code=PayrollComponent.SemanticCode.PF_EMPLOYEE,
        )
        return PayrollFactory.payroll_run_component(
            payroll_run_employee=row,
            component=pf_component,
            amount="180.00",
            sequence=200,
        )

    def test_fnf_lifecycle_api_and_payloads(self):
        calculate_response = self.client.post(
            "/api/payroll/fnf/calculate/",
            {
                "contract_id": str(self.setup["hrms_contract"].id),
                "separation_date": "2025-04-30",
                "inputs": {"bonus_amount": "100.00"},
            },
            format="json",
        )
        self.assertEqual(calculate_response.status_code, 201, calculate_response.content)
        settlement_id = calculate_response.json()["data"]["id"]

        list_response = self.client.get(f"/api/payroll/fnf/?entity={self.entity_id}")
        self.assertEqual(list_response.status_code, 200, list_response.content)
        payload = list_response.json()
        results = payload.get("results", payload) if isinstance(payload, dict) else payload
        self.assertEqual(len(results), 1)

        detail_response = self.client.get(f"/api/payroll/fnf/{settlement_id}/?entity={self.entity_id}")
        self.assertEqual(detail_response.status_code, 200, detail_response.content)
        detail_payload = detail_response.json()
        self.assertIn("grouped_components", detail_payload)
        self.assertIn("components", detail_payload)

        recalc_response = self.client.post(
            f"/api/payroll/fnf/{settlement_id}/recalculate/?entity={self.entity_id}",
            {"inputs": {"bonus_amount": "250.00"}},
            format="json",
        )
        self.assertEqual(recalc_response.status_code, 200, recalc_response.content)
        self.assertEqual(recalc_response.json()["data"]["status"], FnFSettlement.Status.CALCULATED)

        approve_response = self.client.post(
            f"/api/payroll/fnf/{settlement_id}/approve/?entity={self.entity_id}",
            {"note": "Looks good"},
            format="json",
        )
        self.assertEqual(approve_response.status_code, 200, approve_response.content)

        post_response = self.client.post(
            f"/api/payroll/fnf/{settlement_id}/post/?entity={self.entity_id}",
            {"post_reference": "FNF-POST-001"},
            format="json",
        )
        self.assertEqual(post_response.status_code, 200, post_response.content)

        paid_response = self.client.post(
            f"/api/payroll/fnf/{settlement_id}/paid/?entity={self.entity_id}",
            {"payment_reference": "FNF-PAY-001"},
            format="json",
        )
        self.assertEqual(paid_response.status_code, 200, paid_response.content)
        self.assertEqual(paid_response.json()["data"]["payment_status"], "paid")

        second = PayrollFnFEngine.calculate_fnf(
            self.setup["hrms_contract"].id,
            separation_date=date(2025, 4, 15),
            inputs={"payable_days": "15.00"},
        )
        cancel_response = self.client.post(
            f"/api/payroll/fnf/{second.id}/cancel/?entity={self.entity_id}",
            {"note": "Cancelled by admin"},
            format="json",
        )
        self.assertEqual(cancel_response.status_code, 200, cancel_response.content)
        self.assertEqual(cancel_response.json()["data"]["status"], FnFSettlement.Status.CANCELLED)

    def test_ess_payslip_list_and_detail_payloads(self):
        run, row, payslip = self._create_run_with_payslip()
        statutory_row = self._add_statutory_component_row(row)
        statutory_row.calculation_basis_snapshot = {
            "semantic_code": PayrollComponent.SemanticCode.PF_EMPLOYEE,
            "attendance_trace": {"method": "CALENDAR_DAYS"},
        }
        statutory_row.metadata = {
            "calculation_trace": {
                "calculation_mode": "STATUTORY_ENGINE",
                "final_amount": "180.00",
            }
        }
        statutory_row.save(update_fields=["calculation_basis_snapshot", "metadata", "updated_at"])
        payslip = PayslipService.build_for_run_employee(row)

        list_response = self.client.get("/api/payroll/ess/payslips/")
        self.assertEqual(list_response.status_code, 200, list_response.content)
        payload = list_response.json()
        results = payload.get("results", payload) if isinstance(payload, dict) else payload
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["payslip_number"], payslip.payslip_number)

        detail_response = self.client.get(f"/api/payroll/ess/payslips/{payslip.id}/")
        self.assertEqual(detail_response.status_code, 200, detail_response.content)
        detail_payload = detail_response.json()
        self.assertIn("grouped_components", detail_payload)
        self.assertIn("statutory", detail_payload["grouped_components"])
        self.assertGreaterEqual(len(detail_payload["component_trace"]), 1)

    def test_ess_tax_and_placeholder_payloads(self):
        declaration = ContractTaxDeclaration.objects.create(
            entity=self.setup["entity"],
            contract_payroll_profile=self.setup["contract_profile"],
            financial_year=self.setup["entityfinid"],
            tax_regime=ContractTaxDeclaration.TaxRegime.NEW,
            declaration_status=ContractTaxDeclaration.DeclarationStatus.SUBMITTED,
            declared_annual_income=Decimal("500000.00"),
            is_active=True,
        )
        ContractTaxDeclarationLine.objects.create(
            declaration=declaration,
            section_code=ContractTaxDeclarationLine.SectionCode.SECTION_80C,
            description="PF",
            declared_amount=Decimal("120000.00"),
            approved_amount=Decimal("100000.00"),
            is_active=True,
        )

        tax_response = self.client.get("/api/payroll/ess/tax-declaration-summary/")
        self.assertEqual(tax_response.status_code, 200, tax_response.content)
        self.assertEqual(tax_response.json()["status"], "available")
        self.assertEqual(tax_response.json()["data"]["tax_regime"], ContractTaxDeclaration.TaxRegime.NEW)

        reimbursement_response = self.client.get("/api/payroll/ess/reimbursements/placeholder/")
        self.assertEqual(reimbursement_response.status_code, 200, reimbursement_response.content)
        self.assertFalse(reimbursement_response.json()["enabled"])

        attendance_response = self.client.get("/api/payroll/ess/attendance-summary/placeholder/")
        self.assertEqual(attendance_response.status_code, 200, attendance_response.content)
        self.assertEqual(attendance_response.json()["status"], "available")

    def test_pending_workflow_payloads(self):
        settlement = PayrollFnFEngine.calculate_fnf(
            self.setup["hrms_contract"].id,
            separation_date=date(2025, 4, 30),
            inputs={},
        )
        fnf_response = self.client.get(f"/api/payroll/workflows/pending-fnf-approvals/?entity={self.entity_id}")
        self.assertEqual(fnf_response.status_code, 200, fnf_response.content)
        fnf_payload = fnf_response.json()
        fnf_results = fnf_payload.get("results", fnf_payload) if isinstance(fnf_payload, dict) else fnf_payload
        self.assertEqual(len(fnf_results), 1)
        self.assertEqual(fnf_results[0]["id"], settlement.id)

        run_result = PayrollRunService.create_run(
            entity_id=self.entity_id,
            entityfinid_id=self.entityfinid_id,
            subentity_id=self.subentity_id,
            payroll_period_id=self.setup["period"].id,
            run_type=PayrollRun.RunType.REGULAR,
            posting_date=self.setup["period"].period_end,
            payout_date=self.setup["period"].payout_date,
            created_by_id=self.user.id,
        )
        run = PayrollRunService.calculate_run(run_result.run).run
        PayrollRunService.submit_run(run, submitted_by_id=self.user.id, note="submit", reason_code="READY")

        pending_response = self.client.get(f"/api/payroll/workflows/pending-payroll-approvals/?entity={self.entity_id}")
        self.assertEqual(pending_response.status_code, 200, pending_response.content)
        pending_payload = pending_response.json()
        pending_results = pending_payload.get("results", pending_payload) if isinstance(pending_payload, dict) else pending_payload
        self.assertEqual(len(pending_results), 1)
        self.assertEqual(pending_results[0]["id"], run.id)

    def test_readiness_exceptions_and_profile_completeness_payloads(self):
        blocked_contract = PayrollFactory.hrms_contract(entity=self.setup["entity"], subentity=self.setup["subentity"])
        ContractPayrollProfileService.create_or_update_profile(
            {
                "entity": self.setup["entity"],
                "hrms_contract": blocked_contract,
                "pay_frequency": "MONTHLY",
                "payroll_status": "ACTIVE",
                "payroll_start_date": blocked_contract.payroll_effective_from,
                "is_active": True,
            }
        )

        readiness_response = self.client.get(
            f"/api/payroll/runtime/readiness-detail/?entity={self.entity_id}&contract={blocked_contract.id}&payroll_period={self.setup['period'].id}"
        )
        self.assertEqual(readiness_response.status_code, 200, readiness_response.content)
        self.assertEqual(readiness_response.json()["summary"]["readiness_status"], "BLOCKED")

        exceptions_response = self.client.get(
            f"/api/payroll/workflows/exceptions/?entity={self.entity_id}&payroll_period={self.setup['period'].id}"
        )
        self.assertEqual(exceptions_response.status_code, 200, exceptions_response.content)
        self.assertGreaterEqual(exceptions_response.json()["blocked_count"], 1)

        completeness_response = self.client.get(
            f"/api/payroll/workflows/profile-completeness/?entity={self.entity_id}&payroll_period={self.setup['period'].id}"
        )
        self.assertEqual(completeness_response.status_code, 200, completeness_response.content)
        self.assertGreaterEqual(len(completeness_response.json()["results"]), 1)

    def test_component_statutory_and_attendance_trace_payloads(self):
        run, row, _payslip = self._create_run_with_payslip()
        basic_component = row.components.select_related("component").first()
        statutory_row = self._add_statutory_component_row(row)
        statutory_row.calculation_basis_snapshot = {
            "semantic_code": PayrollComponent.SemanticCode.PF_EMPLOYEE,
            "attendance_trace": {"proration_factor": "1.00"},
        }
        statutory_row.metadata = {
            "calculation_trace": {
                "calculation_mode": "STATUTORY_ENGINE",
                "final_amount": "180.00",
            }
        }
        statutory_row.save(update_fields=["calculation_basis_snapshot", "metadata", "updated_at"])

        component_trace_response = self.client.get(
            f"/api/payroll/runs/{run.id}/components/{basic_component.id}/trace/?entity={self.entity_id}"
        )
        self.assertEqual(component_trace_response.status_code, 200, component_trace_response.content)
        self.assertIn("component_trace", component_trace_response.json())

        statutory_trace_response = self.client.get(
            f"/api/payroll/runs/{run.id}/employees/{row.id}/statutory-trace/?entity={self.entity_id}"
        )
        self.assertEqual(statutory_trace_response.status_code, 200, statutory_trace_response.content)
        self.assertEqual(len(statutory_trace_response.json()["statutory_components"]), 1)

        attendance_trace_response = self.client.get(
            f"/api/payroll/runs/{run.id}/employees/{row.id}/attendance-trace/?entity={self.entity_id}"
        )
        self.assertEqual(attendance_trace_response.status_code, 200, attendance_trace_response.content)
        self.assertIn("attendance_execution", attendance_trace_response.json())
