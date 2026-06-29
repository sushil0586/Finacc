from __future__ import annotations

from decimal import Decimal
from unittest import skipUnless
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from entity.models import NotificationEvent, UserNotification

try:
    from payroll.models import PayrollRun
    from payroll.services.payroll_run_service import PayrollRunService
    from payroll.tests.factories import PayrollFactory
    PAYROLL_TESTS_AVAILABLE = True
except Exception:
    PayrollRun = None
    PayrollRunService = None
    PayrollFactory = None
    PAYROLL_TESTS_AVAILABLE = False


@skipUnless(PAYROLL_TESTS_AVAILABLE, "Payroll app is not installed in this test configuration.")
class NotificationApiTests(TestCase):
    def setUp(self):
        self.setup = PayrollFactory.full_payroll_setup()
        self.user = self.setup["user"]
        self.client.force_login(self.user)

    def _build_approvable_run(self) -> PayrollRun:
        run = PayrollFactory.payroll_run(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            payroll_period=self.setup["period"],
            status=PayrollRun.Status.CALCULATED,
            run_number="RUN-NOTIF-001",
            created_by=self.user,
        )
        PayrollFactory.payroll_run_employee(
            payroll_run=run,
            employee_profile=self.setup["profile"],
            salary_structure=self.setup["structure"],
            salary_structure_version=self.setup["version"],
            ledger_policy_version=self.setup["ledger_policy"],
            contract_payroll_profile=self.setup["contract_profile"],
            payable_amount=Decimal("950.00"),
        )
        return run

    def test_approval_creates_notification(self):
        run = self._build_approvable_run()

        PayrollRunService.approve_run(run, approved_by_id=self.user.id, note="approve with notify")

        self.assertTrue(
            UserNotification.objects.filter(
                user=self.user,
                event__event_code="PAYROLL_RUN_APPROVED",
            ).exists()
        )

    def test_payroll_blocker_notification_created(self):
        run = self._build_approvable_run()
        with patch.object(PayrollRunService, "_approval_preflight_blockers", return_value=[{"code": "MISSING_SETUP"}]):
            with self.assertRaises(ValueError):
                PayrollRunService.approve_run(run, approved_by_id=self.user.id, note="blocked")

        event = NotificationEvent.objects.filter(event_code="PAYROLL_RUN_BLOCKED").latest("id")
        self.assertEqual(event.entity_id, self.setup["entity"].id)
        self.assertEqual(event.payload["blocking_issues"][0]["code"], "MISSING_SETUP")

    def test_unread_count_and_mark_read_work(self):
        run = self._build_approvable_run()
        PayrollRunService.approve_run(run, approved_by_id=self.user.id, note="approve with notify")
        notification = UserNotification.objects.filter(user=self.user).latest("id")
        total_unread = UserNotification.objects.filter(user=self.user, is_read=False).count()

        unread_url = reverse("entity:entity-notification-unread-count")
        response = self.client.get(unread_url, {"entity": self.setup["entity"].id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], total_unread)

        mark_read_url = reverse("entity:entity-notification-mark-read", kwargs={"pk": notification.id})
        response = self.client.post(mark_read_url, data={}, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

        response = self.client.get(unread_url, {"entity": self.setup["entity"].id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], total_unread - 1)
