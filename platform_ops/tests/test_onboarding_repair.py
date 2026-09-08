from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from Authentication.models import User
from platform_ops.models import PlatformAuditEvent, PlatformOperationRequest, PlatformPermission, PlatformProvisioningJob, PlatformRole, PlatformUserRole


@override_settings(PLATFORM_OPS_ENABLED=True, PLATFORM_OPS_MUTATIONS_ENABLED=True)
class PlatformOnboardingRepairTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.operator = User.objects.create_user(username="repairer", email="repairer@example.com", password="Pass123!")
        role = PlatformRole.objects.create(code="repair-test", name="Repair Test")
        role.permissions.add(
            PlatformPermission.objects.get(code="platform.repair.preview"),
            PlatformPermission.objects.get(code="platform.repair.execute"),
        )
        PlatformUserRole.objects.create(user=cls.operator, role=role, granted_by=cls.operator, reason="Repair tests")

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.operator)

    def operation(self, *, status="failed", job_status="failed"):
        operation = PlatformOperationRequest.objects.create(
            operation_type=PlatformOperationRequest.OperationType.ONBOARD_CUSTOMER,
            risk=PlatformOperationRequest.Risk.MEDIUM,
            status=status,
            requested_by=self.operator,
            reason="Repair failed onboarding after incident review",
            ticket_reference="INC-REPAIR-1",
            idempotency_key=f"repair-{PlatformOperationRequest.objects.count()}",
            payload_hash="a" * 64,
            request_snapshot={
                "owner": {"email": "repair-owner@example.com"},
                "customer": {"external_customer_id": "REPAIR-CUSTOMER-1"},
                "onboarding": {"entity": {"entity_code": "REPAIR-ENTITY-1"}},
            },
        )
        PlatformProvisioningJob.objects.create(
            operation=operation, status=job_status, current_stage="entity", attempt_count=1,
        )
        return operation

    def test_preview_reports_clean_full_transaction_retry(self):
        operation = self.operation()
        response = self.client.get(f"/api/platform/operations/{operation.id}/repair-preview/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["eligible"])
        self.assertTrue(response.data["rollback_verified"])
        self.assertEqual(response.data["strategy"], "full_transaction_retry")
        self.assertEqual(response.data["failed_stage"], "entity")

    def test_preview_blocks_identifier_collision(self):
        operation = self.operation()
        User.objects.create_user(username="occupied", email="repair-owner@example.com", password="Pass123!")
        response = self.client.get(f"/api/platform/operations/{operation.id}/repair-preview/")
        self.assertFalse(response.data["eligible"])
        self.assertEqual(response.data["collisions"][0]["code"], "owner_email_in_use")
        self.assertEqual(response.data["strategy"], "manual_review")

    def test_execute_repair_delegates_to_transactional_onboarding(self):
        operation = self.operation()
        succeeded = operation
        succeeded.status = PlatformOperationRequest.Status.SUCCEEDED
        with patch("platform_ops.operation_views.PlatformOperationService.execute_onboarding", return_value=(succeeded, False)) as execute:
            response = self.client.post(f"/api/platform/operations/{operation.id}/repair/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        execute.assert_called_once_with(operation_id=operation.id)
        self.assertTrue(PlatformAuditEvent.objects.filter(event_type="platform.onboarding.repair.succeeded").exists())

    def test_execute_repair_rejects_nonfailed_operation(self):
        operation = self.operation(status="validated", job_status="pending")
        response = self.client.post(f"/api/platform/operations/{operation.id}/repair/", {}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.data["repair"]["eligible"])

    def test_legacy_retry_requires_repair_execute_permission(self):
        operation = self.operation()
        role = PlatformRole.objects.get(code="repair-test")
        role.permissions.remove(PlatformPermission.objects.get(code="platform.repair.execute"))
        response = self.client.post(f"/api/platform/operations/{operation.id}/retry/", {}, format="json")
        self.assertEqual(response.status_code, 403)
