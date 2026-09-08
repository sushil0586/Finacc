from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from Authentication.models import User
from platform_ops.models import PlatformOperationRequest, PlatformPermission, PlatformRole, PlatformUserRole
from subscriptions.models import CustomerAccount, CustomerSubscription, SubscriptionPlan


@override_settings(PLATFORM_OPS_ENABLED=True, PLATFORM_OPS_MUTATIONS_ENABLED=True)
class PlatformSubscriptionChangeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.maker = User.objects.create_user(username="plan-maker", email="plan-maker@example.com", password="Pass123!")
        cls.checker = User.objects.create_user(username="plan-checker", email="plan-checker@example.com", password="Pass123!")
        cls.executor = User.objects.create_user(username="plan-executor", email="plan-executor@example.com", password="Pass123!")
        cls.owner = User.objects.create_user(username="plan-owner", email="plan-owner@example.com", password="Pass123!")
        maker_role = PlatformRole.objects.create(code="plan-maker-role", name="Plan Maker")
        maker_role.permissions.add(PlatformPermission.objects.get(code="platform.subscription.change"))
        checker_role = PlatformRole.objects.create(code="plan-checker-role", name="Plan Checker")
        checker_role.permissions.add(PlatformPermission.objects.get(code="platform.operation.approve"))
        executor_role = PlatformRole.objects.create(code="plan-executor-role", name="Plan Executor")
        executor_role.permissions.add(PlatformPermission.objects.get(code="platform.operation.execute"))
        for user, role in ((cls.maker, maker_role), (cls.checker, checker_role), (cls.executor, executor_role)):
            PlatformUserRole.objects.create(user=user, role=role, granted_by=cls.maker, reason="Subscription change tests")
        cls.current_plan = SubscriptionPlan.objects.create(name="Current Plan", code="current-plan", price_amount="100.00")
        cls.new_plan = SubscriptionPlan.objects.create(name="New Plan", code="new-plan", price_amount="200.00")
        cls.inactive_plan = SubscriptionPlan.objects.create(name="Inactive Plan", code="inactive-plan", is_active=False)

    def setUp(self):
        self.client = APIClient()
        self.customer = CustomerAccount.objects.create(
            name="Plan Change Customer",
            slug=f"plan-change-{CustomerAccount.objects.count()}",
            owner=self.owner,
            status=CustomerAccount.Status.ACTIVE,
        )
        self.subscription = CustomerSubscription.objects.create(
            customer_account=self.customer,
            plan=self.current_plan,
            status=CustomerSubscription.Status.ACTIVE,
            current_period_start=timezone.now(),
        )

    def request_change(self, plan_code="new-plan", key="plan-change-1"):
        self.client.force_authenticate(self.maker)
        self.subscription.refresh_from_db()
        return self.client.post(
            f"/api/platform/customers/{self.customer.id}/subscription-change-requests/",
            {
                "idempotency_key": key,
                "reason": "Change subscription after approved commercial review",
                "ticket_reference": "BILL-3001",
                "expected_target_version": self.subscription.updated_at.isoformat(),
                "plan_code": plan_code,
            },
            format="json",
        )

    def approve(self, operation_id):
        self.client.force_authenticate(self.checker)
        return self.client.post(
            f"/api/platform/operations/{operation_id}/decision/",
            {"decision": "approved", "comment": "Commercial terms and target plan reviewed"},
            format="json",
        )

    def execute(self, operation_id):
        self.client.force_authenticate(self.executor)
        return self.client.post(f"/api/platform/operations/{operation_id}/execute/", {}, format="json")

    def test_approved_plan_change_closes_old_and_creates_one_current_subscription(self):
        requested = self.request_change()
        self.assertEqual(requested.status_code, 201)
        self.assertEqual(requested.data["operation"]["status"], "pending_approval")
        operation_id = requested.data["operation"]["id"]
        self.assertEqual(self.execute(operation_id).status_code, 400)
        self.assertEqual(self.approve(operation_id).status_code, 200)

        executed = self.execute(operation_id)
        replayed = self.execute(operation_id)

        self.assertEqual(executed.status_code, 200)
        self.assertTrue(replayed.data["replayed"])
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, CustomerSubscription.Status.CANCELED)
        self.assertIsNotNone(self.subscription.ended_at)
        current = self.customer.subscriptions.filter(is_active=True, ended_at__isnull=True).get()
        self.assertEqual(current.plan, self.new_plan)
        self.assertEqual(executed.data["operation"]["result"]["before"]["subscription_id"], self.subscription.id)
        self.assertEqual(executed.data["operation"]["result"]["after"]["subscription_id"], current.id)

    def test_same_or_inactive_plan_is_rejected(self):
        same = self.request_change(plan_code="current-plan", key="same-plan")
        inactive = self.request_change(plan_code="inactive-plan", key="inactive-plan")

        self.assertEqual(same.status_code, 400)
        self.assertEqual(inactive.status_code, 400)
        self.assertIn("plan_code", same.data)
        self.assertIn("plan_code", inactive.data)

    def test_stale_subscription_is_rejected_at_request(self):
        stale_version = self.subscription.updated_at
        CustomerSubscription.objects.filter(pk=self.subscription.id).update(updated_at=timezone.now() + timedelta(seconds=1))
        self.client.force_authenticate(self.maker)
        response = self.client.post(
            f"/api/platform/customers/{self.customer.id}/subscription-change-requests/",
            {
                "idempotency_key": "stale-request",
                "reason": "Change subscription after approved commercial review",
                "ticket_reference": "BILL-3002",
                "expected_target_version": stale_version.isoformat(),
                "plan_code": "new-plan",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("expected_target_version", response.data)

    def test_change_after_approval_invalidates_execution(self):
        operation_id = self.request_change().data["operation"]["id"]
        self.approve(operation_id)
        CustomerSubscription.objects.filter(pk=self.subscription.id).update(updated_at=timezone.now() + timedelta(seconds=1))

        response = self.execute(operation_id)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["operation"]["failure"]["code"], "stale_approval")
        self.assertFalse(self.customer.subscriptions.filter(plan=self.new_plan).exists())

    def test_idempotent_request_replays_without_duplicate_operation(self):
        first = self.request_change()
        replay = self.request_change()

        self.assertEqual(first.status_code, 201)
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.data["replayed"])
        self.assertEqual(PlatformOperationRequest.objects.filter(
            operation_type=PlatformOperationRequest.OperationType.CHANGE_SUBSCRIPTION_PLAN,
        ).count(), 1)
