from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from Authentication.models import User
from platform_ops.models import PlatformOperationRequest, PlatformPermission, PlatformRole, PlatformUserRole
from subscriptions.models import CustomerAccount, UserEntityAccess


@override_settings(PLATFORM_OPS_ENABLED=True, PLATFORM_OPS_MUTATIONS_ENABLED=True)
class PlatformMembershipChangeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.maker = User.objects.create_user(username="member-maker", email="member-maker@example.com", password="Pass123!")
        cls.checker = User.objects.create_user(username="member-checker", email="member-checker@example.com", password="Pass123!")
        cls.executor = User.objects.create_user(username="member-executor", email="member-executor@example.com", password="Pass123!")
        cls.owner = User.objects.create_user(username="tenant-owner", email="tenant-owner@example.com", password="Pass123!")
        cls.member_user = User.objects.create_user(username="tenant-member", email="tenant-member@example.com", password="Pass123!")
        maker_role = PlatformRole.objects.create(code="member-maker-role", name="Membership Maker")
        maker_role.permissions.add(PlatformPermission.objects.get(code="platform.membership.manage"))
        checker_role = PlatformRole.objects.create(code="member-checker-role", name="Membership Checker")
        checker_role.permissions.add(PlatformPermission.objects.get(code="platform.operation.approve"))
        executor_role = PlatformRole.objects.create(code="member-executor-role", name="Membership Executor")
        executor_role.permissions.add(PlatformPermission.objects.get(code="platform.operation.execute"))
        for user, role in ((cls.maker, maker_role), (cls.checker, checker_role), (cls.executor, executor_role)):
            PlatformUserRole.objects.create(user=user, role=role, granted_by=cls.maker, reason="Membership tests")

    def setUp(self):
        self.client = APIClient()
        self.future_expiry = timezone.now() + timedelta(days=90)
        self.customer = CustomerAccount.objects.create(
            name="Membership Customer", slug=f"membership-{CustomerAccount.objects.count()}",
            owner=self.owner, status=CustomerAccount.Status.ACTIVE,
        )
        self.owner_membership = UserEntityAccess.objects.create(
            customer_account=self.customer, user=self.owner, role=UserEntityAccess.Role.OWNER,
        )
        self.membership = UserEntityAccess.objects.create(
            customer_account=self.customer, user=self.member_user, role=UserEntityAccess.Role.MEMBER,
        )

    def request_change(self, *, key="membership-change-1", role="admin", is_active=True, version=None):
        self.client.force_authenticate(self.maker)
        self.membership.refresh_from_db()
        return self.client.post(
            f"/api/platform/customers/{self.customer.id}/memberships/{self.membership.id}/change-requests/",
            {
                "idempotency_key": key,
                "reason": "Update tenant access after approved security review",
                "ticket_reference": "SEC-4001",
                "expected_target_version": (version or self.membership.updated_at).isoformat(),
                "role": role,
                "is_active": is_active,
                "expires_at": self.future_expiry.isoformat() if is_active else None,
            },
            format="json",
        )

    def approve(self, operation_id):
        self.client.force_authenticate(self.checker)
        return self.client.post(
            f"/api/platform/operations/{operation_id}/decision/",
            {"decision": "approved", "comment": "Identity and access ticket reviewed independently"},
            format="json",
        )

    def execute(self, operation_id):
        self.client.force_authenticate(self.executor)
        return self.client.post(f"/api/platform/operations/{operation_id}/execute/", {}, format="json")

    def test_approved_change_updates_role_expiry_and_replays_once(self):
        requested = self.request_change()
        self.assertEqual(requested.status_code, 201)
        operation_id = requested.data["operation"]["id"]
        self.assertEqual(self.approve(operation_id).status_code, 200)
        executed = self.execute(operation_id)
        replay = self.execute(operation_id)
        self.assertEqual(executed.status_code, 200)
        self.assertTrue(replay.data["replayed"])
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.role, UserEntityAccess.Role.ADMIN)
        self.assertIsNotNone(self.membership.expires_at)

    def test_approved_suspension_uses_membership_deactivation(self):
        operation_id = self.request_change(role="member", is_active=False, key="suspend-member").data["operation"]["id"]
        self.approve(operation_id)
        self.assertEqual(self.execute(operation_id).status_code, 200)
        self.membership.refresh_from_db()
        self.assertFalse(self.membership.is_active)
        self.assertEqual(self.membership.role, UserEntityAccess.Role.MEMBER)
        self.assertEqual(self.membership.metadata["deactivated_by_id"], self.maker.id)

    def test_owner_membership_is_protected(self):
        self.client.force_authenticate(self.maker)
        response = self.client.post(
            f"/api/platform/customers/{self.customer.id}/memberships/{self.owner_membership.id}/change-requests/",
            {
                "idempotency_key": "owner-change", "reason": "Attempt owner role change after review",
                "ticket_reference": "SEC-4002", "expected_target_version": self.owner_membership.updated_at.isoformat(),
                "role": "admin", "is_active": True, "expires_at": None,
            }, format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("membership", response.data)

    def test_stale_request_and_stale_approval_are_rejected(self):
        old_version = self.membership.updated_at
        UserEntityAccess.objects.filter(pk=self.membership.id).update(updated_at=timezone.now() + timedelta(seconds=1))
        self.assertEqual(self.request_change(key="stale-request", version=old_version).status_code, 400)
        requested = self.request_change(key="stale-approval")
        operation_id = requested.data["operation"]["id"]
        self.approve(operation_id)
        UserEntityAccess.objects.filter(pk=self.membership.id).update(updated_at=timezone.now() + timedelta(seconds=2))
        response = self.execute(operation_id)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["operation"]["failure"]["code"], "stale_approval")

    def test_request_is_idempotent(self):
        first = self.request_change()
        replay = self.request_change()
        self.assertEqual(first.status_code, 201)
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.data["replayed"])
        self.assertEqual(PlatformOperationRequest.objects.filter(
            operation_type=PlatformOperationRequest.OperationType.UPDATE_TENANT_MEMBERSHIP,
        ).count(), 1)
