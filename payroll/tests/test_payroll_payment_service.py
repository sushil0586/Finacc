from __future__ import annotations

from django.test import TestCase

from payroll.models import PayrollRun
from payroll.services.payroll_run_hardening_service import PayrollRunHardeningService
from payroll.tests.factories import PayrollFactory


class PayrollPaymentFlowTests(TestCase):
    def setUp(self):
        self.setup = PayrollFactory.full_payroll_setup()

    def test_payment_handoff_requires_posted_run(self):
        run = PayrollFactory.payroll_run(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            payroll_period=self.setup["period"],
        )
        with self.assertRaisesMessage(ValueError, "Only posted payroll runs can be handed off"):
            PayrollRunHardeningService.handoff_payment(run, user_id=self.setup["user"].id, batch_ref="B1")

    def test_payment_reconcile_updates_payment_status_without_changing_payroll_status(self):
        run = PayrollFactory.payroll_run(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            payroll_period=self.setup["period"],
            status=PayrollRun.Status.POSTED,
        )
        PayrollRunHardeningService.handoff_payment(run, user_id=self.setup["user"].id, batch_ref="B1")
        PayrollRunHardeningService.reconcile_payment(
            run,
            user_id=self.setup["user"].id,
            payment_status=PayrollRun.PaymentStatus.DISBURSED,
            comment="ok",
        )
        run.refresh_from_db()
        self.assertEqual(run.status, PayrollRun.Status.POSTED)
        self.assertEqual(run.payment_status, PayrollRun.PaymentStatus.DISBURSED)
