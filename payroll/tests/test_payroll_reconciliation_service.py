from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from payroll.services.payroll_reconciliation_service import PayrollReconciliationService
from payroll.tests.factories import PayrollFactory


class PayrollReconciliationServiceTests(TestCase):
    def setUp(self):
        self.setup = PayrollFactory.full_payroll_setup()
        self.run = PayrollFactory.payroll_run(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            payroll_period=self.setup["period"],
            employee_count=1,
            gross_amount=Decimal("1000.00"),
            deduction_amount=Decimal("100.00"),
            net_pay_amount=Decimal("900.00"),
        )
        run_employee = PayrollFactory.payroll_run_employee(
            payroll_run=self.run,
            employee_profile=self.setup["profile"],
            salary_structure=self.setup["structure"],
            salary_structure_version=self.setup["version"],
            ledger_policy_version=self.setup["ledger_policy"],
        )
        PayrollFactory.payroll_run_component(
            payroll_run_employee=run_employee,
            component=self.setup["component"],
            component_posting_version=self.setup["component_posting"],
            source_structure_line=self.setup["line"],
            amount="1000.00",
        )

    def test_reconciliation_passes_for_matching_snapshot(self):
        legacy = {
            "employee_count": 1,
            "gross_amount": "1000.00",
            "deduction_amount": "100.00",
            "net_pay_amount": "900.00",
            "component_totals": {self.setup["component"].code: "1000.00"},
        }
        result = PayrollReconciliationService.reconcile_legacy_snapshot(payroll_run=self.run, legacy_snapshot=legacy)
        self.assertTrue(result.passed)

    def test_reconciliation_fails_outside_tolerance(self):
        legacy = {
            "employee_count": 1,
            "gross_amount": "1100.00",
            "deduction_amount": "100.00",
            "net_pay_amount": "1000.00",
            "component_totals": {self.setup["component"].code: "1100.00"},
        }
        result = PayrollReconciliationService.reconcile_legacy_snapshot(payroll_run=self.run, legacy_snapshot=legacy)
        self.assertFalse(result.passed)
        self.assertEqual(result.blocks[0].status, "fail")

    def test_payslip_spotcheck_payload_contains_rows(self):
        payload = PayrollReconciliationService.build_payslip_spotcheck_payload(run=self.run)
        self.assertEqual(payload["sample_size"], 1)
        self.assertEqual(payload["rows"][0]["employee_code"], self.setup["profile"].employee_code)
