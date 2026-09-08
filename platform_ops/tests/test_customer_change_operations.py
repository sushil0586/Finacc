from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from Authentication.models import User
from platform_ops.models import (
    PlatformOperationRequest,
    PlatformPermission,
    PlatformRole,
    PlatformUserRole,
)
from subscriptions.models import CustomerAccount


@override_settings(PLATFORM_OPS_ENABLED=True, PLATFORM_OPS_MUTATIONS_ENABLED=True)
class PlatformCustomerContactChangeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.operator = User.objects.create_user(
            username="contact.operator",
            email="contact.operator@example.com",
            password="StrongPass123!",
        )
        cls.owner = User.objects.create_user(
            username="tenant.owner",
            email="tenant.owner@example.com",
            password="StrongPass123!",
        )
        cls.role = PlatformRole.objects.create(code="customer-editor", name="Customer Editor")
        cls.role.permissions.add(
            PlatformPermission.objects.get(code="platform.customer.update"),
            PlatformPermission.objects.get(code="platform.operation.view"),
            PlatformPermission.objects.get(code="platform.operation.execute"),
        )
        PlatformUserRole.objects.create(
            user=cls.operator,
            role=cls.role,
            granted_by=cls.operator,
            reason="Customer change operation tests",
        )
        cls.customer = CustomerAccount.objects.create(
            name="Change Test Customer",
            slug="change-test-customer",
            owner=cls.owner,
            status=CustomerAccount.Status.ACTIVE,
            primary_contact_email="old@example.com",
            primary_contact_phone="9000000000",
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.operator)
        self.customer.refresh_from_db()

    def payload(self, **changes):
        return {
            "idempotency_key": "customer-contact-change-1",
            "reason": "Correct the customer contact details from support ticket",
            "ticket_reference": "SUP-1001",
            "expected_target_version": self.customer.updated_at.isoformat(),
            "changes": changes or {
                "primary_contact_email": "new@example.com",
                "primary_contact_phone": "9111111111",
            },
        }

    def request_change(self, payload=None):
        return self.client.post(
            f"/api/platform/customers/{self.customer.id}/contact-change-requests/",
            payload or self.payload(),
            format="json",
        )

    def test_request_previews_before_and_after_without_mutating_customer(self):
        response = self.request_change()

        self.assertEqual(response.status_code, 201)
        operation = response.data["operation"]
        self.assertEqual(operation["operation_type"], "customer_contact_update")
        self.assertEqual(operation["risk"], "medium")
        self.assertEqual(operation["validation"]["before"]["primary_contact_email"], "old@example.com")
        self.assertEqual(operation["validation"]["after"]["primary_contact_email"], "new@example.com")
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.primary_contact_email, "old@example.com")

    def test_execute_changes_only_allowlisted_fields_and_captures_snapshots(self):
        created = self.request_change()
        operation_id = created.data["operation"]["id"]

        response = self.client.post(f"/api/platform/operations/{operation_id}/execute/", {}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["operation"]["status"], "succeeded")
        self.assertEqual(response.data["operation"]["result"]["before"]["primary_contact_email"], "old@example.com")
        self.assertEqual(response.data["operation"]["result"]["after"]["primary_contact_email"], "new@example.com")
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.primary_contact_email, "new@example.com")
        self.assertEqual(self.customer.primary_contact_phone, "9111111111")

    def test_idempotent_replay_and_conflict(self):
        first = self.request_change()
        replay = self.request_change()
        conflict_payload = self.payload(primary_contact_email="different@example.com")
        conflict = self.request_change(conflict_payload)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.data["replayed"])
        self.assertEqual(conflict.status_code, 400)
        self.assertEqual(PlatformOperationRequest.objects.filter(
            operation_type=PlatformOperationRequest.OperationType.CUSTOMER_CONTACT_UPDATE,
        ).count(), 1)

    def test_idempotency_rejects_same_changes_for_a_different_target_version(self):
        self.request_change()
        payload = self.payload()
        payload["expected_target_version"] = (self.customer.updated_at + timedelta(seconds=1)).isoformat()

        response = self.request_change(payload)

        self.assertEqual(response.status_code, 400)
        self.assertIn("idempotency_key", response.data)

    def test_rejects_non_allowlisted_fields(self):
        response = self.request_change(self.payload(status="suspended"))

        self.assertEqual(response.status_code, 400)
        self.assertIn("status", response.data["changes"])
        self.assertEqual(PlatformOperationRequest.objects.count(), 0)

    def test_execution_refuses_stale_target_without_applying_change(self):
        created = self.request_change()
        operation_id = created.data["operation"]["id"]
        CustomerAccount.objects.filter(pk=self.customer.id).update(
            primary_contact_phone="9222222222",
            updated_at=timezone.now() + timedelta(seconds=1),
        )

        response = self.client.post(f"/api/platform/operations/{operation_id}/execute/", {}, format="json")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["operation"]["status"], "failed")
        self.assertEqual(response.data["operation"]["failure"]["code"], "stale_target")
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.primary_contact_email, "old@example.com")
        self.assertEqual(self.customer.primary_contact_phone, "9222222222")

    def test_update_permission_is_required(self):
        self.role.permissions.remove(PlatformPermission.objects.get(code="platform.customer.update"))

        response = self.request_change()

        self.assertEqual(response.status_code, 403)
