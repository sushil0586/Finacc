from __future__ import annotations

from django.db import IntegrityError
from django.test import TestCase

from payroll.models import PayrollRun, SalaryStructureVersion
from payroll.tests.factories import PayrollFactory


class PayrollModelTests(TestCase):
    def setUp(self):
        self.setup = PayrollFactory.full_payroll_setup()

    def test_salary_structure_version_unique_per_structure(self):
        with self.assertRaises(IntegrityError):
            SalaryStructureVersion.objects.create(
                salary_structure=self.setup["structure"],
                version_no=1,
            )

    def test_payroll_run_unique_by_scope_period_type(self):
        parent_run = PayrollFactory.payroll_run(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            payroll_period=self.setup["period"],
            run_type=PayrollRun.RunType.OFF_CYCLE,
        )
        PayrollFactory.payroll_run(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            payroll_period=self.setup["period"],
            correction_of_run=parent_run,
        )
        with self.assertRaises(IntegrityError):
            PayrollFactory.payroll_run(
                entity=self.setup["entity"],
                entityfinid=self.setup["entityfinid"],
                subentity=self.setup["subentity"],
                payroll_period=self.setup["period"],
                correction_of_run=parent_run,
            )

    def test_workflow_status_is_separate_from_payment_status(self):
        run = PayrollFactory.payroll_run(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            payroll_period=self.setup["period"],
            status=PayrollRun.Status.POSTED,
            payment_status=PayrollRun.PaymentStatus.HANDED_OFF,
        )
        self.assertEqual(run.status, PayrollRun.Status.POSTED)
        self.assertEqual(run.payment_status, PayrollRun.PaymentStatus.HANDED_OFF)
