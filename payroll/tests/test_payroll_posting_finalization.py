from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from payroll.models import FnFSettlement, FnFSettlementComponent, PayrollComponent
from payroll.services import PayrollPostingService, PayrollRunService
from payroll.tests.factories import PayrollFactory
from posting.models import EntityStaticAccountMap, StaticAccount


class PayrollPostingFinalizationTests(TestCase):
    def setUp(self):
        self.setup = PayrollFactory.full_payroll_setup()

    def _approve_calculated_run(self):
        run = PayrollRunService.create_run(
            entity_id=self.setup["entity"].id,
            entityfinid_id=self.setup["entityfinid"].id,
            subentity_id=self.setup["subentity"].id,
            payroll_period_id=self.setup["period"].id,
            run_type="REGULAR",
            posting_date=self.setup["period"].period_end,
            payout_date=self.setup["period"].payout_date,
            created_by_id=self.setup["user"].id,
        ).run
        PayrollRunService.calculate_run(run)
        PayrollRunService.submit_run(run, submitted_by_id=self.setup["user"].id)
        PayrollRunService.approve_run(run, approved_by_id=self.setup["user"].id)
        run.refresh_from_db()
        return run

    def _map_static(self, code: str, mapped_account):
        static, _ = StaticAccount.objects.update_or_create(
            code=code,
            defaults={
                "name": code.replace("_", " ").title(),
                "group": "OTHER",
                "is_required": False,
                "is_active": True,
            },
        )
        return EntityStaticAccountMap.objects.create(
            entity=self.setup["entity"],
            sub_entity=self.setup["subentity"],
            static_account=static,
            account=mapped_account,
            ledger=mapped_account.ledger,
            is_active=True,
        )

    def test_preview_payroll_journal_balances(self):
        run = self._approve_calculated_run()

        preview = PayrollPostingService.preview_run(run)

        self.assertTrue(preview["validation"]["is_valid"])
        self.assertEqual(preview["totals"]["debit_total"], preview["totals"]["credit_total"])
        categories = {row["category"] for row in preview["journal_rows"]}
        self.assertIn("expense", categories)
        self.assertIn("salary_payable", categories)

    def test_missing_component_mapping_blocks_posting(self):
        run = self._approve_calculated_run()
        component_row = run.employee_runs.prefetch_related("components__component_posting_version").first().components.first()
        component_row.component_posting_version.expense_account = None
        component_row.component_posting_version.save(update_fields=["expense_account"])

        preview = PayrollPostingService.preview_run(run)

        self.assertFalse(preview["validation"]["is_valid"])
        self.assertTrue(
            any(issue["code"] == "MISSING_COMPONENT_EXPENSE_MAPPING" for issue in preview["validation"]["issues"])
        )
        with self.assertRaises(ValueError):
            PayrollPostingService.post_run(run, user_id=self.setup["user"].id)

    def test_statutory_payable_line_uses_static_mapping(self):
        pt_payable_account = PayrollFactory.gl_account(
            entity=self.setup["entity"],
            user=self.setup["user"],
            accounthead=self.setup["accounthead"],
            accountname="PT Payable",
        )
        self._map_static("PAYROLL_PT_PAYABLE", pt_payable_account)

        pt_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="PROFESSIONAL_TAX",
            component_type=PayrollComponent.ComponentType.DEDUCTION,
            posting_behavior=PayrollComponent.PostingBehavior.EMPLOYEE_LIABILITY,
            semantic_code=PayrollComponent.SemanticCode.PT,
        )
        pt_posting = PayrollFactory.component_posting(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            component=pt_component,
            expense_account=None,
            liability_account=None,
            payable_account=None,
        )
        run = PayrollFactory.payroll_run(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            payroll_period=self.setup["period"],
            status="APPROVED",
            is_immutable=True,
            ledger_policy_version=self.setup["ledger_policy"],
        )
        row = PayrollFactory.payroll_run_employee(
            payroll_run=run,
            contract_payroll_profile=self.setup["contract_profile"],
            salary_structure=self.setup["structure"],
            salary_structure_version=self.setup["version"],
            ledger_policy_version=self.setup["ledger_policy"],
            gross_amount=Decimal("1000.00"),
            deduction_amount=Decimal("200.00"),
            employer_contribution_amount=Decimal("0.00"),
            reimbursement_amount=Decimal("0.00"),
            payable_amount=Decimal("800.00"),
        )
        PayrollFactory.payroll_run_component(
            payroll_run_employee=row,
            component=self.setup["component"],
            component_posting_version=self.setup["component_posting"],
            source_structure_line=self.setup["line"],
            amount="1000.00",
            sequence=100,
        )
        PayrollFactory.payroll_run_component(
            payroll_run_employee=row,
            component=pt_component,
            component_posting_version=pt_posting,
            amount="200.00",
            sequence=200,
        )

        preview = PayrollPostingService.preview_run(run)

        self.assertTrue(preview["validation"]["is_valid"])
        self.assertTrue(
            any(
                row["category"] == "liability" and row["account_id"] == pt_payable_account.id
                for row in preview["journal_rows"]
            )
        )

    def test_fnf_posting_preview_balances_and_uses_fnf_payable(self):
        self._map_static("PAYROLL_FNF_PAYABLE", self.setup["payable_account"])

        settlement = FnFSettlement.objects.create(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            hrms_contract=self.setup["hrms_contract"],
            contract_payroll_profile=self.setup["contract_profile"],
            salary_structure=self.setup["structure"],
            salary_structure_version=self.setup["version"],
            payroll_period=self.setup["period"],
            settlement_number="FNF-001",
            separation_date=self.setup["period"].period_end,
            last_working_day=self.setup["period"].period_end,
            status=FnFSettlement.Status.APPROVED,
        )
        FnFSettlementComponent.objects.create(
            settlement=settlement,
            component=self.setup["component"],
            source_type=FnFSettlementComponent.SourceType.SALARY_LINE,
            component_code=self.setup["component"].code,
            component_name=self.setup["component"].name,
            component_type=self.setup["component"].component_type,
            posting_behavior=self.setup["component"].posting_behavior,
            sequence=100,
            amount=Decimal("500.00"),
        )

        preview = PayrollPostingService.preview_fnf(settlement)

        self.assertTrue(preview["validation"]["is_valid"])
        self.assertEqual(preview["totals"]["debit_total"], preview["totals"]["credit_total"])
        self.assertTrue(any(row["category"] == "fnf_payable" for row in preview["journal_rows"]))

    def test_posting_does_not_recalculate_payroll(self):
        run = self._approve_calculated_run()

        with patch.object(PayrollRunService, "calculate_run", side_effect=AssertionError("recalculation should not happen")):
            PayrollPostingService.preview_run(run)
            with patch("posting.services.posting_service.PostingService._pg_advisory_lock", return_value=None):
                PayrollRunService.post_run(run, posted_by_id=self.setup["user"].id)
