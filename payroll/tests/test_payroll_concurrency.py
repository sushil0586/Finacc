from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from financial.models import AccountBankDetails
from payroll.models import PayrollPaymentBatch, PayrollRun, PayrollRunActionLog
from payroll.services import PayrollPaymentBatchService
from payroll.services.payroll_reversal_service import PayrollReversalService
from payroll.services.payroll_run_hardening_service import PayrollRunHardeningService
from payroll.services.payroll_run_service import PayrollRunService
from payroll.tests.factories import PayrollFactory
from posting.models import PostingBatch, TxnType


@skipUnless(connection.vendor == "postgresql", "Payroll concurrency certification requires PostgreSQL row locking.")
class PayrollPostgreSQLConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.setup = PayrollFactory.full_payroll_setup()

    def _run_concurrently(self, callback):
        barrier = Barrier(2)

        def worker():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return callback()
            except Exception as exc:  # The losing transition is an asserted result.
                return exc
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            return list(executor.map(lambda _: worker(), range(2)))

    def _create_run(self) -> PayrollRun:
        return PayrollRunService.create_run(
            entity_id=self.setup["entity"].id,
            entityfinid_id=self.setup["entityfinid"].id,
            subentity_id=self.setup["subentity"].id,
            payroll_period_id=self.setup["period"].id,
            run_type=PayrollRun.RunType.REGULAR,
            posting_date=self.setup["period"].period_end,
            payout_date=self.setup["period"].payout_date,
            created_by_id=self.setup["user"].id,
        ).run

    def _approve_run(self, run: PayrollRun) -> PayrollRun:
        PayrollRunService.calculate_run(run)
        PayrollRunService.submit_run(run, submitted_by_id=self.setup["user"].id, note="submit")
        return PayrollRunService.approve_run(
            run,
            approved_by_id=self.setup["user"].id,
            note="approve",
        ).run

    def test_simultaneous_calculation_creates_one_employee_snapshot(self):
        run = self._create_run()

        results = self._run_concurrently(
            lambda: PayrollRunService.calculate_run(PayrollRun.objects.get(pk=run.pk))
        )

        successes = [result for result in results if not isinstance(result, Exception)]
        failures = [result for result in results if isinstance(result, Exception)]
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 1)
        self.assertIn("already calculated", str(failures[0]))
        run.refresh_from_db()
        self.assertEqual(run.status, PayrollRun.Status.CALCULATED)
        self.assertEqual(run.employee_runs.count(), 1)
        self.assertEqual(
            run.action_logs.filter(action=PayrollRunActionLog.Action.CALCULATED).count(),
            1,
        )

    def test_simultaneous_posting_creates_one_posting_revision(self):
        run = self._approve_run(self._create_run())

        results = self._run_concurrently(
            lambda: PayrollRunService.post_run(
                PayrollRun.objects.get(pk=run.pk),
                posted_by_id=self.setup["user"].id,
            )
        )

        successes = [result for result in results if not isinstance(result, Exception)]
        failures = [result for result in results if isinstance(result, Exception)]
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 1)
        self.assertIn("Only approved payroll runs can be posted", str(failures[0]))
        run.refresh_from_db()
        self.assertEqual(run.status, PayrollRun.Status.POSTED)
        self.assertIsNotNone(run.posted_entry_id)
        self.assertEqual(
            PostingBatch.objects.filter(txn_type=TxnType.PAYROLL, txn_id=run.id).count(),
            1,
        )
        self.assertEqual(
            run.action_logs.filter(action=PayrollRunActionLog.Action.POSTED).count(),
            1,
        )

    def test_simultaneous_payment_batch_creation_keeps_one_active_batch(self):
        run = self._approve_run(self._create_run())

        results = self._run_concurrently(
            lambda: PayrollPaymentBatchService.create_from_payroll_run(
                run=PayrollRun.objects.get(pk=run.pk),
                user_id=self.setup["user"].id,
            )
        )

        successes = [result for result in results if not isinstance(result, Exception)]
        failures = [result for result in results if isinstance(result, Exception)]
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 1)
        self.assertIn("active payment batch already exists", str(failures[0]))
        self.assertEqual(
            PayrollPaymentBatch.objects.filter(payroll_run=run).count(),
            1,
        )

    def test_simultaneous_payment_confirmation_records_one_disbursement(self):
        AccountBankDetails.objects.create(
            account=self.setup["contract_profile"].bank_account,
            entity=self.setup["entity"],
            createdby=self.setup["user"],
            bankname="Concurrency Test Bank",
            banKAcno="123456789012",
            ifsc="HDFC0001234",
            branch="Test Branch",
            isprimary=True,
            isactive=True,
        )
        run = PayrollRunService.post_run(
            self._approve_run(self._create_run()),
            posted_by_id=self.setup["user"].id,
        ).run
        batch = PayrollPaymentBatchService.create_from_payroll_run(
            run=run,
            user_id=self.setup["user"].id,
        )
        batch = PayrollPaymentBatchService.validate_batch(
            batch=batch,
            user_id=self.setup["user"].id,
        )
        batch = PayrollPaymentBatchService.approve_batch(
            batch=batch,
            user_id=self.setup["user"].id,
        )
        batch = PayrollPaymentBatchService.export_batch(
            batch=batch,
            user_id=self.setup["user"].id,
        ).batch

        results = self._run_concurrently(
            lambda: PayrollPaymentBatchService.mark_paid(
                batch=PayrollPaymentBatch.objects.get(pk=batch.pk),
                user_id=self.setup["user"].id,
                payment_reference="UTR-CONCURRENT-001",
            )
        )

        successes = [result for result in results if not isinstance(result, Exception)]
        failures = [result for result in results if isinstance(result, Exception)]
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 1)
        self.assertIn("can be marked paid", str(failures[0]))
        batch.refresh_from_db()
        run.refresh_from_db()
        self.assertEqual(batch.status, PayrollPaymentBatch.Status.PAID)
        self.assertEqual(batch.payment_reference, "UTR-CONCURRENT-001")
        self.assertEqual(run.payment_status, PayrollRun.PaymentStatus.DISBURSED)
        self.assertEqual(
            batch.status_logs.filter(new_status=PayrollPaymentBatch.Status.PAID).count(),
            1,
        )
        self.assertEqual(
            run.action_logs.filter(action=PayrollRunActionLog.Action.DISBURSED).count(),
            1,
        )

    def test_simultaneous_reversal_creates_one_reversal_and_one_posting(self):
        run = PayrollRunService.post_run(
            self._approve_run(self._create_run()),
            posted_by_id=self.setup["user"].id,
        ).run

        results = self._run_concurrently(
            lambda: PayrollReversalService.reverse_run(
                PayrollRun.objects.get(pk=run.pk),
                user_id=self.setup["user"].id,
                reason="concurrency certification",
            )
        )

        successes = [result for result in results if not isinstance(result, Exception)]
        failures = [result for result in results if isinstance(result, Exception)]
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 1)
        self.assertIn("Only posted payroll runs can be reversed", str(failures[0]))
        run.refresh_from_db()
        self.assertEqual(run.status, PayrollRun.Status.REVERSED)
        self.assertEqual(run.reversal_runs.count(), 1)
        reversal = run.reversal_runs.get()
        self.assertEqual(
            PostingBatch.objects.filter(txn_type=TxnType.PAYROLL, txn_id=reversal.id).count(),
            1,
        )

    def test_posting_failure_rolls_back_status_audit_and_accounting(self):
        run = self._approve_run(self._create_run())

        def fail_after_audit(locked_run, *, user_id):
            PayrollRunHardeningService.log_action(
                locked_run,
                action=PayrollRunActionLog.Action.POSTED,
                user_id=user_id,
            )
            raise RuntimeError("simulated posting failure")

        with patch(
            "payroll.services.payroll_run_service.PayrollPostingService.post_run",
            side_effect=fail_after_audit,
        ):
            with self.assertRaisesMessage(RuntimeError, "simulated posting failure"):
                PayrollRunService.post_run(run, posted_by_id=self.setup["user"].id)

        run.refresh_from_db()
        self.assertEqual(run.status, PayrollRun.Status.APPROVED)
        self.assertIsNone(run.posted_entry_id)
        self.assertFalse(
            run.action_logs.filter(action=PayrollRunActionLog.Action.POSTED).exists()
        )
        self.assertFalse(
            PostingBatch.objects.filter(txn_type=TxnType.PAYROLL, txn_id=run.id).exists()
        )
