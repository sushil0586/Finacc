from __future__ import annotations

from django.test import TestCase

from payroll.services.payroll_rollout_validation_service import PayrollRolloutValidationService
from payroll.tests.factories import PayrollFactory


class PayrollRolloutValidationServiceTests(TestCase):
    def test_validation_passes_with_complete_setup(self):
        setup = PayrollFactory.full_payroll_setup()
        result = PayrollRolloutValidationService.validate_setup(
            entity_id=setup["entity"].id,
            entityfinid_id=setup["entityfinid"].id,
            subentity_id=setup["subentity"].id,
            period_code=setup["period"].code,
        )
        self.assertTrue(result.passed)

    def test_validation_fails_when_critical_config_missing(self):
        scope = PayrollFactory.entity_scope()
        result = PayrollRolloutValidationService.validate_setup(
            entity_id=scope["entity"].id,
            entityfinid_id=scope["entityfinid"].id,
            subentity_id=scope["subentity"].id,
        )
        self.assertFalse(result.passed)
        codes = {issue.code for issue in result.issues}
        self.assertIn("missing_components", codes)
        self.assertIn("missing_ledger_policy", codes)
