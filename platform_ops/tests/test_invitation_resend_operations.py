from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from Authentication.models import AuthOTP, User
from platform_ops.models import PlatformPermission, PlatformRole, PlatformUserRole
from subscriptions.models import CustomerAccount, UserEntityAccess


@override_settings(PLATFORM_OPS_ENABLED=True, PLATFORM_OPS_MUTATIONS_ENABLED=True)
class PlatformInvitationResendTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.maker = User.objects.create_user(username="resend-maker", email="resend-maker@example.com", password="Pass123!")
        cls.executor = User.objects.create_user(username="resend-executor", email="resend-executor@example.com", password="Pass123!")
        cls.owner = User.objects.create_user(username="resend-owner", email="resend-owner@example.com", password="Pass123!")
        maker_role = PlatformRole.objects.create(code="resend-maker-role", name="Resend Maker")
        maker_role.permissions.add(PlatformPermission.objects.get(code="platform.membership.manage"))
        executor_role = PlatformRole.objects.create(code="resend-executor-role", name="Resend Executor")
        executor_role.permissions.add(PlatformPermission.objects.get(code="platform.operation.execute"))
        PlatformUserRole.objects.create(user=cls.maker, role=maker_role, granted_by=cls.maker, reason="Resend tests")
        PlatformUserRole.objects.create(user=cls.executor, role=executor_role, granted_by=cls.maker, reason="Resend tests")

    def setUp(self):
        self.client = APIClient()
        self.customer = CustomerAccount.objects.create(
            name="Resend Customer", slug=f"resend-{CustomerAccount.objects.count()}", owner=self.owner,
        )
        self.user = User.objects.create_user(
            username=f"pending-{self.customer.id}", email=f"pending-{self.customer.id}@example.com",
            password=None, email_verified=False,
        )
        self.membership = UserEntityAccess.objects.create(
            customer_account=self.customer, user=self.user, role=UserEntityAccess.Role.MEMBER,
            metadata={"invite_last_sent_at": (timezone.now() - timedelta(minutes=5)).isoformat()},
        )

    def request_resend(self, *, key="resend-1", version=None):
        self.client.force_authenticate(self.maker)
        self.membership.refresh_from_db()
        return self.client.post(
            f"/api/platform/customers/{self.customer.id}/memberships/{self.membership.id}/invitation-resend-requests/",
            {
                "idempotency_key": key,
                "reason": "Resend verification after approved support request",
                "ticket_reference": "IAM-6001",
                "expected_target_version": (version or self.membership.updated_at).isoformat(),
            }, format="json",
        )

    def execute(self, operation_id):
        self.client.force_authenticate(self.executor)
        return self.client.post(f"/api/platform/operations/{operation_id}/execute/", {}, format="json")

    def test_resend_generates_one_otp_and_execution_replays(self):
        requested = self.request_resend()
        self.assertEqual(requested.status_code, 201)
        executed = self.execute(requested.data["operation"]["id"])
        otp_id = AuthOTP.objects.get(user=self.user, purpose="email_verification").id
        replay = self.execute(requested.data["operation"]["id"])
        self.assertEqual(executed.status_code, 200)
        self.assertTrue(replay.data["replayed"])
        self.assertEqual(AuthOTP.objects.get(user=self.user, purpose="email_verification").id, otp_id)
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.metadata["invite_resend_count"], 1)
        self.assertNotIn("otp", executed.data["operation"]["result"])

    def test_cooldown_and_daily_limit_are_enforced(self):
        now = timezone.now()
        self.membership.metadata = {"platform_invite_resend_history": [(now - timedelta(seconds=20)).isoformat()]}
        self.membership.save(update_fields=["metadata", "updated_at"])
        self.assertEqual(self.request_resend(key="cooldown").status_code, 400)
        self.membership.metadata = {
            "platform_invite_resend_history": [(now - timedelta(hours=index + 1)).isoformat() for index in range(5)]
        }
        self.membership.save(update_fields=["metadata", "updated_at"])
        self.assertEqual(self.request_resend(key="daily-limit").status_code, 400)

    def test_verified_inactive_expired_and_owner_targets_are_blocked(self):
        self.user.email_verified = True
        self.user.save(update_fields=["email_verified", "updated_at"])
        self.assertEqual(self.request_resend(key="verified").status_code, 400)
        self.user.email_verified = False
        self.user.save(update_fields=["email_verified", "updated_at"])
        self.membership.is_active = False
        self.membership.save(update_fields=["is_active", "updated_at"])
        self.assertEqual(self.request_resend(key="inactive").status_code, 400)
        self.membership.is_active = True
        self.membership.expires_at = timezone.now() - timedelta(minutes=1)
        self.membership.save(update_fields=["is_active", "expires_at", "updated_at"])
        self.assertEqual(self.request_resend(key="expired").status_code, 400)
        self.membership.user = self.owner
        self.membership.role = UserEntityAccess.Role.OWNER
        self.membership.expires_at = None
        self.membership.save(update_fields=["user", "role", "expires_at", "updated_at"])
        self.assertEqual(self.request_resend(key="owner").status_code, 400)

    def test_stale_membership_invalidates_execution(self):
        requested = self.request_resend()
        UserEntityAccess.objects.filter(pk=self.membership.id).update(updated_at=timezone.now() + timedelta(seconds=2))
        response = self.execute(requested.data["operation"]["id"])
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["operation"]["failure"]["code"], "stale_target")
        self.assertFalse(AuthOTP.objects.filter(user=self.user, purpose="email_verification").exists())
