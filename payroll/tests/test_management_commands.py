from __future__ import annotations

import json
import tempfile
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from payroll.services.payroll_run_service import PayrollRunService
from payroll.tests.factories import PayrollFactory


class PayrollManagementCommandTests(TestCase):
    def setUp(self):
        self.setup = PayrollFactory.full_payroll_setup()

    def test_validate_payroll_rollout_setup_command_success(self):
        out = StringIO()
        call_command(
            "validate_payroll_rollout_setup",
            entity=self.setup["entity"].id,
            entityfinid=self.setup["entityfinid"].id,
            subentity=self.setup["subentity"].id,
            period_code=self.setup["period"].code,
            stdout=out,
        )
        payload = json.loads(out.getvalue())
        self.assertTrue(payload["passed"])

    def test_validate_payroll_rollout_setup_command_failure(self):
        scope = PayrollFactory.entity_scope()
        with self.assertRaises(CommandError):
            call_command(
                "validate_payroll_rollout_setup",
                entity=scope["entity"].id,
                entityfinid=scope["entityfinid"].id,
                subentity=scope["subentity"].id,
            )

    def test_shadow_validation_command_success(self):
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

        out = StringIO()
        call_command(
            "run_payroll_shadow_validation",
            run_id=run.id,
            expected_employee_count=1,
            stdout=out,
        )
        payload = json.loads(out.getvalue())
        self.assertTrue(payload["passed"])

    def test_reconcile_payroll_results_command_failure(self):
        run = PayrollFactory.payroll_run(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            payroll_period=self.setup["period"],
            employee_count=1,
        )
        with tempfile.NamedTemporaryFile("w+", suffix=".json") as handle:
            json.dump(
                {
                    "employee_count": 1,
                    "gross_amount": "9999.00",
                    "deduction_amount": "100.00",
                    "net_pay_amount": "9000.00",
                    "component_totals": {},
                },
                handle,
            )
            handle.flush()
            with self.assertRaises(CommandError):
                call_command("reconcile_payroll_results", run_id=run.id, legacy_json=handle.name)

    def test_verify_payroll_posting_command_failure_without_posted_entry(self):
        run = PayrollFactory.payroll_run(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            payroll_period=self.setup["period"],
        )
        with self.assertRaises(CommandError):
            call_command("verify_payroll_posting", run_id=run.id)

    def test_validate_payroll_cutover_command_outputs_json(self):
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
        out = StringIO()
        call_command(
            "validate_payroll_cutover",
            entity=self.setup["entity"].id,
            entityfinid=self.setup["entityfinid"].id,
            subentity=self.setup["subentity"].id,
            period_code=self.setup["period"].code,
            run_id=run.id,
            expected_employee_count=1,
            legacy_frozen=True,
            stdout=out,
        )
        payload = json.loads(out.getvalue())
        self.assertIn("checks", payload)
        self.assertTrue(payload["passed"])
