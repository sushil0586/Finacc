from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import serializers
from rest_framework.test import APIClient

from Authentication.models import User
from platform_ops.models import (
    PlatformOperationApproval,
    PlatformOperationRequest,
    PlatformPermission,
    PlatformProvisioningJob,
    PlatformRole,
    PlatformUserRole,
)
from platform_ops.operations import PlatformOperationService
from subscriptions.models import CustomerAccount


@override_settings(PLATFORM_OPS_ENABLED=True, PLATFORM_OPS_MUTATIONS_ENABLED=True, PLATFORM_OPS_APPROVAL_TTL_HOURS=1)
class PlatformOperationLifecycleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.operator = User.objects.create_user(username="lifecycle-operator", email="lifecycle@example.com", password="Pass123!")
        cls.owner = User.objects.create_user(username="lifecycle-owner", email="lifecycle-owner@example.com", password="Pass123!")
        role = PlatformRole.objects.create(code="lifecycle-role", name="Lifecycle Operator")
        role.permissions.add(
            PlatformPermission.objects.get(code="platform.operation.cancel"),
            PlatformPermission.objects.get(code="platform.operation.execute"),
            PlatformPermission.objects.get(code="platform.repair.execute"),
        )
        PlatformUserRole.objects.create(user=cls.operator, role=role, granted_by=cls.operator, reason="Lifecycle tests")

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.operator)
        self.customer = CustomerAccount.objects.create(
            name="Lifecycle Customer", slug=f"lifecycle-{CustomerAccount.objects.count()}",
            owner=self.owner, status=CustomerAccount.Status.ACTIVE,
        )

    def operation(self, *, status="validated", operation_type="customer_contact_update", key="lifecycle-1"):
        return PlatformOperationRequest.objects.create(
            operation_type=operation_type,
            risk=PlatformOperationRequest.Risk.MEDIUM,
            status=status,
            requested_by=self.operator,
            reason="Lifecycle operation created for controlled testing",
            ticket_reference="OPS-8001",
            idempotency_key=key,
            payload_hash=key.ljust(64, "0")[:64],
            request_snapshot={"changes": {}},
            customer_account_id=self.customer.id,
            expected_target_version=self.customer.updated_at,
        )

    def test_cancel_records_actor_reason_and_replays(self):
        operation = self.operation()
        response = self.client.post(
            f"/api/platform/operations/{operation.id}/cancel/",
            {"reason": "Customer requested cancellation before execution"}, format="json",
        )
        replay = self.client.post(
            f"/api/platform/operations/{operation.id}/cancel/",
            {"reason": "Customer requested cancellation before execution"}, format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["operation"]["status"], "cancelled")
        self.assertEqual(response.data["operation"]["cancellation"]["cancelled_by"]["email"], self.operator.email)
        self.assertTrue(replay.data["replayed"])

    def test_running_succeeded_and_rejected_operations_are_not_cancellable(self):
        for index, status_value in enumerate(("running", "succeeded", "rejected")):
            operation = self.operation(status=status_value, key=f"terminal-{index}")
            response = self.client.post(
                f"/api/platform/operations/{operation.id}/cancel/",
                {"reason": "Attempt cancellation after terminal transition"}, format="json",
            )
            self.assertEqual(response.status_code, 400)

    def test_expired_approval_becomes_terminal_before_execution(self):
        operation = self.operation(status="approved", operation_type="customer_status_update", key="expired-approval")
        operation.risk = PlatformOperationRequest.Risk.HIGH
        operation.request_snapshot = {"desired_status": "suspended"}
        operation.save(update_fields=["risk", "request_snapshot", "updated_at"])
        PlatformOperationApproval.objects.create(
            operation=operation,
            decided_by=self.owner,
            decision=PlatformOperationApproval.Decision.APPROVED,
            comment="Approval that is intentionally expired",
            target_version=self.customer.updated_at,
            decided_at=timezone.now() - timedelta(hours=2),
        )
        response = self.client.post(f"/api/platform/operations/{operation.id}/execute/", {}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["operation"]["failure"]["code"], "approval_expired")
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.status, CustomerAccount.Status.ACTIVE)

    def test_retry_rejects_non_onboarding_and_nonfailed_operations(self):
        failed = self.operation(status="failed", key="failed-contact")
        response = self.client.post(f"/api/platform/operations/{failed.id}/retry/", {}, format="json")
        self.assertEqual(response.status_code, 400)
        onboarding = self.operation(status="validated", operation_type="onboard_customer", key="valid-onboarding")
        response = self.client.post(f"/api/platform/operations/{onboarding.id}/retry/", {}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_retry_accepts_only_failed_onboarding_with_failed_job(self):
        onboarding = self.operation(status="failed", operation_type="onboard_customer", key="failed-onboarding")
        job = PlatformProvisioningJob.objects.create(
            operation=onboarding, status=PlatformProvisioningJob.Status.FAILED, attempt_count=1,
        )
        PlatformOperationService.validate_retry(onboarding)
        job.status = PlatformProvisioningJob.Status.SUCCEEDED
        job.save(update_fields=["status", "updated_at"])
        onboarding = PlatformOperationRequest.objects.select_related("provisioning_job").get(pk=onboarding.pk)
        with self.assertRaises(serializers.ValidationError):
            PlatformOperationService.validate_retry(onboarding)
