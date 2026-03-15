from __future__ import annotations

from django.test import TestCase

from payroll.services.payroll_cutover_service import PayrollCutoverService
from payroll.services.payroll_run_service import PayrollRunService
from payroll.tests.factories import PayrollFactory


class PayrollCutoverServiceTests(TestCase):
    def setUp(self):
        self.setup = PayrollFactory.full_payroll_setup()

    def test_cutover_validation_passes_when_scope_is_ready(self):
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

        result = PayrollCutoverService.validate_cutover(
            entity_id=self.setup["entity"].id,
            entityfinid_id=self.setup["entityfinid"].id,
            subentity_id=self.setup["subentity"].id,
            period_code=self.setup["period"].code,
            payroll_run_id=run.id,
            expected_employee_count=1,
            legacy_frozen=True,
        )
        self.assertTrue(result.passed)

    def test_cutover_validation_warns_when_legacy_not_frozen(self):
        result = PayrollCutoverService.validate_cutover(
            entity_id=self.setup["entity"].id,
            entityfinid_id=self.setup["entityfinid"].id,
            subentity_id=self.setup["subentity"].id,
            period_code=self.setup["period"].code,
            legacy_frozen=False,
        )
        codes = {issue.code for issue in result.issues}
        self.assertIn("legacy_not_frozen", codes)
