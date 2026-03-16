from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from payroll.models import PayrollRun
from payroll.serializers import PayrollRunDetailSerializer, PayrollRunSummarySerializer, PayslipSerializer
from payroll.services.payroll_run_hardening_service import PayrollRunHardeningService
from payroll.services.payroll_reversal_service import PayrollReversalService
from payroll.services.payroll_run_service import PayrollRunService
from payroll.tests.factories import PayrollFactory


class PayrollTraceabilityContractTests(TestCase):
    def setUp(self):
        self.setup = PayrollFactory.full_payroll_setup()

    def _build_posted_run(self):
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
        PayrollRunService.submit_run(run, submitted_by_id=self.setup["user"].id, note="submitted for audit")
        PayrollRunService.approve_run(run, approved_by_id=self.setup["user"].id, note="approved")
        with patch("posting.services.posting_service.PostingService._pg_advisory_lock", return_value=None):
            PayrollRunService.post_run(run, posted_by_id=self.setup["user"].id)
        return PayrollRun.objects.get(id=run.id)

    def test_run_detail_exposes_structured_traceability_and_timeline(self):
        run = self._build_posted_run()
        PayrollRunHardeningService.handoff_payment(
            run,
            user_id=self.setup["user"].id,
            batch_ref="BANK-BATCH-001",
            payload={"reconciliation_reference": "REC-001"},
        )
        PayrollRunHardeningService.reconcile_payment(
            run,
            user_id=self.setup["user"].id,
            payment_status=PayrollRun.PaymentStatus.RECONCILED,
            comment="bank confirmed",
        )

        run = (
            PayrollRun.objects.select_related(
                "entity",
                "entityfinid",
                "subentity",
                "payroll_period",
                "created_by",
                "submitted_by",
                "approved_by",
                "posted_by",
                "reversed_by",
                "reversed_run",
                "ledger_policy_version",
            )
            .prefetch_related(
                "action_logs__acted_by",
                "reversal_runs",
                "employee_runs__employee_profile__employee_user",
                "employee_runs__salary_structure",
                "employee_runs__salary_structure_version",
                "employee_runs__components",
                "employee_runs__components__component",
            )
            .get(id=run.id)
        )
        payload = PayrollRunDetailSerializer(run).data

        self.assertIn("traceability", payload)
        self.assertIn("timeline", payload)
        self.assertIn("actors", payload)
        self.assertIn("employee_rows", payload)
        self.assertIn("component_totals", payload)
        self.assertIn("posting_verification_issues", payload)
        self.assertIn("payment_verification_issues", payload)

        self.assertEqual(payload["traceability"]["run"]["run_id"], run.id)
        self.assertEqual(payload["traceability"]["posting"]["posting_entry_id"], run.posted_entry_id)
        self.assertEqual(payload["traceability"]["payment"]["handoff_reference"], "BANK-BATCH-001")
        self.assertEqual(payload["traceability"]["payment"]["reconciliation_reference"], "REC-001")
        self.assertEqual(payload["actors"]["created_by"]["user_id"], self.setup["user"].id)
        self.assertTrue(any(event["event_type"] == "posted" for event in payload["timeline"]))
        self.assertTrue(any(event["event_type"] == "payment_handoff" for event in payload["timeline"]))
        self.assertEqual(payload["employee_rows"][0]["payroll_profile_id"], self.setup["profile"].id)
        self.assertEqual(payload["component_totals"][0]["component_code"], self.setup["component"].code)

    def test_summary_serializer_exposes_component_totals_and_employee_issue_rows(self):
        run = self._build_posted_run()
        summary = PayrollRunService.summary(
            PayrollRun.objects.prefetch_related(
                "action_logs__acted_by",
                "reversal_runs",
                "employee_runs__employee_profile",
                "employee_runs__components",
            ).get(id=run.id)
        )
        payload = PayrollRunSummarySerializer(summary).data

        self.assertIn("traceability", payload)
        self.assertIn("timeline", payload)
        self.assertIn("employee_rows", payload)
        self.assertIn("component_totals", payload)
        self.assertEqual(payload["employee_rows"][0]["employee_code"], self.setup["profile"].employee_code)
        self.assertEqual(payload["component_totals"][0]["category"], "earning")

    def test_payslip_serializer_groups_sections_and_reversal_traceability_is_linked(self):
        run = self._build_posted_run()
        row = run.employee_runs.select_related("employee_profile", "salary_structure").prefetch_related("components").first()
        payslip = PayrollFactory.payslip(payroll_run_employee=row)
        payslip_payload = PayslipSerializer(
            PayslipSerializer.Meta.model.objects.select_related(
                "payroll_run_employee",
                "payroll_run_employee__employee_profile",
                "payroll_run_employee__salary_structure",
            ).prefetch_related("payroll_run_employee__components").get(id=payslip.id)
        ).data

        self.assertIn("earnings", payslip_payload)
        self.assertIn("deductions", payslip_payload)
        self.assertIn("employer_contributions", payslip_payload)
        self.assertEqual(payslip_payload["payroll_profile_id"], row.employee_profile_id)
        self.assertEqual(payslip_payload["salary_structure_id"], row.salary_structure_id)

        with patch("posting.services.posting_service.PostingService._pg_advisory_lock", return_value=None):
            reversal = PayrollReversalService.reverse_run(run, user_id=self.setup["user"].id, reason="audit fix")

        original_payload = PayrollRunDetailSerializer(
            PayrollRun.objects.select_related(
                "entity",
                "entityfinid",
                "subentity",
                "payroll_period",
                "created_by",
                "submitted_by",
                "approved_by",
                "posted_by",
                "reversed_by",
                "reversed_run",
                "ledger_policy_version",
            ).prefetch_related("action_logs__acted_by", "reversal_runs", "employee_runs__components").get(id=run.id)
        ).data
        reversal_payload = PayrollRunDetailSerializer(
            PayrollRun.objects.select_related(
                "entity",
                "entityfinid",
                "subentity",
                "payroll_period",
                "created_by",
                "submitted_by",
                "approved_by",
                "posted_by",
                "reversed_by",
                "reversed_run",
                "ledger_policy_version",
            ).prefetch_related("action_logs__acted_by", "reversal_runs", "employee_runs__components").get(id=reversal.id)
        ).data

        self.assertEqual(original_payload["traceability"]["reversal"]["status"], "reversed")
        self.assertEqual(original_payload["traceability"]["reversal"]["reversing_run_id"], reversal.id)
        self.assertEqual(reversal_payload["traceability"]["reversal"]["status"], "reversal_run")
        self.assertEqual(reversal_payload["traceability"]["reversal"]["original_run_id"], run.id)
