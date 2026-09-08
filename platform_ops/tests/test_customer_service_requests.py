from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from Authentication.models import User
from subscriptions.models import CustomerAccount, UserEntityAccess
from platform_ops.models import (
    CustomerServiceRequest,
    PlatformPermission,
    PlatformRole,
    PlatformUserRole,
)


@override_settings(PLATFORM_OPS_ENABLED=True, PLATFORM_OPS_MUTATIONS_ENABLED=True)
class CustomerServiceRequestApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = User.objects.create_user(username="customer-requester", email="customer-requester@example.com", password="Test!1789")
        cls.other = User.objects.create_user(username="other-customer", email="other-customer@example.com", password="Test!1789")
        cls.operator = User.objects.create_user(username="request-operator", email="request-operator@example.com", password="Test!1789")
        cls.account = CustomerAccount.objects.create(name="Request Customer", slug="request-customer", owner=cls.customer, status="active")
        UserEntityAccess.objects.create(user=cls.customer, customer_account=cls.account, role="owner")
        permission, _ = PlatformPermission.objects.get_or_create(code="platform.support.manage", defaults={"name": "Manage customer requests"})
        role = PlatformRole.objects.create(code="request-manager-test", name="Request Manager")
        role.permissions.add(permission)
        PlatformUserRole.objects.create(user=cls.operator, role=role, granted_by=cls.operator, reason="Test request management")

    def setUp(self):
        self.client = APIClient()

    def test_customer_submits_and_only_sees_own_request(self):
        self.client.force_authenticate(self.customer)
        response = self.client.post("/api/subscriptions/service-requests", {
            "request_type": "entity_change",
            "subject": "Change registered address",
            "description": "Please update our registered office address from next month.",
            "priority": "normal",
        }, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], "new")
        self.assertEqual(response.data["events"][0]["to_status"], "new")
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get("/api/subscriptions/service-requests").data, [])

    def test_operator_processes_request_with_auditable_transitions(self):
        item = CustomerServiceRequest.objects.create(
            customer_account=self.account,
            request_type="subscription_change",
            subject="Upgrade plan",
            description="Please move this workspace to the business plan.",
            submitted_by=self.customer,
        )
        self.client.force_authenticate(self.operator)
        for next_status in ("in_review", "approved", "processing"):
            response = self.client.patch(f"/api/platform/customer-requests/{item.id}/", {
                "status": next_status,
                "note": f"Moved to {next_status}",
                "assign_to_me": True,
            }, format="json")
            self.assertEqual(response.status_code, 200)
        invalid = self.client.patch(f"/api/platform/customer-requests/{item.id}/", {"status": "completed"}, format="json")
        self.assertEqual(invalid.status_code, 400)
        completed = self.client.patch(f"/api/platform/customer-requests/{item.id}/", {
            "status": "completed",
            "resolution": "Business plan enabled and verified.",
            "note": "Customer change completed.",
        }, format="json")
        self.assertEqual(completed.status_code, 200)
        self.assertEqual(completed.data["status"], "completed")
        self.assertEqual(len(completed.data["events"]), 4)

    def test_invalid_status_jump_is_rejected(self):
        item = CustomerServiceRequest.objects.create(
            customer_account=self.account,
            request_type="account_change",
            subject="Change contact",
            description="Please change the primary contact for our account.",
            submitted_by=self.customer,
        )
        self.client.force_authenticate(self.operator)
        response = self.client.patch(f"/api/platform/customer-requests/{item.id}/", {
            "status": "completed",
            "resolution": "Done.",
        }, format="json")
        self.assertEqual(response.status_code, 400)
