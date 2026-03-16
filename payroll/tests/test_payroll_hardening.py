from __future__ import annotations

import csv
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from payroll.admin import PayrollRunAdmin
from payroll.models import PayrollRun, PayrollRunActionLog
from payroll.services.payroll_export_service import PayrollExportService
from payroll.services.payroll_run_service import PayrollRunService
from payroll.tests.factories import PayrollFactory
from payroll.views.payroll_run_views import (
    PayrollRunApproveAPIView,
    PayrollRunCalculateAPIView,
    PayrollRunPaymentHandoffAPIView,
    PayrollRunPaymentReconcileAPIView,
    PayrollRunPostAPIView,
    PayrollRunReverseAPIView,
)


class PayrollHardeningTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.setup = PayrollFactory.full_payroll_setup()
        self.operator = PayrollFactory.user(username="operator", email="operator@example.com")
        self.reviewer = PayrollFactory.user(username="reviewer", email="reviewer@example.com")
        self.finance = PayrollFactory.user(username="finance", email="finance@example.com")
        self.payroll_admin = PayrollFactory.user(username="payrolladmin", email="payrolladmin@example.com")
        self.admin_user = PayrollFactory.user(username="payadmin", email="payadmin@example.com", is_staff=True)
        self.admin_user.is_superuser = True
        self.admin_user.save(update_fields=["is_superuser"])
        Group.objects.get_or_create(name="payroll_operator")[0].user_set.add(self.operator)
        Group.objects.get_or_create(name="payroll_reviewer")[0].user_set.add(self.reviewer)
        Group.objects.get_or_create(name="payroll_finance")[0].user_set.add(self.finance)
        Group.objects.get_or_create(name="payroll_admin")[0].user_set.add(self.payroll_admin)

    def _build_calculated_run(self):
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
        return PayrollRun.objects.get(id=run.id)

    def _build_posted_run(self):
        run = self._build_calculated_run()
        PayrollRunService.submit_run(run, submitted_by_id=self.setup["user"].id, note="submitted")
        PayrollRunService.approve_run(run, approved_by_id=self.setup["user"].id, note="approved")
        with patch("posting.services.posting_service.PostingService._pg_advisory_lock", return_value=None):
            PayrollRunService.post_run(run, posted_by_id=self.setup["user"].id)
        return PayrollRun.objects.get(id=run.id)

    def test_approved_run_employee_row_is_immutable_for_totals(self):
        run = self._build_calculated_run()
        PayrollRunService.approve_run(run, approved_by_id=self.setup["user"].id, note="approved")
        row = run.employee_runs.first()
        row.gross_amount = row.gross_amount + 10
        with self.assertRaises(ValidationError):
            row.save()

    def test_posted_run_payload_is_immutable_but_status_comment_can_change(self):
        run = self._build_posted_run()
        run.gross_amount = run.gross_amount + 1
        with self.assertRaises(ValidationError):
            run.save()

        run = PayrollRun.objects.get(id=run.id)
        run.status_comment = "investigation note"
        run.save()
        self.assertEqual(PayrollRun.objects.get(id=run.id).status_comment, "investigation note")

    def test_audit_payload_contains_run_reference_actor_and_reference_metadata(self):
        run = self._build_posted_run()
        log = run.action_logs.filter(action=PayrollRunActionLog.Action.POSTED).latest("created_at")
        self.assertEqual(log.payload["run_id"], run.id)
        self.assertEqual(log.payload["run_reference"], run.run_number or f"{run.doc_code}-{run.doc_no or run.id}")
        self.assertEqual(log.payload["actor_id"], self.setup["user"].id)
        self.assertIn("actor_name", log.payload)
        self.assertEqual(log.payload["posting_entry_id"], run.posted_entry_id)

    def test_calculate_view_requires_operator_permission(self):
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
        view = PayrollRunCalculateAPIView.as_view()

        denied_request = self.factory.post(f"/payroll/runs/{run.id}/calculate/", {}, format="json")
        force_authenticate(denied_request, user=self.reviewer)
        denied_response = view(denied_request, pk=run.id)
        self.assertEqual(denied_response.status_code, status.HTTP_403_FORBIDDEN)

        allowed_request = self.factory.post(f"/payroll/runs/{run.id}/calculate/", {}, format="json")
        force_authenticate(allowed_request, user=self.operator)
        allowed_response = view(allowed_request, pk=run.id)
        self.assertEqual(allowed_response.status_code, status.HTTP_200_OK)

    def test_post_view_requires_finance_permission(self):
        run = self._build_calculated_run()
        PayrollRunService.submit_run(run, submitted_by_id=self.setup["user"].id)
        PayrollRunService.approve_run(run, approved_by_id=self.setup["user"].id)
        view = PayrollRunPostAPIView.as_view()

        denied_request = self.factory.post(f"/payroll/runs/{run.id}/post/", {}, format="json")
        force_authenticate(denied_request, user=self.operator)
        denied_response = view(denied_request, pk=run.id)
        self.assertEqual(denied_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_approve_view_requires_reviewer_permission(self):
        run = self._build_calculated_run()
        view = PayrollRunApproveAPIView.as_view()

        denied_request = self.factory.post(f"/payroll/runs/{run.id}/approve/", {}, format="json")
        force_authenticate(denied_request, user=self.operator)
        denied_response = view(denied_request, pk=run.id)
        self.assertEqual(denied_response.status_code, status.HTTP_403_FORBIDDEN)

        allowed_request = self.factory.post(f"/payroll/runs/{run.id}/approve/", {"note": "approved"}, format="json")
        force_authenticate(allowed_request, user=self.reviewer)
        allowed_response = view(allowed_request, pk=run.id)
        self.assertEqual(allowed_response.status_code, status.HTTP_200_OK)

    def test_payment_views_require_finance_permission(self):
        run = self._build_posted_run()
        handoff_view = PayrollRunPaymentHandoffAPIView.as_view()
        denied_handoff = self.factory.post(
            f"/payroll/runs/{run.id}/payment-handoff/",
            {"payment_batch_ref": "BATCH-01"},
            format="json",
        )
        force_authenticate(denied_handoff, user=self.operator)
        denied_handoff_response = handoff_view(denied_handoff, pk=run.id)
        self.assertEqual(denied_handoff_response.status_code, status.HTTP_403_FORBIDDEN)

        allowed_handoff = self.factory.post(
            f"/payroll/runs/{run.id}/payment-handoff/",
            {"payment_batch_ref": "BATCH-01"},
            format="json",
        )
        force_authenticate(allowed_handoff, user=self.finance)
        allowed_handoff_response = handoff_view(allowed_handoff, pk=run.id)
        self.assertEqual(allowed_handoff_response.status_code, status.HTTP_200_OK)

        reconcile_view = PayrollRunPaymentReconcileAPIView.as_view()
        denied_reconcile = self.factory.post(
            f"/payroll/runs/{run.id}/payment-reconcile/",
            {"payment_status": PayrollRun.PaymentStatus.DISBURSED},
            format="json",
        )
        force_authenticate(denied_reconcile, user=self.reviewer)
        denied_reconcile_response = reconcile_view(denied_reconcile, pk=run.id)
        self.assertEqual(denied_reconcile_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_reverse_view_requires_payroll_admin_permission(self):
        run = self._build_posted_run()
        view = PayrollRunReverseAPIView.as_view()

        denied_request = self.factory.post(f"/payroll/runs/{run.id}/reverse/", {"note": "reverse"}, format="json")
        force_authenticate(denied_request, user=self.finance)
        denied_response = view(denied_request, pk=run.id)
        self.assertEqual(denied_response.status_code, status.HTTP_403_FORBIDDEN)

        allowed_request = self.factory.post(f"/payroll/runs/{run.id}/reverse/", {"note": "reverse"}, format="json")
        force_authenticate(allowed_request, user=self.payroll_admin)
        with patch("posting.services.posting_service.PostingService._pg_advisory_lock", return_value=None):
            allowed_response = view(allowed_request, pk=run.id)
        self.assertEqual(allowed_response.status_code, status.HTTP_200_OK)

    def test_superuser_bypass_still_allows_restricted_action(self):
        run = self._build_calculated_run()
        view = PayrollRunApproveAPIView.as_view()
        request = self.factory.post(f"/payroll/runs/{run.id}/approve/", {"note": "approved"}, format="json")
        force_authenticate(request, user=self.admin_user)
        response = view(request, pk=run.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_finalized_payroll_run_cannot_be_deleted(self):
        run = self._build_posted_run()
        with self.assertRaises(ValidationError):
            run.delete()

    def test_payroll_action_log_cannot_be_deleted(self):
        run = self._build_posted_run()
        log = run.action_logs.latest("created_at")
        with self.assertRaises(ValidationError):
            log.delete()

    def test_export_service_outputs_csv_headers_and_data(self):
        run = self._build_posted_run()
        response = PayrollExportService.export_run_register(
            runs=PayrollRun.objects.select_related("entity", "payroll_period").filter(id=run.id)
        )
        content = response.content.decode()
        rows = list(csv.reader(StringIO(content)))
        self.assertEqual(rows[0][0], "run_id")
        self.assertEqual(rows[1][0], str(run.id))

    def test_admin_export_action_returns_csv_response(self):
        run = self._build_posted_run()
        admin_instance = PayrollRunAdmin(PayrollRun, admin_site=None)
        response = admin_instance.export_deduction_summary_csv(
            request=None,
            queryset=PayrollRun.objects.filter(id=run.id),
        )
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertIn("payroll_deduction_summary.csv", response["Content-Disposition"])
