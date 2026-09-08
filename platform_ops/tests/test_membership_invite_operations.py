from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from Authentication.models import AuthOTP, User
from entity.models import Entity
from platform_ops.models import PlatformOperationRequest, PlatformPermission, PlatformRole, PlatformUserRole
from subscriptions.models import CustomerAccount, CustomerSubscription, SubscriptionPlan, UserEntityAccess


@override_settings(PLATFORM_OPS_ENABLED=True, PLATFORM_OPS_MUTATIONS_ENABLED=True)
class PlatformMembershipInviteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.maker = User.objects.create_user(username="invite-maker", email="invite-maker@example.com", password="Pass123!")
        cls.executor = User.objects.create_user(username="invite-executor", email="invite-executor@example.com", password="Pass123!")
        cls.owner = User.objects.create_user(username="invite-owner", email="invite-owner@example.com", password="Pass123!")
        maker_role = PlatformRole.objects.create(code="invite-maker-role", name="Invitation Maker")
        maker_role.permissions.add(PlatformPermission.objects.get(code="platform.membership.manage"))
        executor_role = PlatformRole.objects.create(code="invite-executor-role", name="Invitation Executor")
        executor_role.permissions.add(PlatformPermission.objects.get(code="platform.operation.execute"))
        PlatformUserRole.objects.create(user=cls.maker, role=maker_role, granted_by=cls.maker, reason="Invite tests")
        PlatformUserRole.objects.create(user=cls.executor, role=executor_role, granted_by=cls.maker, reason="Invite tests")
        cls.plan = SubscriptionPlan.objects.create(name="Invite Plan", code="invite-plan", price_amount="100.00")

    def setUp(self):
        self.client = APIClient()
        self.customer = CustomerAccount.objects.create(
            name="Invite Customer", slug=f"invite-{CustomerAccount.objects.count()}", owner=self.owner,
            status=CustomerAccount.Status.ACTIVE,
        )
        self.entity = Entity.objects.create(
            entityname="Invite Entity", entity_code=f"INV-{self.customer.id}", customer_account=self.customer, createdby=self.owner,
        )
        CustomerSubscription.objects.create(
            customer_account=self.customer, plan=self.plan, status=CustomerSubscription.Status.ACTIVE,
            current_period_start=timezone.now(),
        )
        self.expiry = timezone.now() + timedelta(days=30)

    def request_invite(self, *, email="new.member@example.com", key="invite-1", version=None):
        self.client.force_authenticate(self.maker)
        self.customer.refresh_from_db()
        return self.client.post(
            f"/api/platform/customers/{self.customer.id}/membership-invite-requests/",
            {
                "idempotency_key": key,
                "reason": "Invite user after approved customer access request",
                "ticket_reference": "IAM-5001",
                "expected_target_version": (version or self.customer.updated_at).isoformat(),
                "email": email,
                "first_name": "New",
                "last_name": "Member",
                "role": "viewer",
                "expires_at": self.expiry.isoformat(),
            }, format="json",
        )

    def execute(self, operation_id):
        self.client.force_authenticate(self.executor)
        return self.client.post(f"/api/platform/operations/{operation_id}/execute/", {}, format="json")

    def test_new_identity_invite_creates_secure_membership_and_verification(self):
        requested = self.request_invite()
        self.assertEqual(requested.status_code, 201)
        self.assertEqual(requested.data["operation"]["status"], "validated")
        executed = self.execute(requested.data["operation"]["id"])
        replay = self.execute(requested.data["operation"]["id"])
        self.assertEqual(executed.status_code, 200)
        self.assertTrue(replay.data["replayed"])
        user = User.objects.get(email="new.member@example.com")
        self.assertFalse(user.has_usable_password())
        self.assertFalse(user.email_verified)
        membership = UserEntityAccess.objects.get(customer_account=self.customer, user=user)
        self.assertEqual(membership.role, UserEntityAccess.Role.VIEWER)
        self.assertEqual(membership.metadata["invite_last_sent_by_id"], self.maker.id)
        self.assertTrue(AuthOTP.objects.filter(user=user, purpose="email_verification").exists())

    def test_existing_verified_identity_is_reused_without_otp(self):
        existing = User.objects.create_user(username="existing-member", email="existing@example.com", password="Pass123!", email_verified=True)
        requested = self.request_invite(email=existing.email, key="existing-invite")
        executed = self.execute(requested.data["operation"]["id"])
        self.assertEqual(executed.status_code, 200)
        self.assertFalse(executed.data["operation"]["result"]["created_user"])
        self.assertTrue(UserEntityAccess.objects.filter(customer_account=self.customer, user=existing).exists())
        self.assertFalse(AuthOTP.objects.filter(user=existing, purpose="email_verification").exists())

    def test_duplicate_membership_is_rejected_and_request_replays(self):
        first = self.request_invite()
        replay = self.request_invite()
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.data["replayed"])
        self.execute(first.data["operation"]["id"])
        duplicate = self.request_invite(key="duplicate-after-execute")
        self.assertEqual(duplicate.status_code, 400)
        self.assertIn("email", duplicate.data)
        self.assertEqual(PlatformOperationRequest.objects.filter(
            operation_type=PlatformOperationRequest.OperationType.INVITE_TENANT_USER,
        ).count(), 1)

    def test_customer_change_invalidates_execution(self):
        requested = self.request_invite()
        CustomerAccount.objects.filter(pk=self.customer.id).update(updated_at=timezone.now() + timedelta(seconds=2))
        response = self.execute(requested.data["operation"]["id"])
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["operation"]["failure"]["code"], "stale_target")
        self.assertFalse(User.objects.filter(email="new.member@example.com").exists())
