from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from payroll.models import PayrollRun
from payroll.services.payroll_reversal_service import PayrollReversalService
from payroll.services.payroll_run_service import PayrollRunService
from payroll.tests.factories import PayrollFactory


class PayrollReversalServiceTests(TestCase):
    def setUp(self):
        self.setup = PayrollFactory.full_payroll_setup()
        self.run = PayrollRunService.create_run(
            entity_id=self.setup["entity"].id,
            entityfinid_id=self.setup["entityfinid"].id,
            subentity_id=self.setup["subentity"].id,
            payroll_period_id=self.setup["period"].id,
            run_type=PayrollRun.RunType.REGULAR,
            posting_date=self.setup["period"].period_end,
            payout_date=self.setup["period"].payout_date,
            created_by_id=self.setup["user"].id,
        ).run
        PayrollRunService.calculate_run(self.run)
        PayrollRunService.submit_run(self.run, submitted_by_id=self.setup["user"].id)
        PayrollRunService.approve_run(self.run, approved_by_id=self.setup["user"].id)
        with patch("posting.services.posting_service.PostingService._pg_advisory_lock", return_value=None):
            PayrollRunService.post_run(self.run, posted_by_id=self.setup["user"].id)

    def test_reverse_posted_run_creates_linked_reversal(self):
        with patch("posting.services.posting_service.PostingService._pg_advisory_lock", return_value=None):
            reversal = PayrollReversalService.reverse_run(self.run, user_id=self.setup["user"].id, reason="test reversal")
        self.run.refresh_from_db()

        self.assertEqual(self.run.status, PayrollRun.Status.REVERSED)
        self.assertEqual(reversal.reversed_run_id, self.run.id)
        self.assertEqual(reversal.status, PayrollRun.Status.POSTED)
        self.assertIsNotNone(reversal.reversal_posting_entry_id)

    def test_reverse_non_posted_run_fails(self):
        draft_run = PayrollFactory.payroll_run(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            payroll_period=self.setup["period"],
        )
        with self.assertRaisesMessage(ValueError, "Only posted payroll runs can be reversed."):
            PayrollReversalService.reverse_run(draft_run, user_id=self.setup["user"].id, reason="nope")
