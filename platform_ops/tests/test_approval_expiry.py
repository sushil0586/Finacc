import json
from datetime import timedelta
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from Authentication.models import User
from platform_ops.models import PlatformAuditEvent, PlatformOperationApproval, PlatformOperationRequest
from platform_ops.operations import PlatformOperationService
from subscriptions.models import CustomerAccount


@override_settings(PLATFORM_OPS_APPROVAL_TTL_HOURS=24)
class PlatformApprovalExpiryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.requester = User.objects.create_user(username="expiry-maker", email="expiry-maker@example.com", password="Pass123!")
        cls.approver = User.objects.create_user(username="expiry-checker", email="expiry-checker@example.com", password="Pass123!")
        cls.customer = CustomerAccount.objects.create(name="Expiry Customer", slug="expiry-customer", owner=cls.requester)

    def operation(self, *, age_hours):
        operation = PlatformOperationRequest.objects.create(
            operation_type=PlatformOperationRequest.OperationType.CUSTOMER_STATUS_UPDATE,
            risk=PlatformOperationRequest.Risk.HIGH,
            status=PlatformOperationRequest.Status.APPROVED,
            requested_by=self.requester,
            reason="Approved customer status operation for expiry testing",
            ticket_reference="OPS-EXPIRY-1",
            idempotency_key=f"expiry-{age_hours}-{PlatformOperationRequest.objects.count()}",
            payload_hash="e" * 64,
            request_snapshot={"desired_status": "suspended"},
            customer_account_id=self.customer.id,
            expected_target_version=self.customer.updated_at,
        )
        approval = PlatformOperationApproval.objects.create(
            operation=operation,
            decided_by=self.approver,
            decision=PlatformOperationApproval.Decision.APPROVED,
            comment="Approved for scheduled expiry testing",
            target_version=self.customer.updated_at,
            decided_at=timezone.now() - timedelta(hours=age_hours),
        )
        return operation

    def test_sweep_expires_only_approvals_outside_execution_window(self):
        expired = self.operation(age_hours=25)
        current = self.operation(age_hours=23)
        result = PlatformOperationService.expire_approved_operations()
        expired.refresh_from_db()
        current.refresh_from_db()
        self.assertEqual(result["expired"], 1)
        self.assertEqual(expired.failure_code, "approval_expired")
        self.assertEqual(current.status, PlatformOperationRequest.Status.APPROVED)
        event = PlatformAuditEvent.objects.get(event_type="platform.operation.approval.expired")
        self.assertIsNone(event.actor_id)
        self.assertEqual(event.details["trigger"], "scheduled_sweep")

    def test_sweep_is_idempotent(self):
        self.operation(age_hours=25)
        first = PlatformOperationService.expire_approved_operations()
        second = PlatformOperationService.expire_approved_operations()
        self.assertEqual(first["expired"], 1)
        self.assertEqual(second["expired"], 0)
        self.assertEqual(PlatformAuditEvent.objects.filter(event_type="platform.operation.approval.expired").count(), 1)

    def test_dry_run_reports_without_mutation_or_audit(self):
        operation = self.operation(age_hours=25)
        result = PlatformOperationService.expire_approved_operations(dry_run=True)
        operation.refresh_from_db()
        self.assertEqual(result["matched"], 1)
        self.assertEqual(result["expired"], 0)
        self.assertEqual(operation.status, PlatformOperationRequest.Status.APPROVED)
        self.assertFalse(PlatformAuditEvent.objects.exists())

    def test_management_command_supports_dry_run_and_execution(self):
        operation = self.operation(age_hours=25)
        output = StringIO()
        call_command("expire_platform_approvals", "--dry-run", stdout=output)
        self.assertIn("matched: 1", output.getvalue())
        operation.refresh_from_db()
        self.assertEqual(operation.status, PlatformOperationRequest.Status.APPROVED)
        output = StringIO()
        call_command("expire_platform_approvals", stdout=output)
        self.assertIn("expired: 1", output.getvalue())

    def test_management_command_json_is_stable_for_monitoring(self):
        operation = self.operation(age_hours=25)
        output = StringIO()
        call_command("expire_platform_approvals", "--dry-run", "--json", stdout=output)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload, {
            "dry_run": True, "expired": 0, "matched": 1,
            "operation_ids": [str(operation.id)],
        })
        output = StringIO()
        call_command("expire_platform_approvals", "--json", stdout=output)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["expired"], 1)
        self.assertFalse(payload["dry_run"])

    def test_systemd_timer_contract_is_deployed_by_refresh_script(self):
        root = Path(__file__).resolve().parents[2]
        service = (root / "deploy/ec2/finacc-platform-approval-expiry.service").read_text()
        timer = (root / "deploy/ec2/finacc-platform-approval-expiry.timer").read_text()
        refresh = (root / "deploy/ec2/staging_refresh_backend.sh").read_text()
        self.assertIn("expire_platform_approvals --json", service)
        self.assertIn("EnvironmentFile=/home/ubuntu/Finacc/.env", service)
        self.assertIn("OnCalendar=hourly", timer)
        self.assertIn("Persistent=true", timer)
        self.assertIn("enable --now finacc-platform-approval-expiry.timer", refresh)
