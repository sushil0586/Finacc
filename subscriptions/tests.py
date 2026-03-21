from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from Authentication.models import User
from entity.models import Entity

from .models import CustomerAccount, CustomerSubscription, PlanLimit, UserEntityAccess
from .services import SubscriptionLimitCodes, SubscriptionService


class SubscriptionServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="owner@example.com",
            email="owner@example.com",
            password="secret123",
            first_name="Owner",
        )
        self.member = User.objects.create_user(
            username="member@example.com",
            email="member@example.com",
            password="secret123",
        )

    def test_signup_creates_customer_account_and_subscription(self):
        account = SubscriptionService.handle_signup(user=self.user)

        self.assertEqual(account.owner, self.user)
        self.assertTrue(CustomerSubscription.objects.filter(customer_account=account).exists())
        self.assertTrue(
            UserEntityAccess.objects.filter(
                customer_account=account,
                user=self.user,
                role=UserEntityAccess.Role.OWNER,
            ).exists()
        )

    def test_register_entity_creation_links_customer_account_and_access(self):
        entity = Entity.objects.create(entityname="Demo Entity", createdby=self.user)

        account = SubscriptionService.register_entity_creation(entity=entity, owner=self.user)

        entity.refresh_from_db()
        self.assertEqual(entity.customer_account, account)
        self.assertTrue(
            UserEntityAccess.objects.filter(
                customer_account=account,
                user=self.user,
                role=UserEntityAccess.Role.OWNER,
            ).exists()
        )

    def test_trialing_subscription_auto_moves_to_active_after_trial_end(self):
        plan = SubscriptionService.get_or_create_default_plan()
        plan.trial_days = 1
        plan.save(update_fields=["trial_days", "updated_at"])

        account = SubscriptionService.ensure_customer_account(user=self.user, intent=SubscriptionService.INTENT_TRIAL)
        subscription = SubscriptionService.ensure_active_subscription(
            customer_account=account,
            intent=SubscriptionService.INTENT_TRIAL,
        )
        subscription.status = CustomerSubscription.Status.TRIALING
        subscription.trial_ends_at = timezone.now() - timedelta(days=1)
        subscription.auto_renew = True
        subscription.save(update_fields=["status", "trial_ends_at", "auto_renew", "updated_at"])

        refreshed = SubscriptionService.ensure_active_subscription(customer_account=account)

        self.assertEqual(refreshed.id, subscription.id)
        self.assertEqual(refreshed.status, CustomerSubscription.Status.ACTIVE)

    def test_trialing_subscription_without_auto_renew_becomes_expired(self):
        plan = SubscriptionService.get_or_create_default_plan()
        plan.trial_days = 1
        plan.save(update_fields=["trial_days", "updated_at"])

        account = SubscriptionService.ensure_customer_account(user=self.user, intent=SubscriptionService.INTENT_TRIAL)
        subscription = SubscriptionService.ensure_active_subscription(
            customer_account=account,
            intent=SubscriptionService.INTENT_TRIAL,
        )
        subscription.status = CustomerSubscription.Status.TRIALING
        subscription.trial_ends_at = timezone.now() - timedelta(days=1)
        subscription.auto_renew = False
        subscription.save(update_fields=["status", "trial_ends_at", "auto_renew", "updated_at"])

        refreshed = SubscriptionService.ensure_active_subscription(customer_account=account)

        self.assertEqual(refreshed.id, subscription.id)
        self.assertEqual(refreshed.status, CustomerSubscription.Status.EXPIRED)

    def test_invite_limit_counts_only_non_expired_memberships(self):
        account = SubscriptionService.ensure_customer_account(user=self.user)
        plan = SubscriptionService.get_or_create_default_plan()
        PlanLimit.objects.update_or_create(
            plan=plan,
            key=SubscriptionLimitCodes.MAX_ENTITY_USERS,
            defaults={"limit_type": PlanLimit.LimitType.INTEGER, "int_value": 2},
        )

        entity = Entity.objects.create(entityname="Demo Entity", createdby=self.user, customer_account=account)
        UserEntityAccess.objects.update_or_create(
            user=self.member,
            customer_account=account,
            defaults={
                "role": UserEntityAccess.Role.MEMBER,
                "is_active": True,
                "expires_at": timezone.now() - timedelta(days=1),
                "granted_by": self.user,
            },
        )

        another = User.objects.create_user(username="new@example.com", email="new@example.com", password="secret123")
        created_access = SubscriptionService.register_user_invite(entity=entity, user=another, invited_by=self.user)

        self.assertEqual(created_access.role, UserEntityAccess.Role.MEMBER)

    def test_create_entity_blocked_when_account_inactive(self):
        account = SubscriptionService.ensure_customer_account(user=self.user)
        account.status = CustomerAccount.Status.SUSPENDED
        account.save(update_fields=["status", "updated_at"])

        with self.assertRaises(ValidationError) as exc:
            SubscriptionService.assert_can_create_entity(user=self.user)

        self.assertEqual(exc.exception.detail.get("code"), "subscription_account_inactive")

    def test_create_entity_blocked_when_subscription_expired(self):
        account = SubscriptionService.ensure_customer_account(user=self.user)
        sub = SubscriptionService.ensure_active_subscription(customer_account=account)
        sub.status = CustomerSubscription.Status.EXPIRED
        sub.ended_at = None
        sub.auto_renew = False
        sub.save(update_fields=["status", "ended_at", "auto_renew", "updated_at"])

        with self.assertRaises(ValidationError) as exc:
            SubscriptionService.assert_can_create_entity(user=self.user)

        self.assertEqual(exc.exception.detail.get("code"), "subscription_inactive")
