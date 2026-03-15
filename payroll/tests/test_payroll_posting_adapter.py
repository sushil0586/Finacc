from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from payroll.services.payroll_posting_verification_service import PayrollPostingVerificationService
from payroll.services.payroll_run_service import PayrollRunService
from payroll.tests.factories import PayrollFactory
from posting.models import Entry, JournalLine, TxnType


class PayrollPostingAdapterTests(TestCase):
    def setUp(self):
        self.setup = PayrollFactory.full_payroll_setup()

    def test_posting_creates_balanced_entry(self):
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
        with patch("posting.services.posting_service.PostingService._pg_advisory_lock", return_value=None):
            PayrollRunService.post_run(run, posted_by_id=self.setup["user"].id)
        run.refresh_from_db()

        entry = Entry.objects.get(id=run.posted_entry_id)
        self.assertEqual(entry.txn_type, TxnType.PAYROLL)

        lines = JournalLine.objects.filter(entry=entry)
        dr_total = sum((line.amount for line in lines if line.drcr), Decimal("0.00"))
        cr_total = sum((line.amount for line in lines if not line.drcr), Decimal("0.00"))
        self.assertEqual(dr_total, cr_total)

    def test_posting_verification_passes_for_valid_posting(self):
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
        with patch("posting.services.posting_service.PostingService._pg_advisory_lock", return_value=None):
            PayrollRunService.post_run(run, posted_by_id=self.setup["user"].id)
        run.refresh_from_db()

        result = PayrollPostingVerificationService.verify_run_posting(run=run)
        self.assertTrue(result.passed)
