from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from payroll.models import PayrollRun
from payroll.services.payroll_run_service import PayrollRunService
from payroll.tests.factories import PayrollFactory


class PayrollRunServiceTests(TestCase):
    def setUp(self):
        self.setup = PayrollFactory.full_payroll_setup()

    def test_create_calculate_submit_approve_post_run(self):
        run = PayrollRunService.create_run(
            entity_id=self.setup["entity"].id,
            entityfinid_id=self.setup["entityfinid"].id,
            subentity_id=self.setup["subentity"].id,
            payroll_period_id=self.setup["period"].id,
            run_type=PayrollRun.RunType.REGULAR,
            posting_date=self.setup["period"].period_end,
            payout_date=self.setup["period"].payout_date,
            created_by_id=self.setup["user"].id,
        ).run

        PayrollRunService.calculate_run(run)
        run.refresh_from_db()
        self.assertEqual(run.status, PayrollRun.Status.CALCULATED)
        self.assertEqual(run.employee_runs.count(), 1)

        PayrollRunService.submit_run(run, submitted_by_id=self.setup["user"].id, note="submit")
        PayrollRunService.approve_run(run, approved_by_id=self.setup["user"].id, note="approve")
        run.refresh_from_db()
        self.assertEqual(run.status, PayrollRun.Status.APPROVED)
        self.assertTrue(run.is_immutable)
        self.assertEqual(run.employee_runs.filter(is_frozen=True).count(), 1)

        with patch("posting.services.posting_service.PostingService._pg_advisory_lock", return_value=None):
            PayrollRunService.post_run(run, posted_by_id=self.setup["user"].id)
        run.refresh_from_db()
        self.assertEqual(run.status, PayrollRun.Status.POSTED)
        self.assertIsNotNone(run.posted_entry_id)

    def test_invalid_post_transition_fails(self):
        run = PayrollFactory.payroll_run(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            payroll_period=self.setup["period"],
        )
        with self.assertRaisesMessage(ValueError, "Only approved payroll runs can be posted."):
            PayrollRunService.post_run(run, posted_by_id=self.setup["user"].id)

    def test_calculate_fails_when_immutable(self):
        run = PayrollFactory.payroll_run(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            payroll_period=self.setup["period"],
            is_immutable=True,
        )
        with self.assertRaisesMessage(ValueError, "immutable"):
            PayrollRunService.calculate_run(run)

    def test_calculate_blocks_subentity_scope_mismatch(self):
        other_scope = PayrollFactory.entity_scope(user=self.setup["user"], name_prefix="Other")
        other_structure = PayrollFactory.salary_structure(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=other_scope["subentity"],
        )
        other_version = PayrollFactory.salary_structure_version(salary_structure=other_structure)
        PayrollFactory.employee_profile(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=other_scope["subentity"],
            payment_account=self.setup["payable_account"],
            salary_structure=other_structure,
            salary_structure_version=other_version,
            employee_code="EMP-MISMATCH",
        )
        run = PayrollFactory.payroll_run(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            payroll_period=self.setup["period"],
        )
        PayrollRunService.calculate_run(run)
        self.assertEqual(run.employee_runs.count(), 1)
        self.assertTrue(all(row.employee_profile.subentity_id == self.setup["subentity"].id for row in run.employee_runs.all()))
