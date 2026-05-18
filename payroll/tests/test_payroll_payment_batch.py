from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from financial.models import AccountBankDetails
from payroll.models import PayrollPaymentBatch, PayrollPaymentBatchLine, PayrollRun
from payroll.services import PayrollPaymentBatchService
from payroll.tests.factories import PayrollFactory


class PayrollPaymentBatchServiceTests(TestCase):
    def setUp(self):
        self.setup = PayrollFactory.full_payroll_setup()
        self.contract_profile = self.setup["contract_profile"]
        self.bank_account = self.contract_profile.bank_account
        self.run = PayrollFactory.payroll_run(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            payroll_period=self.setup["period"],
            status=PayrollRun.Status.APPROVED,
            run_number="RUN-APR-001",
        )
        self.employee_row = PayrollFactory.payroll_run_employee(
            payroll_run=self.run,
            employee_profile=self.setup["profile"],
            salary_structure=self.setup["structure"],
            salary_structure_version=self.setup["version"],
            ledger_policy_version=self.setup["ledger_policy"],
            contract_payroll_profile=self.contract_profile,
            payable_amount=Decimal("1250.00"),
        )
        AccountBankDetails.objects.create(
            account=self.bank_account,
            entity=self.setup["entity"],
            createdby=self.setup["user"],
            bankname="Axis Bank",
            banKAcno="123456789012",
            ifsc="HDFC0001234",
            branch="Main Branch",
            isprimary=True,
            isactive=True,
        )

    def test_create_batch_from_approved_payroll_run_uses_payroll_run_employee_snapshot(self):
        batch = PayrollPaymentBatchService.create_from_payroll_run(run=self.run, user_id=self.setup["user"].id)

        self.assertEqual(batch.source_type, PayrollPaymentBatch.SourceType.PAYROLL_RUN)
        self.assertEqual(batch.status, PayrollPaymentBatch.Status.DRAFT)
        self.assertEqual(batch.total_lines, 1)
        self.assertEqual(batch.total_amount, Decimal("1250.00"))
        line = batch.lines.get()
        self.assertEqual(line.payroll_run_employee_id, self.employee_row.id)
        self.assertEqual(line.employee_code, self.contract_profile.employee_code)
        self.assertEqual(line.amount, Decimal("1250.00"))

    def test_validation_catches_missing_bank_account(self):
        self.contract_profile.bank_account = None
        self.contract_profile.bank_account_details = {}
        self.contract_profile.save(update_fields=["bank_account", "bank_account_details", "updated_at"])

        batch = PayrollPaymentBatchService.create_from_payroll_run(run=self.run, user_id=self.setup["user"].id)
        batch = PayrollPaymentBatchService.validate_batch(batch=batch, user_id=self.setup["user"].id)

        line = batch.lines.get()
        self.assertEqual(batch.status, PayrollPaymentBatch.Status.VALIDATED)
        self.assertEqual(line.line_status, PayrollPaymentBatchLine.LineStatus.INVALID)
        self.assertIn("Missing bank account.", line.validation_errors_json)

    def test_create_batch_excludes_zero_and_negative_net_pay_by_default(self):
        self.employee_row.payable_amount = Decimal("0.00")
        self.employee_row.save(update_fields=["payable_amount", "updated_at"])

        batch = PayrollPaymentBatchService.create_from_payroll_run(run=self.run, user_id=self.setup["user"].id)

        self.assertEqual(batch.total_lines, 0)
        self.assertEqual(batch.skipped_line_count, 1)
        self.assertEqual(batch.total_amount, Decimal("0.00"))

    def test_create_batch_can_keep_non_positive_rows_when_enabled(self):
        self.employee_row.payable_amount = Decimal("-25.00")
        self.employee_row.save(update_fields=["payable_amount", "updated_at"])

        batch = PayrollPaymentBatchService.create_from_payroll_run(
            run=self.run,
            user_id=self.setup["user"].id,
            allow_non_positive_amounts=True,
        )

        self.assertEqual(batch.total_lines, 1)
        self.assertEqual(batch.skipped_line_count, 0)
        self.assertEqual(batch.lines.get().amount, Decimal("-25.00"))

    def test_export_generates_csv_headers_and_marks_run_handed_off(self):
        self.run.status = PayrollRun.Status.POSTED
        self.run.save(update_fields=["status", "updated_at"])
        batch = PayrollPaymentBatchService.create_from_payroll_run(run=self.run, user_id=self.setup["user"].id)
        batch = PayrollPaymentBatchService.validate_batch(batch=batch, user_id=self.setup["user"].id)
        batch = PayrollPaymentBatchService.approve_batch(batch=batch, user_id=self.setup["user"].id)

        result = PayrollPaymentBatchService.export_batch(batch=batch, user_id=self.setup["user"].id)

        header = result.file_content.splitlines()[0]
        self.assertEqual(
            header,
            "employee_code,employee_name,account_holder_name,account_number,ifsc_code,amount,narration",
        )
        batch.refresh_from_db()
        self.run.refresh_from_db()
        self.assertEqual(batch.status, PayrollPaymentBatch.Status.EXPORTED)
        self.assertEqual(self.run.payment_status, PayrollRun.PaymentStatus.HANDED_OFF)
        self.assertEqual(self.run.payment_batch_ref, batch.batch_number)

    def test_lifecycle_transitions_update_final_payment_status(self):
        self.run.status = PayrollRun.Status.POSTED
        self.run.save(update_fields=["status", "updated_at"])
        batch = PayrollPaymentBatchService.create_from_payroll_run(run=self.run, user_id=self.setup["user"].id)
        batch = PayrollPaymentBatchService.validate_batch(batch=batch, user_id=self.setup["user"].id)
        batch = PayrollPaymentBatchService.approve_batch(batch=batch, user_id=self.setup["user"].id)
        batch = PayrollPaymentBatchService.export_batch(batch=batch, user_id=self.setup["user"].id).batch
        batch = PayrollPaymentBatchService.mark_paid(
            batch=batch,
            user_id=self.setup["user"].id,
            payment_reference="UTR-001",
        )

        batch.refresh_from_db()
        self.run.refresh_from_db()
        self.assertEqual(batch.status, PayrollPaymentBatch.Status.PAID)
        self.assertEqual(batch.payment_reference, "UTR-001")
        self.assertEqual(self.run.payment_status, PayrollRun.PaymentStatus.DISBURSED)
        self.assertTrue(batch.status_logs.filter(new_status=PayrollPaymentBatch.Status.PAID).exists())

    def test_cancelled_batch_cannot_be_exported(self):
        batch = PayrollPaymentBatchService.create_from_payroll_run(run=self.run, user_id=self.setup["user"].id)
        batch = PayrollPaymentBatchService.cancel_batch(
            batch=batch,
            user_id=self.setup["user"].id,
            cancellation_reason="Superseded",
        )

        with self.assertRaisesMessage(ValueError, "Only approved payment batches can be exported."):
            PayrollPaymentBatchService.export_batch(batch=batch, user_id=self.setup["user"].id)
