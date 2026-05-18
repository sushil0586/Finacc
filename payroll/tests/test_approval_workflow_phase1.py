from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from entity.models import ApprovalActionLog, ApprovalRequest
from financial.models import AccountBankDetails
from payroll.models import ContractTaxDeclaration, FnFSettlement, PayrollPaymentBatch, PayrollRun
from payroll.services import ContractTaxDeclarationService, PayrollPaymentBatchService
from payroll.services.payroll_fnf_engine import PayrollFnFEngine
from payroll.services.payroll_run_service import PayrollRunService
from payroll.tests.factories import PayrollFactory


class ApprovalWorkflowPhase1Tests(TestCase):
    def setUp(self):
        self.setup = PayrollFactory.full_payroll_setup()
        self.user = self.setup["user"]
        self.contract_profile = self.setup["contract_profile"]
        self.contract = self.setup["hrms_contract"]
        AccountBankDetails.objects.create(
            account=self.contract_profile.bank_account,
            entity=self.setup["entity"],
            createdby=self.user,
            bankname="Axis Bank",
            banKAcno="123456789012",
            ifsc="UTIB0000001",
            branch="Main Branch",
            isprimary=True,
            isactive=True,
        )

    def test_payroll_posting_requires_approval_clearance(self):
        run = PayrollFactory.payroll_run(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            payroll_period=self.setup["period"],
            status=PayrollRun.Status.APPROVED,
            is_immutable=True,
            run_number="RUN-PH1-001",
            approval_status=PayrollRun.ApprovalStatus.DRAFT,
        )

        with self.assertRaisesMessage(ValueError, "Payroll run must be approval-cleared before posting."):
            PayrollRunService.post_run(run, posted_by_id=self.user.id)

    def test_payroll_approval_creates_audit_request_and_locked_status(self):
        run = PayrollFactory.payroll_run(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            payroll_period=self.setup["period"],
            status=PayrollRun.Status.CALCULATED,
            run_number="RUN-PH1-002",
        )
        PayrollFactory.payroll_run_employee(
            payroll_run=run,
            employee_profile=self.setup["profile"],
            salary_structure=self.setup["structure"],
            salary_structure_version=self.setup["version"],
            ledger_policy_version=self.setup["ledger_policy"],
            contract_payroll_profile=self.contract_profile,
        )

        result = PayrollRunService.approve_run(run, approved_by_id=self.user.id, note="approval-hardening")

        self.assertEqual(result.run.status, PayrollRun.Status.APPROVED)
        self.assertEqual(result.run.approval_status, PayrollRun.ApprovalStatus.LOCKED)
        request = ApprovalRequest.objects.get(workflow_key="payroll_run", object_id=str(run.id))
        self.assertEqual(request.status, ApprovalRequest.Status.LOCKED)
        actions = list(
            ApprovalActionLog.objects.filter(approval_request=request).order_by("id").values_list("action", flat=True)
        )
        self.assertEqual(actions, ["SUBMITTED", "ROUTED", "APPROVED", "LOCKED"])

        with patch(
            "payroll.services.payroll_run_service.PayrollPostingService.post_run",
            return_value=SimpleNamespace(id=101, voucher_no="JV-101"),
        ):
            posted = PayrollRunService.post_run(run, posted_by_id=self.user.id)
        self.assertEqual(posted.run.status, PayrollRun.Status.POSTED)

    def test_payment_batch_approval_gates_export_and_creates_audit_log(self):
        run = PayrollFactory.payroll_run(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            payroll_period=self.setup["period"],
            status=PayrollRun.Status.POSTED,
            run_number="RUN-PH1-003",
        )
        PayrollFactory.payroll_run_employee(
            payroll_run=run,
            employee_profile=self.setup["profile"],
            salary_structure=self.setup["structure"],
            salary_structure_version=self.setup["version"],
            ledger_policy_version=self.setup["ledger_policy"],
            contract_payroll_profile=self.contract_profile,
            payable_amount=Decimal("1250.00"),
        )
        batch = PayrollPaymentBatchService.create_from_payroll_run(run=run, user_id=self.user.id)
        batch = PayrollPaymentBatchService.validate_batch(batch=batch, user_id=self.user.id)
        batch.status = PayrollPaymentBatch.Status.APPROVED
        batch.save(update_fields=["status", "updated_at"])

        with self.assertRaisesMessage(ValueError, "Payment batch must be approval-cleared before export."):
            PayrollPaymentBatchService.export_batch(batch=batch, user_id=self.user.id)

        batch.status = PayrollPaymentBatch.Status.VALIDATED
        batch.save(update_fields=["status", "updated_at"])
        batch = PayrollPaymentBatchService.approve_batch(batch=batch, user_id=self.user.id, comment="ready to export")

        self.assertEqual(batch.approval_status, PayrollPaymentBatch.ApprovalStatus.APPROVED)
        request = ApprovalRequest.objects.get(workflow_key="payroll_payment_batch", object_id=str(batch.id))
        self.assertEqual(request.status, ApprovalRequest.Status.APPROVED)
        self.assertTrue(
            ApprovalActionLog.objects.filter(
                approval_request=request,
                action=ApprovalActionLog.Action.APPROVED,
            ).exists()
        )

    def test_fnf_payment_requires_approval_clearance(self):
        settlement = FnFSettlement.objects.create(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            hrms_contract=self.contract,
            contract_payroll_profile=self.contract_profile,
            settlement_number="FNF-PH1-001",
            separation_date=date(2025, 4, 30),
            last_working_day=date(2025, 4, 30),
            settlement_date=date(2025, 4, 30),
            status=FnFSettlement.Status.APPROVED,
            approval_status=FnFSettlement.ApprovalStatus.DRAFT,
            net_payable_amount=Decimal("5000.00"),
        )

        with self.assertRaisesMessage(ValueError, "FnF settlement must be approval-cleared before payment"):
            PayrollFnFEngine.mark_paid(settlement.id, payment_reference="UTR-FNF-1", user_id=self.user.id)

    def test_rejected_tax_declaration_is_excluded_from_preferred_resolution(self):
        rejected = PayrollFactory.contract_tax_declaration(
            entity=self.setup["entity"],
            contract_payroll_profile=self.contract_profile,
            financial_year=self.setup["entityfinid"],
            declaration_status=ContractTaxDeclaration.DeclarationStatus.REJECTED,
            approval_status=ContractTaxDeclaration.ApprovalStatus.REJECTED,
            rejected_at=timezone.now(),
        )

        preferred = ContractTaxDeclarationService.resolve_preferred_declaration(
            contract_payroll_profile=self.contract_profile,
            declaration_date=self.setup["period"].period_end,
            financial_year_id=self.setup["entityfinid"].id,
        )

        self.assertIsNone(preferred)
        self.assertEqual(rejected.approval_status, ContractTaxDeclaration.ApprovalStatus.REJECTED)
