from datetime import timedelta

from django.core import mail
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from django.db import connection
from rest_framework.exceptions import ValidationError
from rest_framework import status
from rest_framework.test import APITestCase

from Authentication.models import User
from entity.models import Entity

from .models import CustomerAccount, CustomerSubscription, PlanLimit, SubscriptionPlan, UserEntityAccess
from .services import SubscriptionLimitCodes, SubscriptionService
from rbac.models import Permission, RBACAuditLog, Role, RolePermission, UserRoleAssignment


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
        self.assertEqual(account.legal_name, "Owner")
        self.assertEqual(account.trade_name, "Owner")
        self.assertEqual(account.primary_contact_name, "Owner")
        self.assertEqual(account.primary_contact_email, "owner@example.com")
        self.assertEqual(account.billing_contact_name, "Owner")
        self.assertEqual(account.billing_email, "owner@example.com")
        self.assertTrue(CustomerSubscription.objects.filter(customer_account=account).exists())
        self.assertTrue(
            UserEntityAccess.objects.filter(
                customer_account=account,
                user=self.user,
                role=UserEntityAccess.Role.OWNER,
            ).exists()
        )

    def test_signup_persists_selected_plan_and_intent_metadata(self):
        starter = SubscriptionService.get_or_create_default_plan()
        growth = SubscriptionPlan.objects.create(
            code="growth-signup",
            name="Growth Signup",
            description="Growth plan for signup persistence coverage",
            tier=starter.PlanTier.PRO,
            billing_interval=starter.BillingInterval.MONTHLY,
            price_amount="1999.00",
            currency="INR",
            trial_days=14,
            is_public=True,
            is_default=False,
            is_selectable_for_signup=True,
        )
        SubscriptionService.ensure_plan_limit_catalog(plan=growth)

        account = SubscriptionService.handle_signup(
            user=self.user,
            intent=SubscriptionService.INTENT_TRIAL,
            plan_code=growth.code,
        )
        subscription = account.subscriptions.get()

        self.assertEqual(account.metadata["signup_intent"], SubscriptionService.INTENT_TRIAL)
        self.assertEqual(account.metadata["selected_plan_code"], growth.code)
        self.assertEqual(subscription.plan.code, growth.code)
        self.assertEqual(subscription.metadata["signup_intent"], SubscriptionService.INTENT_TRIAL)
        self.assertEqual(subscription.metadata["selected_plan_code"], growth.code)
        self.assertEqual(subscription.status, CustomerSubscription.Status.TRIALING)

    def test_get_selectable_plan_rejects_existing_plan_when_not_signup_selectable(self):
        starter = SubscriptionService.get_or_create_default_plan()
        invite_only = SubscriptionPlan.objects.create(
            code="invite-only-growth",
            name="Invite Only Growth",
            description="Plan exists but is not signup selectable",
            tier=starter.PlanTier.PRO,
            billing_interval=starter.BillingInterval.MONTHLY,
            price_amount="1499.00",
            currency="INR",
            trial_days=0,
            is_public=True,
            is_default=False,
            is_selectable_for_signup=False,
        )
        SubscriptionService.ensure_plan_limit_catalog(plan=invite_only)

        with self.assertRaises(ValidationError) as exc:
            SubscriptionService.get_selectable_plan(code=invite_only.code)

        self.assertEqual(exc.exception.detail.get("code"), "subscription_plan_unavailable")
        self.assertEqual(exc.exception.detail.get("plan_code"), invite_only.code)

    def test_existing_account_signup_refreshes_selected_plan_metadata(self):
        account = SubscriptionService.handle_signup(user=self.user)

        starter = SubscriptionService.get_or_create_default_plan()
        upgrade = SubscriptionPlan.objects.create(
            code="starter-upgrade-choice",
            name="Starter Upgrade Choice",
            description="Selectable plan metadata refresh coverage",
            tier=starter.PlanTier.PRO,
            billing_interval=starter.BillingInterval.MONTHLY,
            price_amount="999.00",
            currency="INR",
            trial_days=0,
            is_public=True,
            is_default=False,
            is_selectable_for_signup=True,
        )
        SubscriptionService.ensure_plan_limit_catalog(plan=upgrade)

        refreshed = SubscriptionService.handle_signup(
            user=self.user,
            intent=SubscriptionService.INTENT_STANDARD,
            plan_code=upgrade.code,
        )
        refreshed_subscription = SubscriptionService.ensure_active_subscription(
            customer_account=refreshed,
            intent=SubscriptionService.INTENT_STANDARD,
            plan_code=upgrade.code,
        )

        self.assertEqual(refreshed.id, account.id)
        self.assertEqual(refreshed.metadata["selected_plan_code"], upgrade.code)
        self.assertEqual(
            refreshed_subscription.metadata["selected_plan_code"],
            upgrade.code,
        )

    def test_only_one_default_plan_remains_after_marking_new_default(self):
        first = SubscriptionPlan.objects.create(
            code="default-a",
            name="Default A",
            description="First default plan",
            is_default=True,
            is_public=True,
            is_selectable_for_signup=True,
        )
        SubscriptionService.ensure_plan_limit_catalog(plan=first)

        second = SubscriptionPlan.objects.create(
            code="default-b",
            name="Default B",
            description="Second default plan",
            is_default=True,
            is_public=True,
            is_selectable_for_signup=True,
        )
        SubscriptionService.ensure_plan_limit_catalog(plan=second)

        first.refresh_from_db()
        second.refresh_from_db()

        self.assertFalse(first.is_default)
        self.assertTrue(second.is_default)
        self.assertEqual(SubscriptionPlan.objects.filter(is_default=True).count(), 1)

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

    def test_subscription_snapshot_exposes_trial_days_remaining(self):
        plan = SubscriptionService.get_or_create_default_plan()
        plan.trial_days = 3
        plan.save(update_fields=["trial_days", "updated_at"])

        account = SubscriptionService.ensure_customer_account(
            user=self.user,
            intent=SubscriptionService.INTENT_TRIAL,
        )
        subscription = SubscriptionService.ensure_active_subscription(
            customer_account=account,
            intent=SubscriptionService.INTENT_TRIAL,
        )
        subscription.status = CustomerSubscription.Status.TRIALING
        subscription.trial_ends_at = timezone.now() + timedelta(days=2, hours=1)
        subscription.save(update_fields=["status", "trial_ends_at", "updated_at"])

        snapshot = SubscriptionService.build_subscription_snapshot(customer_account=account)

        self.assertEqual(snapshot["subscription"]["status"], CustomerSubscription.Status.TRIALING)
        self.assertIsNotNone(snapshot["subscription"]["trial_days_remaining"])
        self.assertGreaterEqual(snapshot["subscription"]["trial_days_remaining"], 1)

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

        self.assertEqual(exc.exception.detail.get("code"), "subscription_account_setup_inactive")

    def test_create_entity_allowed_when_account_pending(self):
        account = SubscriptionService.ensure_customer_account(user=self.user)
        account.status = CustomerAccount.Status.PENDING
        account.save(update_fields=["status", "updated_at"])

        allowed_account = SubscriptionService.assert_can_create_entity(user=self.user)

        self.assertEqual(allowed_account.id, account.id)

    def test_create_entity_limit_error_exposes_contract_fields(self):
        account = SubscriptionService.ensure_customer_account(user=self.user)
        starter = SubscriptionService.get_or_create_default_plan()
        capped_plan = SubscriptionPlan.objects.create(
            code="entity-cap-1",
            name="Entity Cap 1",
            description="Dedicated plan for entity limit validation",
            tier=starter.PlanTier.PRO,
            billing_interval=starter.BillingInterval.MONTHLY,
            price_amount="499.00",
            currency="INR",
            trial_days=0,
            is_public=True,
            is_default=False,
            is_selectable_for_signup=True,
        )
        SubscriptionService.ensure_plan_limit_catalog(plan=capped_plan)
        PlanLimit.objects.update_or_create(
            plan=capped_plan,
            key=SubscriptionLimitCodes.MAX_ENTITIES,
            defaults={"limit_type": PlanLimit.LimitType.INTEGER, "int_value": 1},
        )
        SubscriptionService.change_plan(
            customer_account=account,
            new_plan=capped_plan,
            changed_by=self.user,
        )
        Entity.objects.create(
            entityname="Existing Entity",
            createdby=self.user,
            customer_account=account,
        )

        with self.assertRaises(ValidationError) as exc:
            SubscriptionService.assert_can_create_entity(user=self.user)

        self.assertEqual(exc.exception.detail.get("code"), "subscription_limit_exceeded")
        self.assertEqual(exc.exception.detail.get("limit_code"), SubscriptionLimitCodes.MAX_ENTITIES)
        self.assertEqual(int(exc.exception.detail.get("limit")), 1)
        self.assertEqual(int(exc.exception.detail.get("current")), 1)

    def test_operational_membership_rejects_pending_account(self):
        account = SubscriptionService.ensure_customer_account(user=self.user)
        account.status = CustomerAccount.Status.PENDING
        account.save(update_fields=["status", "updated_at"])
        entity = Entity.objects.create(
            entityname="Pending Entity",
            createdby=self.user,
            customer_account=account,
        )

        self.assertFalse(
            SubscriptionService.has_entity_membership(user=self.user, entity=entity)
        )

    def test_subscription_snapshot_exposes_tenant_access_flags(self):
        account = SubscriptionService.ensure_customer_account(user=self.user)
        account.status = CustomerAccount.Status.SUSPENDED
        account.save(update_fields=["status", "updated_at"])

        snapshot = SubscriptionService.build_subscription_snapshot(customer_account=account)

        self.assertFalse(snapshot["customer_account"]["setup_accessible"])
        self.assertFalse(snapshot["customer_account"]["operational_accessible"])
        self.assertTrue(snapshot["customer_account"]["billing_accessible"])

    def test_create_entity_blocked_when_subscription_expired(self):
        account = SubscriptionService.ensure_customer_account(user=self.user)
        sub = SubscriptionService.ensure_active_subscription(customer_account=account)
        sub.status = CustomerSubscription.Status.EXPIRED
        sub.ended_at = None
        sub.auto_renew = False
        sub.save(update_fields=["status", "ended_at", "auto_renew", "updated_at"])

        with self.assertRaises(ValidationError) as exc:
            SubscriptionService.assert_can_create_entity(user=self.user)

        self.assertEqual(exc.exception.detail.get("code"), "subscription_setup_inactive")

    def test_create_entity_allowed_when_subscription_past_due(self):
        account = SubscriptionService.ensure_customer_account(user=self.user)
        sub = SubscriptionService.ensure_active_subscription(customer_account=account)
        sub.status = CustomerSubscription.Status.PAST_DUE
        sub.save(update_fields=["status", "updated_at"])

        allowed_account = SubscriptionService.assert_can_create_entity(user=self.user)

        self.assertEqual(allowed_account.id, account.id)

    def test_operational_membership_rejects_paused_subscription(self):
        account = SubscriptionService.ensure_customer_account(user=self.user)
        sub = SubscriptionService.ensure_active_subscription(customer_account=account)
        sub.status = CustomerSubscription.Status.PAUSED
        sub.save(update_fields=["status", "updated_at"])
        entity = Entity.objects.create(
            entityname="Paused Entity",
            createdby=self.user,
            customer_account=account,
        )

        self.assertFalse(
            SubscriptionService.has_entity_membership(user=self.user, entity=entity)
        )

    def test_subscription_snapshot_exposes_subscription_access_flags(self):
        account = SubscriptionService.ensure_customer_account(user=self.user)
        sub = SubscriptionService.ensure_active_subscription(customer_account=account)
        sub.status = CustomerSubscription.Status.PAST_DUE
        sub.save(update_fields=["status", "updated_at"])

        snapshot = SubscriptionService.build_subscription_snapshot(customer_account=account)

        self.assertTrue(snapshot["subscription"]["setup_accessible"])
        self.assertTrue(snapshot["subscription"]["operational_accessible"])
        self.assertTrue(snapshot["subscription"]["billing_accessible"])

    def test_subscription_snapshot_exposes_status_and_limit_block_reasons(self):
        account = SubscriptionService.ensure_customer_account(user=self.user)
        starter = SubscriptionService.get_or_create_default_plan()
        capped_plan = SubscriptionPlan.objects.create(
            code="status-limit-block-plan",
            name="Status Limit Block Plan",
            description="Plan used to validate block reasons",
            tier=starter.PlanTier.PRO,
            billing_interval=starter.BillingInterval.MONTHLY,
            price_amount="699.00",
            currency="INR",
            trial_days=0,
            is_public=True,
            is_default=False,
            is_selectable_for_signup=True,
        )
        SubscriptionService.ensure_plan_limit_catalog(plan=capped_plan)
        PlanLimit.objects.update_or_create(
            plan=capped_plan,
            key=SubscriptionLimitCodes.MAX_ENTITIES,
            defaults={"limit_type": PlanLimit.LimitType.INTEGER, "int_value": 1},
        )
        SubscriptionService.change_plan(
            customer_account=account,
            new_plan=capped_plan,
            changed_by=self.user,
        )
        Entity.objects.create(
            entityname="Used Entity",
            createdby=self.user,
            customer_account=account,
        )

        sub = SubscriptionService.ensure_active_subscription(customer_account=account)
        sub.status = CustomerSubscription.Status.PAUSED
        sub.save(update_fields=["status", "updated_at"])

        snapshot = SubscriptionService.build_subscription_snapshot(customer_account=account)

        subscription_reason_codes = {
            row["code"] for row in snapshot["block_reasons"]["subscription"]
        }
        limit_reason_codes = {
            row["code"] for row in snapshot["block_reasons"]["limits"]
        }

        self.assertIn("subscription_paused", subscription_reason_codes)
        self.assertIn("max_entities_reached", limit_reason_codes)

    def test_owner_has_full_tenant_membership_capabilities(self):
        account = SubscriptionService.ensure_customer_account(user=self.user)

        self.assertTrue(SubscriptionService.can_manage_tenant(user=self.user, customer_account=account))
        self.assertTrue(SubscriptionService.can_manage_billing(user=self.user, customer_account=account))
        self.assertTrue(SubscriptionService.can_invite_members(user=self.user, customer_account=account))
        self.assertTrue(SubscriptionService.can_create_entities(user=self.user, customer_account=account))

    def test_billing_role_only_has_billing_capability(self):
        account = SubscriptionService.ensure_customer_account(user=self.user)
        SubscriptionService.ensure_account_membership(
            customer_account=account,
            user=self.member,
            role=UserEntityAccess.Role.BILLING,
            granted_by=self.user,
        )

        self.assertFalse(SubscriptionService.can_manage_tenant(user=self.member, customer_account=account))
        self.assertTrue(SubscriptionService.can_manage_billing(user=self.member, customer_account=account))
        self.assertFalse(SubscriptionService.can_invite_members(user=self.member, customer_account=account))
        self.assertFalse(SubscriptionService.can_create_entities(user=self.member, customer_account=account))

    def test_admin_role_can_invite_and_create_entities_but_not_billing(self):
        account = SubscriptionService.ensure_customer_account(user=self.user)
        SubscriptionService.ensure_account_membership(
            customer_account=account,
            user=self.member,
            role=UserEntityAccess.Role.ADMIN,
            granted_by=self.user,
        )

        self.assertTrue(SubscriptionService.can_manage_tenant(user=self.member, customer_account=account))
        self.assertFalse(SubscriptionService.can_manage_billing(user=self.member, customer_account=account))
        self.assertTrue(SubscriptionService.can_invite_members(user=self.member, customer_account=account))
        self.assertTrue(SubscriptionService.can_create_entities(user=self.member, customer_account=account))

    def test_member_cannot_invite_users(self):
        account = SubscriptionService.ensure_customer_account(user=self.user)
        entity = Entity.objects.create(entityname="Invite Entity", createdby=self.user, customer_account=account)
        SubscriptionService.ensure_account_membership(
            customer_account=account,
            user=self.member,
            role=UserEntityAccess.Role.MEMBER,
            granted_by=self.user,
        )

        another = User.objects.create_user(username="deny@example.com", email="deny@example.com", password="secret123")
        with self.assertRaises(ValidationError) as exc:
            SubscriptionService.register_user_invite(
                entity=entity,
                user=another,
                invited_by=self.member,
            )

        self.assertEqual(exc.exception.detail.get("code"), "tenant_membership_invite_denied")

    def test_default_plan_seeds_canonical_limit_catalog(self):
        plan = SubscriptionService.get_or_create_default_plan()

        self.assertTrue(PlanLimit.objects.filter(plan=plan, key=SubscriptionLimitCodes.MAX_ENTITIES).exists())
        self.assertTrue(PlanLimit.objects.filter(plan=plan, key=SubscriptionLimitCodes.MAX_ENTITY_USERS).exists())
        self.assertTrue(PlanLimit.objects.filter(plan=plan, key=SubscriptionLimitCodes.FEATURE_FINANCIAL).exists())
        self.assertTrue(PlanLimit.objects.filter(plan=plan, key=SubscriptionLimitCodes.FEATURE_PAYROLL).exists())

    def test_default_plan_normalizes_legacy_entity_limit_to_twenty(self):
        plan = SubscriptionService.get_or_create_default_plan()
        PlanLimit.objects.update_or_create(
            plan=plan,
            key=SubscriptionLimitCodes.MAX_ENTITIES,
            defaults={"limit_type": PlanLimit.LimitType.INTEGER, "int_value": 10},
        )

        SubscriptionService.get_or_create_default_plan()

        limit = PlanLimit.objects.get(plan=plan, key=SubscriptionLimitCodes.MAX_ENTITIES)
        self.assertEqual(limit.int_value, 20)

    def test_default_plan_preserves_explicit_core_feature_flag_overrides(self):
        plan = SubscriptionService.get_or_create_default_plan()
        for feature_key in SubscriptionService.DEFAULT_CORE_FEATURE_FLAGS:
            PlanLimit.objects.update_or_create(
                plan=plan,
                key=feature_key,
                defaults={"limit_type": PlanLimit.LimitType.BOOLEAN, "bool_value": False},
            )

        SubscriptionService.get_or_create_default_plan()

        for feature_key in SubscriptionService.DEFAULT_CORE_FEATURE_FLAGS:
            limit = PlanLimit.objects.get(plan=plan, key=feature_key)
            self.assertFalse(limit.bool_value, msg=f"{feature_key} should preserve explicit disabled override")

    def test_get_all_plan_limits_returns_catalog_defaults(self):
        account = SubscriptionService.ensure_customer_account(user=self.user)

        limits = SubscriptionService.get_all_plan_limits(customer_account=account)

        self.assertEqual(limits[SubscriptionLimitCodes.MAX_ENTITIES], 20)
        self.assertEqual(limits[SubscriptionLimitCodes.MAX_ENTITY_USERS], 5)
        self.assertTrue(limits[SubscriptionLimitCodes.FEATURE_FINANCIAL])
        self.assertTrue(limits[SubscriptionLimitCodes.FEATURE_PAYROLL])

    def test_subscription_snapshot_exposes_feature_flags(self):
        account = SubscriptionService.ensure_customer_account(user=self.user)

        snapshot = SubscriptionService.build_subscription_snapshot(customer_account=account)

        self.assertTrue(snapshot["features"][SubscriptionLimitCodes.FEATURE_FINANCIAL])
        self.assertTrue(snapshot["features"][SubscriptionLimitCodes.FEATURE_PAYROLL])
        self.assertEqual(snapshot["plan"]["code"], snapshot["subscription"]["plan_code"])
        self.assertIn("feature_summary", snapshot)
        self.assertIn("locked_features", snapshot)
        self.assertIn("quota_summary", snapshot)
        self.assertEqual(
            snapshot["quota_summary"]["entities"]["remaining"],
            snapshot["usage"]["entities_remaining"],
        )

    def test_subscription_snapshot_exposes_feature_summary_for_disabled_module(self):
        account = SubscriptionService.ensure_customer_account(user=self.user)
        starter = SubscriptionService.get_or_create_default_plan()
        feature_locked_plan = SubscriptionPlan.objects.create(
            code="feature-lock-payroll",
            name="Feature Lock Payroll",
            description="Plan used to validate disabled feature summaries",
            tier=starter.PlanTier.PRO,
            billing_interval=starter.BillingInterval.MONTHLY,
            price_amount="799.00",
            currency="INR",
            trial_days=0,
            is_public=True,
            is_default=False,
            is_selectable_for_signup=True,
        )
        SubscriptionService.ensure_plan_limit_catalog(plan=feature_locked_plan)
        PlanLimit.objects.update_or_create(
            plan=feature_locked_plan,
            key=SubscriptionLimitCodes.FEATURE_PAYROLL,
            defaults={"limit_type": PlanLimit.LimitType.BOOLEAN, "bool_value": False},
        )
        SubscriptionService.change_plan(
            customer_account=account,
            new_plan=feature_locked_plan,
            changed_by=self.user,
        )

        snapshot = SubscriptionService.build_subscription_snapshot(customer_account=account)

        payroll_summary = snapshot["feature_summary"][SubscriptionLimitCodes.FEATURE_PAYROLL]
        self.assertFalse(payroll_summary["enabled"])
        self.assertEqual(payroll_summary["block_reason"]["code"], "subscription_feature_disabled")
        self.assertEqual(
            payroll_summary["block_reason"]["feature_code"],
            SubscriptionLimitCodes.FEATURE_PAYROLL,
        )
        self.assertTrue(
            any(
                row["feature_code"] == SubscriptionLimitCodes.FEATURE_PAYROLL
                for row in snapshot["locked_features"]
            )
        )

    def test_subscription_snapshot_exposes_tenant_profile_fields(self):
        account = SubscriptionService.ensure_customer_account(user=self.user)
        account.primary_contact_phone = "9999999999"
        account.support_email = "support@example.com"
        account.status_reason = "Manual review"
        account.save(update_fields=["primary_contact_phone", "support_email", "status_reason", "updated_at"])

        snapshot = SubscriptionService.build_subscription_snapshot(customer_account=account)

        self.assertEqual(snapshot["customer_account"]["legal_name"], "Owner")
        self.assertEqual(snapshot["customer_account"]["primary_contact_phone"], "9999999999")
        self.assertEqual(snapshot["customer_account"]["support_email"], "support@example.com")
        self.assertEqual(snapshot["customer_account"]["status_reason"], "Manual review")

    def test_has_entity_membership_rejects_rbac_only_access(self):
        account = SubscriptionService.ensure_customer_account(user=self.user)
        entity = Entity.objects.create(
            entityname="Demo Entity",
            createdby=self.user,
            customer_account=account,
        )

        self.assertFalse(
            SubscriptionService.has_entity_membership(user=self.member, entity=entity)
        )

    def test_has_entity_membership_backfills_owner_membership(self):
        entity = Entity.objects.create(entityname="Owner Entity", createdby=self.user)

        allowed = SubscriptionService.has_entity_membership(
            user=self.user,
            entity=entity,
            backfill_owner=True,
        )

        entity.refresh_from_db()
        self.assertTrue(allowed)
        self.assertIsNotNone(entity.customer_account_id)
        self.assertTrue(
            UserEntityAccess.objects.filter(
                customer_account=entity.customer_account,
                user=self.user,
                role=UserEntityAccess.Role.OWNER,
                is_active=True,
            ).exists()
        )

    def test_assert_entity_access_allows_setup_for_pending_account(self):
        account = SubscriptionService.ensure_customer_account(user=self.user)
        account.status = CustomerAccount.Status.PENDING
        account.save(update_fields=["status", "updated_at"])
        entity = Entity.objects.create(entityname="Setup Entity", createdby=self.user, customer_account=account)

        resolved_account = SubscriptionService.assert_entity_access(
            user=self.user,
            entity=entity,
            access_mode=SubscriptionService.ACCESS_MODE_SETUP,
        )

        self.assertEqual(resolved_account.id, account.id)

    def test_assert_entity_access_blocks_operational_when_account_pending(self):
        account = SubscriptionService.ensure_customer_account(user=self.user)
        account.status = CustomerAccount.Status.PENDING
        account.save(update_fields=["status", "updated_at"])
        entity = Entity.objects.create(entityname="Pending Ops Entity", createdby=self.user, customer_account=account)

        with self.assertRaises(ValidationError) as exc:
            SubscriptionService.assert_entity_access(
                user=self.user,
                entity=entity,
                access_mode=SubscriptionService.ACCESS_MODE_OPERATIONAL,
            )

        self.assertEqual(exc.exception.detail.get("code"), "subscription_account_inactive")

    def test_assert_entity_access_blocks_disabled_feature(self):
        account = SubscriptionService.ensure_customer_account(user=self.user)
        starter = SubscriptionService.get_or_create_default_plan()
        feature_locked_plan = SubscriptionPlan.objects.create(
            code="feature-lock-purchase",
            name="Feature Lock Purchase",
            description="Plan used to validate purchase feature blocking",
            tier=starter.PlanTier.PRO,
            billing_interval=starter.BillingInterval.MONTHLY,
            price_amount="899.00",
            currency="INR",
            trial_days=0,
            is_public=True,
            is_default=False,
            is_selectable_for_signup=True,
        )
        SubscriptionService.ensure_plan_limit_catalog(plan=feature_locked_plan)
        PlanLimit.objects.update_or_create(
            plan=feature_locked_plan,
            key=SubscriptionLimitCodes.FEATURE_PURCHASE,
            defaults={"limit_type": PlanLimit.LimitType.BOOLEAN, "bool_value": False},
        )
        SubscriptionService.change_plan(
            customer_account=account,
            new_plan=feature_locked_plan,
            changed_by=self.user,
        )
        entity = Entity.objects.create(entityname="Feature Entity", createdby=self.user, customer_account=account)

        with self.assertRaises(ValidationError) as exc:
            SubscriptionService.assert_entity_access(
                user=self.user,
                entity=entity,
                feature_code=SubscriptionLimitCodes.FEATURE_PURCHASE,
            )

        self.assertEqual(exc.exception.detail.get("code"), "subscription_feature_disabled")


class TenantMembershipApiTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="tenant-owner",
            email="tenant-owner@example.com",
            password="Owner@12345",
            first_name="Tenant",
            last_name="Owner",
        )
        self.entity = Entity.objects.create(entityname="Tenant Entity", createdby=self.owner)
        self.account = SubscriptionService.register_entity_creation(entity=self.entity, owner=self.owner)
        self.role = Role.objects.create(
            entity=self.entity,
            name="Entity Admin",
            code="entity.admin.membership",
            role_level=Role.LEVEL_ENTITY,
            createdby=self.owner,
        )
        for code in ("admin.user.view", "admin.user.create", "admin.user.update", "admin.user.delete"):
            permission, _ = Permission.objects.get_or_create(
                code=code,
                defaults={
                    "name": code,
                    "module": "admin",
                    "resource": "user",
                    "action": code.rsplit(".", 1)[-1],
                },
            )
            RolePermission.objects.get_or_create(role=self.role, permission=permission)
        UserRoleAssignment.objects.create(
            user=self.owner,
            entity=self.entity,
            role=self.role,
            assigned_by=self.owner,
            is_primary=True,
        )
        self.client.force_authenticate(self.owner)

    def test_list_members_returns_owner_membership(self):
        response = self.client.get(
            reverse("subscriptions_api:admin-memberships"),
            {"entity": self.entity.id},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["entity_id"], self.entity.id)
        self.assertEqual(len(response.data["members"]), 1)
        self.assertEqual(response.data["members"][0]["email"], self.owner.email)
        self.assertIn("invitation_status", response.data["members"][0])
        self.assertIn("can_resend_invite", response.data["members"][0])
        self.assertTrue(response.data["members"][0]["is_current_user"])

    def test_create_membership_creates_user_and_membership(self):
        response = self.client.post(
            reverse("subscriptions_api:admin-memberships"),
            {
                "entity": self.entity.id,
                "email": "member1@example.com",
                "first_name": "Member",
                "last_name": "One",
                "username": "member.one",
                "password": "Member@12345",
                "role": UserEntityAccess.Role.MEMBER,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created_user = User.objects.get(email="member1@example.com")
        self.assertTrue(
            UserEntityAccess.objects.filter(
                customer_account=self.account,
                user=created_user,
                role=UserEntityAccess.Role.MEMBER,
                is_active=True,
            ).exists()
        )
        self.assertTrue(
            RBACAuditLog.objects.filter(
                entity=self.entity,
                object_type="tenant_membership",
                action=RBACAuditLog.ACTION_CREATE,
                message__icontains="member1@example.com",
            ).exists()
        )

    def test_create_membership_adds_existing_user_to_tenant(self):
        existing = User.objects.create_user(
            username="existing-member",
            email="existing-member@example.com",
            password="Existing@12345",
        )

        response = self.client.post(
            reverse("subscriptions_api:admin-memberships"),
            {
                "entity": self.entity.id,
                "email": existing.email,
                "role": UserEntityAccess.Role.ADMIN,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        membership = UserEntityAccess.objects.get(customer_account=self.account, user=existing)
        self.assertEqual(membership.role, UserEntityAccess.Role.ADMIN)

    def test_patch_membership_updates_role(self):
        member = User.objects.create_user(
            username="tenant-member",
            email="tenant-member@example.com",
            password="Tenant@12345",
        )
        membership = SubscriptionService.ensure_account_membership(
            customer_account=self.account,
            user=member,
            role=UserEntityAccess.Role.MEMBER,
            granted_by=self.owner,
        )

        response = self.client.patch(
            reverse("subscriptions_api:admin-membership-detail", args=[membership.id]) + f"?entity={self.entity.id}",
            {"role": UserEntityAccess.Role.ADMIN},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        membership.refresh_from_db()
        self.assertEqual(membership.role, UserEntityAccess.Role.ADMIN)
        self.assertTrue(
            RBACAuditLog.objects.filter(
                entity=self.entity,
                object_type="tenant_membership",
                object_id=membership.id,
                action=RBACAuditLog.ACTION_UPDATE,
                message__icontains="tenant-member@example.com",
            ).exists()
        )

    def test_patch_membership_blocks_self_management_to_prevent_lockout(self):
        self.account.owner = None
        self.account.save(update_fields=["owner", "updated_at"])
        owner_membership = UserEntityAccess.objects.get(customer_account=self.account, user=self.owner)
        owner_membership.role = UserEntityAccess.Role.ADMIN
        owner_membership.save(update_fields=["role", "updated_at"])

        response = self.client.patch(
            reverse("subscriptions_api:admin-membership-detail", args=[owner_membership.id]) + f"?entity={self.entity.id}",
            {"role": UserEntityAccess.Role.MEMBER},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "tenant_membership_self_management_denied")
        owner_membership.refresh_from_db()
        self.assertEqual(owner_membership.role, UserEntityAccess.Role.ADMIN)

    def test_patch_membership_blocks_owner_membership_with_code(self):
        owner_membership = UserEntityAccess.objects.get(customer_account=self.account, user=self.owner)

        response = self.client.patch(
            reverse("subscriptions_api:admin-membership-detail", args=[owner_membership.id]) + f"?entity={self.entity.id}",
            {"role": UserEntityAccess.Role.MEMBER},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "tenant_membership_owner_protected")
        self.assertEqual(response.data["detail"], "Owner membership cannot be changed here.")
        owner_membership.refresh_from_db()
        self.assertEqual(owner_membership.role, UserEntityAccess.Role.OWNER)

    def test_delete_membership_deactivates_membership_and_assignments(self):
        member = User.objects.create_user(
            username="tenant-assigned",
            email="tenant-assigned@example.com",
            password="Tenant@12345",
        )
        membership = SubscriptionService.ensure_account_membership(
            customer_account=self.account,
            user=member,
            role=UserEntityAccess.Role.MEMBER,
            granted_by=self.owner,
        )
        member_role = Role.objects.create(
            entity=self.entity,
            name="Member Role",
            code="entity.member.membership",
            role_level=Role.LEVEL_ENTITY,
            createdby=self.owner,
        )
        assignment = UserRoleAssignment.objects.create(
            user=member,
            entity=self.entity,
            role=member_role,
            assigned_by=self.owner,
            is_primary=False,
        )

        response = self.client.delete(
            reverse("subscriptions_api:admin-membership-detail", args=[membership.id]) + f"?entity={self.entity.id}"
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        membership.refresh_from_db()
        assignment.refresh_from_db()
        self.assertFalse(membership.is_active)
        self.assertFalse(assignment.isactive)
        self.assertTrue(
            RBACAuditLog.objects.filter(
                entity=self.entity,
                object_type="tenant_membership",
                object_id=membership.id,
                action=RBACAuditLog.ACTION_DEACTIVATE,
                message__icontains="tenant-assigned@example.com",
            ).exists()
        )

    def test_delete_membership_blocks_self_deactivation_to_prevent_lockout(self):
        self.account.owner = None
        self.account.save(update_fields=["owner", "updated_at"])
        owner_membership = UserEntityAccess.objects.get(customer_account=self.account, user=self.owner)
        owner_membership.role = UserEntityAccess.Role.ADMIN
        owner_membership.save(update_fields=["role", "updated_at"])

        response = self.client.delete(
            reverse("subscriptions_api:admin-membership-detail", args=[owner_membership.id]) + f"?entity={self.entity.id}"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "tenant_membership_self_deactivation_denied")
        owner_membership.refresh_from_db()
        self.assertTrue(owner_membership.is_active)

    def test_reset_membership_password_updates_password_and_revokes_sessions(self):
        member = User.objects.create_user(
            username="reset-member",
            email="reset-member@example.com",
            password="OldPass@12345",
        )
        membership = SubscriptionService.ensure_account_membership(
            customer_account=self.account,
            user=member,
            role=UserEntityAccess.Role.MEMBER,
            granted_by=self.owner,
        )

        response = self.client.post(
            reverse("subscriptions_api:admin-membership-reset-password", args=[membership.id]) + f"?entity={self.entity.id}",
            {"new_password": "NewPass@12345"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        member.refresh_from_db()
        self.assertTrue(member.check_password("NewPass@12345"))
        self.assertEqual(response.data["membership"]["email"], member.email)
        self.assertTrue(
            RBACAuditLog.objects.filter(
                entity=self.entity,
                object_type="tenant_membership",
                object_id=membership.id,
                action=RBACAuditLog.ACTION_UPDATE,
                changes__security_action="password_reset",
            ).exists()
        )

    def test_reset_membership_password_blocks_owner_membership(self):
        owner_membership = UserEntityAccess.objects.get(customer_account=self.account, user=self.owner)

        response = self.client.post(
            reverse("subscriptions_api:admin-membership-reset-password", args=[owner_membership.id]) + f"?entity={self.entity.id}",
            {"new_password": "NewPass@12345"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "tenant_membership_owner_protected")

    def test_reset_membership_password_blocks_inactive_membership(self):
        member = User.objects.create_user(
            username="inactive-reset-member",
            email="inactive-reset-member@example.com",
            password="OldPass@12345",
        )
        membership = SubscriptionService.ensure_account_membership(
            customer_account=self.account,
            user=member,
            role=UserEntityAccess.Role.MEMBER,
            granted_by=self.owner,
        )
        membership.is_active = False
        membership.save(update_fields=["is_active", "updated_at"])

        response = self.client.post(
            reverse("subscriptions_api:admin-membership-reset-password", args=[membership.id]) + f"?entity={self.entity.id}",
            {"new_password": "NewPass@12345"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "tenant_membership_inactive")

    def test_resend_invite_generates_verification_otp_and_stamps_metadata(self):
        mail.outbox = []
        member = User.objects.create_user(
            username="invite-member",
            email="invite-member@example.com",
            password="Invite@12345",
        )
        member.email_verified = False
        member.save(update_fields=["email_verified", "updated_at"])
        membership = SubscriptionService.ensure_account_membership(
            customer_account=self.account,
            user=member,
            role=UserEntityAccess.Role.MEMBER,
            granted_by=self.owner,
        )

        response = self.client.post(
            reverse("subscriptions_api:admin-membership-resend-invite", args=[membership.id]) + f"?entity={self.entity.id}",
            {"entity": self.entity.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["detail"], "Verification invite resent successfully.")
        self.assertFalse(response.data["membership"]["email_verified"])
        self.assertEqual(response.data["membership"]["invitation_status"], "pending_verification")
        self.assertTrue(response.data["membership"]["last_invite_sent_at"])
        membership.refresh_from_db()
        self.assertEqual(membership.metadata["invite_resend_count"], 1)
        self.assertEqual(membership.metadata["invite_last_sent_by_id"], self.owner.id)
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(
            RBACAuditLog.objects.filter(
                entity=self.entity,
                object_type="tenant_membership",
                object_id=membership.id,
                action=RBACAuditLog.ACTION_UPDATE,
                changes__security_action="resend_invite",
            ).exists()
        )

    def test_resend_invite_reports_already_verified_without_email(self):
        mail.outbox = []
        member = User.objects.create_user(
            username="verified-invite-member",
            email="verified-invite-member@example.com",
            password="Invite@12345",
        )
        member.email_verified = True
        member.save(update_fields=["email_verified", "updated_at"])
        membership = SubscriptionService.ensure_account_membership(
            customer_account=self.account,
            user=member,
            role=UserEntityAccess.Role.MEMBER,
            granted_by=self.owner,
        )

        response = self.client.post(
            reverse("subscriptions_api:admin-membership-resend-invite", args=[membership.id]) + f"?entity={self.entity.id}",
            {"entity": self.entity.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["detail"], "Email is already verified.")
        self.assertTrue(response.data["membership"]["email_verified"])
        self.assertEqual(response.data["membership"]["invitation_status"], "active")
        self.assertEqual(len(mail.outbox), 0)

    def test_resend_invite_blocks_expired_membership(self):
        member = User.objects.create_user(
            username="expired-invite-member",
            email="expired-invite-member@example.com",
            password="Invite@12345",
        )
        membership = SubscriptionService.ensure_account_membership(
            customer_account=self.account,
            user=member,
            role=UserEntityAccess.Role.MEMBER,
            granted_by=self.owner,
        )
        membership.expires_at = timezone.now() - timedelta(days=1)
        membership.save(update_fields=["expires_at", "updated_at"])

        response = self.client.post(
            reverse("subscriptions_api:admin-membership-resend-invite", args=[membership.id]) + f"?entity={self.entity.id}",
            {"entity": self.entity.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "tenant_membership_expired")

    def test_resend_invite_blocks_self_membership(self):
        self.account.owner = None
        self.account.save(update_fields=["owner", "updated_at"])
        owner_membership = UserEntityAccess.objects.get(customer_account=self.account, user=self.owner)
        owner_membership.role = UserEntityAccess.Role.ADMIN
        owner_membership.save(update_fields=["role", "updated_at"])

        response = self.client.post(
            reverse("subscriptions_api:admin-membership-resend-invite", args=[owner_membership.id]) + f"?entity={self.entity.id}",
            {"entity": self.entity.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "tenant_membership_self_invite_resend_denied")

    def test_membership_write_actions_require_matching_permission(self):
        view_only_role = Role.objects.create(
            entity=self.entity,
            name="View Only Membership",
            code="entity.view.only.membership",
            role_level=Role.LEVEL_ENTITY,
            createdby=self.owner,
        )
        update_permission = Permission.objects.get(code="admin.user.update")
        delete_permission = Permission.objects.get(code="admin.user.delete")
        RolePermission.objects.filter(role=self.role, permission__in=[update_permission, delete_permission]).delete()
        member = User.objects.create_user(
            username="permission-target",
            email="permission-target@example.com",
            password="Target@12345",
        )
        membership = SubscriptionService.ensure_account_membership(
            customer_account=self.account,
            user=member,
            role=UserEntityAccess.Role.MEMBER,
            granted_by=self.owner,
        )
        view_permission = Permission.objects.get(code="admin.user.view")
        RolePermission.objects.create(role=view_only_role, permission=view_permission)
        UserRoleAssignment.objects.filter(user=self.owner, entity=self.entity, role=self.role).delete()
        UserRoleAssignment.objects.create(
            user=self.owner,
            entity=self.entity,
            role=view_only_role,
            assigned_by=self.owner,
            is_primary=True,
        )

        patch_response = self.client.patch(
            reverse("subscriptions_api:admin-membership-detail", args=[membership.id]) + f"?entity={self.entity.id}",
            {"role": UserEntityAccess.Role.ADMIN},
            format="json",
        )
        delete_response = self.client.delete(
            reverse("subscriptions_api:admin-membership-detail", args=[membership.id]) + f"?entity={self.entity.id}"
        )
        reset_response = self.client.post(
            reverse("subscriptions_api:admin-membership-reset-password", args=[membership.id]) + f"?entity={self.entity.id}",
            {"new_password": "NewPass@12345"},
            format="json",
        )

        self.assertEqual(patch_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(delete_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(reset_response.status_code, status.HTTP_403_FORBIDDEN)


class SubscriptionPlanAdminApiTests(APITestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="staff-user",
            email="staff@example.com",
            password="Staff@12345",
            is_staff=True,
        )
        self.non_staff = User.objects.create_user(
            username="normal-user",
            email="normal@example.com",
            password="User@12345",
        )
        self.client.force_authenticate(self.staff)
        self.default_plan = SubscriptionService.get_or_create_default_plan()

    def test_staff_can_list_internal_plan_catalog(self):
        response = self.client.get(reverse("subscriptions_api:admin-plans"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(len(response.data["plans"]) >= 1)
        self.assertIn("raw_limits", response.data["plans"][0])

    def test_internal_plan_catalog_reuses_prefetched_limits_without_query_explosion(self):
        for index in range(3):
            plan = SubscriptionPlan.objects.create(
                code=f"catalog-bench-{index}",
                name=f"Catalog Bench {index}",
                description="Benchmark plan",
                is_public=True,
                is_default=False,
                is_selectable_for_signup=True,
            )
            SubscriptionService.ensure_plan_limit_catalog(plan=plan)

        with CaptureQueriesContext(connection) as ctx:
            payload = SubscriptionService.get_internal_plan_catalog()

        self.assertGreaterEqual(len(payload), 4)
        self.assertLessEqual(len(ctx.captured_queries), 12)

    def test_non_staff_cannot_access_plan_admin_api(self):
        self.client.force_authenticate(self.non_staff)

        response = self.client.get(reverse("subscriptions_api:admin-plans"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_can_create_plan_with_nested_limits(self):
        response = self.client.post(
            reverse("subscriptions_api:admin-plans"),
            {
                "code": "growth",
                "name": "Growth",
                "description": "Growth plan",
                "tier": SubscriptionPlan.PlanTier.PRO,
                "billing_interval": SubscriptionPlan.BillingInterval.MONTHLY,
                "price_amount": "1999.00",
                "currency": "INR",
                "trial_days": 14,
                "sort_order": 10,
                "is_public": True,
                "is_default": False,
                "is_selectable_for_signup": True,
                "is_active": True,
                "metadata": {"badge": "Popular"},
                "raw_limits": [
                    {
                        "key": SubscriptionLimitCodes.MAX_ENTITIES,
                        "label": "Maximum Entities",
                        "limit_type": PlanLimit.LimitType.INTEGER,
                        "int_value": 50,
                        "is_unlimited": False,
                    },
                    {
                        "key": SubscriptionLimitCodes.FEATURE_MANUFACTURING,
                        "label": "Manufacturing Module",
                        "limit_type": PlanLimit.LimitType.BOOLEAN,
                        "bool_value": True,
                        "is_unlimited": False,
                    },
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["code"], "growth")
        self.assertEqual(response.data["limits"][SubscriptionLimitCodes.MAX_ENTITIES], 50)
        self.assertTrue(response.data["features"][SubscriptionLimitCodes.FEATURE_MANUFACTURING])
        self.assertTrue(
            PlanLimit.objects.filter(plan__code="growth", key=SubscriptionLimitCodes.FEATURE_MANUFACTURING, bool_value=True).exists()
        )

    def test_staff_can_patch_existing_plan_and_limit_rows(self):
        plan = SubscriptionPlan.objects.create(
            code="pro-plus",
            name="Pro Plus",
            description="Advanced plan",
            is_public=True,
            is_default=False,
            is_selectable_for_signup=True,
        )
        SubscriptionService.ensure_plan_limit_catalog(plan=plan)

        response = self.client.patch(
            reverse("subscriptions_api:admin-plan-detail", kwargs={"plan_id": plan.id}),
            {
                "trial_days": 21,
                "raw_limits": [
                    {
                        "key": SubscriptionLimitCodes.MAX_ENTITY_USERS,
                        "label": "Maximum Tenant Users",
                        "limit_type": PlanLimit.LimitType.INTEGER,
                        "int_value": 35,
                        "is_unlimited": False,
                    },
                    {
                        "key": SubscriptionLimitCodes.FEATURE_ASSETS,
                        "label": "Assets Module",
                        "limit_type": PlanLimit.LimitType.BOOLEAN,
                        "bool_value": True,
                        "is_unlimited": False,
                    },
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["trial_days"], 21)
        self.assertEqual(response.data["limits"][SubscriptionLimitCodes.MAX_ENTITY_USERS], 35)
        self.assertTrue(response.data["features"][SubscriptionLimitCodes.FEATURE_ASSETS])

    def test_staff_can_promote_plan_to_default_via_api(self):
        plan = SubscriptionPlan.objects.create(
            code="new-default",
            name="New Default",
            description="Promoted to default through admin api",
            is_public=True,
            is_default=False,
            is_selectable_for_signup=True,
        )
        SubscriptionService.ensure_plan_limit_catalog(plan=plan)

        response = self.client.patch(
            reverse("subscriptions_api:admin-plan-detail", kwargs={"plan_id": plan.id}),
            {
                "is_default": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        plan.refresh_from_db()
        self.default_plan.refresh_from_db()
        self.assertTrue(plan.is_default)
        self.assertFalse(self.default_plan.is_default)

    def test_default_plan_cannot_be_deactivated(self):
        response = self.client.delete(
            reverse("subscriptions_api:admin-plan-detail", kwargs={"plan_id": self.default_plan.id})
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "default_plan_protected")

    def test_non_default_plan_can_be_soft_deactivated(self):
        plan = SubscriptionPlan.objects.create(
            code="legacy",
            name="Legacy",
            description="Legacy plan",
            is_public=False,
            is_default=False,
            is_selectable_for_signup=False,
        )

        response = self.client.delete(
            reverse("subscriptions_api:admin-plan-detail", kwargs={"plan_id": plan.id})
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        plan.refresh_from_db()
        self.assertFalse(plan.is_active)

    def test_admin_cannot_create_signup_selectable_plan_that_is_not_public(self):
        response = self.client.post(
            reverse("subscriptions_api:admin-plans"),
            {
                "code": "private-selectable",
                "name": "Private Selectable",
                "description": "Invalid commercial state",
                "tier": SubscriptionPlan.PlanTier.PRO,
                "billing_interval": SubscriptionPlan.BillingInterval.MONTHLY,
                "price_amount": "999.00",
                "currency": "INR",
                "trial_days": 0,
                "sort_order": 1,
                "is_public": False,
                "is_default": False,
                "is_selectable_for_signup": True,
                "is_active": True,
                "raw_limits": [
                    {
                        "key": SubscriptionLimitCodes.MAX_ENTITIES,
                        "label": "Maximum Entities",
                        "limit_type": PlanLimit.LimitType.INTEGER,
                        "int_value": 20,
                        "is_unlimited": False,
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("is_selectable_for_signup", response.data)

    def test_admin_cannot_patch_default_plan_into_hidden_or_unselectable_state(self):
        response = self.client.patch(
            reverse(
                "subscriptions_api:admin-plan-detail",
                kwargs={"plan_id": self.default_plan.id},
            ),
            {
                "is_public": False,
                "is_selectable_for_signup": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("is_public", response.data)
        self.assertIn("is_selectable_for_signup", response.data)


class SubscriptionAccountAdminApiTests(APITestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="billing-staff",
            email="billing-staff@example.com",
            password="Staff@12345",
            is_staff=True,
        )
        self.owner = User.objects.create_user(
            username="acct-owner",
            email="acct-owner@example.com",
            password="Owner@12345",
        )
        self.client.force_authenticate(self.staff)
        self.account = SubscriptionService.ensure_customer_account(user=self.owner)
        self.current_subscription = SubscriptionService.ensure_active_subscription(customer_account=self.account)
        self.alt_plan = SubscriptionPlan.objects.create(
            code="business-plus",
            name="Business Plus",
            description="Business plan",
            tier=SubscriptionPlan.PlanTier.BUSINESS,
            billing_interval=SubscriptionPlan.BillingInterval.MONTHLY,
            price_amount="4999.00",
            currency="INR",
            trial_days=0,
            is_public=True,
            is_default=False,
            is_selectable_for_signup=True,
        )
        SubscriptionService.ensure_plan_limit_catalog(plan=self.alt_plan)

    def test_staff_can_view_account_subscription_snapshot(self):
        response = self.client.get(
            reverse("subscriptions_api:admin-account-detail", kwargs={"account_id": self.account.id})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["customer_account"]["id"], self.account.id)
        self.assertEqual(
            response.data["subscription"]["plan_code"],
            self.current_subscription.plan.code,
        )

    def test_non_staff_cannot_view_account_subscription_snapshot(self):
        self.client.force_authenticate(self.owner)

        response = self.client.get(
            reverse("subscriptions_api:admin-account-detail", kwargs={"account_id": self.account.id})
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_can_change_account_plan(self):
        response = self.client.post(
            reverse("subscriptions_api:admin-account-change-plan", kwargs={"account_id": self.account.id}),
            {
                "plan_id": self.alt_plan.id,
                "status_reason": "Upgraded by support",
                "status_notes": "Customer requested higher tier on 2026-07-30",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.account.refresh_from_db()
        self.current_subscription.refresh_from_db()
        new_subscription = self.account.subscriptions.order_by("-id").first()
        self.assertEqual(new_subscription.plan_id, self.alt_plan.id)
        self.assertEqual(new_subscription.metadata["changed_by"], self.staff.id)
        self.assertEqual(new_subscription.metadata["selected_plan_code"], self.alt_plan.code)
        self.assertEqual(self.account.metadata["selected_plan_code"], self.alt_plan.code)
        self.assertEqual(self.current_subscription.status, CustomerSubscription.Status.CANCELED)
        self.assertEqual(response.data["snapshot"]["subscription"]["plan_code"], self.alt_plan.code)
        self.assertEqual(response.data["snapshot"]["plan"]["code"], self.alt_plan.code)
        self.assertEqual(self.account.status_reason, "Upgraded by support")

    def test_staff_plan_change_keeps_snapshot_and_current_subscription_metadata_in_sync(self):
        response = self.client.post(
            reverse("subscriptions_api:admin-account-change-plan", kwargs={"account_id": self.account.id}),
            {
                "plan_id": self.alt_plan.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.account.refresh_from_db()
        active_subscription = SubscriptionService.ensure_active_subscription(customer_account=self.account)
        owner_snapshot = SubscriptionService.build_subscription_snapshot(
            customer_account=self.account,
            user=self.owner,
        )

        self.assertEqual(self.account.metadata["selected_plan_code"], self.alt_plan.code)
        self.assertEqual(active_subscription.plan.code, self.alt_plan.code)
        self.assertEqual(active_subscription.metadata["selected_plan_code"], self.alt_plan.code)
        self.assertEqual(response.data["snapshot"]["subscription"]["plan_code"], self.alt_plan.code)
        self.assertEqual(response.data["snapshot"]["plan"]["code"], self.alt_plan.code)
        self.assertEqual(owner_snapshot["subscription"]["plan_code"], self.alt_plan.code)
        self.assertEqual(owner_snapshot["plan"]["code"], self.alt_plan.code)

    def test_staff_cannot_change_account_to_inactive_plan(self):
        self.alt_plan.is_active = False
        self.alt_plan.save(update_fields=["is_active", "updated_at"])

        response = self.client.post(
            reverse("subscriptions_api:admin-account-change-plan", kwargs={"account_id": self.account.id}),
            {
                "plan_id": self.alt_plan.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "subscription_plan_inactive")
        self.assertEqual(int(response.data["plan_id"]), self.alt_plan.id)

    def test_change_plan_requires_plan_id(self):
        response = self.client.post(
            reverse("subscriptions_api:admin-account-change-plan", kwargs={"account_id": self.account.id}),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("plan_id", response.data)

    def test_staff_can_cancel_account_subscription(self):
        response = self.client.post(
            reverse("subscriptions_api:admin-account-cancel", kwargs={"account_id": self.account.id}),
            {
                "status_reason": "Customer requested cancellation",
                "status_notes": "Canceled after onboarding review on 2026-07-30",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.account.refresh_from_db()
        self.current_subscription.refresh_from_db()
        self.assertEqual(self.current_subscription.status, CustomerSubscription.Status.CANCELED)
        self.assertFalse(self.current_subscription.auto_renew)
        self.assertEqual(self.current_subscription.metadata["canceled_by"], self.staff.id)
        self.assertEqual(response.data["snapshot"]["subscription"]["status"], CustomerSubscription.Status.CANCELED)
        self.assertEqual(self.account.status_reason, "Customer requested cancellation")

    def test_cancel_is_idempotent_when_subscription_is_already_canceled(self):
        first = self.client.post(
            reverse("subscriptions_api:admin-account-cancel", kwargs={"account_id": self.account.id}),
            format="json",
        )
        second = self.client.post(
            reverse("subscriptions_api:admin-account-cancel", kwargs={"account_id": self.account.id}),
            format="json",
        )

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(second.data["detail"], "No active subscription found.")
        self.assertIsNone(second.data["subscription_id"])
        self.assertEqual(
            second.data["snapshot"]["subscription"]["status"],
            CustomerSubscription.Status.CANCELED,
        )

    def test_non_staff_cannot_mutate_account_subscription(self):
        self.client.force_authenticate(self.owner)

        response = self.client.post(
            reverse("subscriptions_api:admin-account-cancel", kwargs={"account_id": self.account.id}),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class SubscriptionPublicApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="sub-api-user",
            email="sub-api-user@example.com",
            password="SubApi@12345",
            first_name="Sub",
            last_name="User",
        )

    def test_public_plan_catalog_returns_only_public_selectable_active_plans(self):
        starter = SubscriptionService.get_or_create_default_plan()
        starter.is_public = True
        starter.is_selectable_for_signup = True
        starter.save(update_fields=["is_public", "is_selectable_for_signup", "updated_at"])

        hidden = SubscriptionService.get_or_create_default_plan()
        hidden.pk = None
        hidden.code = "hidden-growth"
        hidden.name = "Hidden Growth"
        hidden.is_default = False
        hidden.is_public = False
        hidden.is_selectable_for_signup = True
        hidden.save()
        SubscriptionService.ensure_plan_limit_catalog(plan=hidden)

        invite_only = SubscriptionService.get_or_create_default_plan()
        invite_only.pk = None
        invite_only.code = "invite-only"
        invite_only.name = "Invite Only"
        invite_only.is_default = False
        invite_only.is_public = True
        invite_only.is_selectable_for_signup = False
        invite_only.save()
        SubscriptionService.ensure_plan_limit_catalog(plan=invite_only)

        inactive_public = SubscriptionService.get_or_create_default_plan()
        inactive_public.pk = None
        inactive_public.code = "inactive-public"
        inactive_public.name = "Inactive Public"
        inactive_public.is_default = False
        inactive_public.is_public = True
        inactive_public.is_selectable_for_signup = True
        inactive_public.is_active = False
        inactive_public.save()
        SubscriptionService.ensure_plan_limit_catalog(plan=inactive_public)

        response = self.client.get(reverse("subscriptions_api:public-plans"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        codes = [plan["code"] for plan in response.data["plans"]]
        self.assertIn(starter.code, codes)
        self.assertNotIn(hidden.code, codes)
        self.assertNotIn(invite_only.code, codes)
        self.assertNotIn(inactive_public.code, codes)

    def test_public_plan_catalog_is_sorted_and_exposes_frontend_contract_fields(self):
        starter = SubscriptionService.get_or_create_default_plan()
        starter.is_public = True
        starter.is_selectable_for_signup = True
        starter.sort_order = 10
        starter.price_amount = "1999.00"
        starter.metadata = {"badge": "Most Popular"}
        starter.save(update_fields=[
            "is_public",
            "is_selectable_for_signup",
            "sort_order",
            "price_amount",
            "metadata",
            "updated_at",
        ])

        earlier = SubscriptionPlan.objects.create(
            code="early-growth",
            name="Early Growth",
            description="Earlier in sort order",
            tier=SubscriptionPlan.PlanTier.PRO,
            billing_interval=SubscriptionPlan.BillingInterval.MONTHLY,
            price_amount="2999.00",
            currency="INR",
            trial_days=21,
            sort_order=5,
            is_public=True,
            is_default=False,
            is_selectable_for_signup=True,
            metadata={"badge": "Growth"},
        )
        SubscriptionService.ensure_plan_limit_catalog(plan=earlier)

        same_order_cheaper = SubscriptionPlan.objects.create(
            code="same-order-cheaper",
            name="Same Order Cheaper",
            description="Same sort order but lower price",
            tier=SubscriptionPlan.PlanTier.BUSINESS,
            billing_interval=SubscriptionPlan.BillingInterval.MONTHLY,
            price_amount="1499.00",
            currency="INR",
            trial_days=7,
            sort_order=10,
            is_public=True,
            is_default=False,
            is_selectable_for_signup=True,
            metadata={"badge": "Budget"},
        )
        SubscriptionService.ensure_plan_limit_catalog(plan=same_order_cheaper)

        response = self.client.get(reverse("subscriptions_api:public-plans"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        plans = response.data["plans"]
        self.assertGreaterEqual(len(plans), 3)
        self.assertEqual(
            [plan["code"] for plan in plans[:3]],
            ["early-growth", "same-order-cheaper", starter.code],
        )

        growth_payload = next(plan for plan in plans if plan["code"] == "early-growth")
        self.assertEqual(growth_payload["name"], "Early Growth")
        self.assertEqual(growth_payload["trial_days"], 21)
        self.assertEqual(growth_payload["sort_order"], 5)
        self.assertTrue(growth_payload["is_public"])
        self.assertTrue(growth_payload["is_selectable_for_signup"])
        self.assertIn("features", growth_payload)
        self.assertIn("limits", growth_payload)
        self.assertIn("metadata", growth_payload)
        self.assertIn(SubscriptionLimitCodes.FEATURE_PURCHASE, growth_payload["features"])
        self.assertIn(SubscriptionLimitCodes.MAX_ENTITIES, growth_payload["limits"])
        self.assertEqual(growth_payload["metadata"]["badge"], "Growth")

    def test_current_subscription_summary_returns_plan_and_quota_details(self):
        SubscriptionService.ensure_customer_account(user=self.user)
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse("subscriptions_api:current-summary"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["subscription"]["plan_code"], "starter")
        self.assertEqual(response.data["plan"]["code"], "starter")
        self.assertEqual(response.data["limits"][SubscriptionLimitCodes.MAX_ENTITIES], 20)
        self.assertIn("feature_summary", response.data)
        self.assertIn("locked_features", response.data)
        self.assertIn("quota_summary", response.data)
        self.assertIn("block_reasons", response.data)
        self.assertEqual(
            response.data["quota_summary"]["entities"]["limit"],
            response.data["limits"][SubscriptionLimitCodes.MAX_ENTITIES],
        )

    def test_current_subscription_summary_requires_authentication(self):
        response = self.client.get(reverse("subscriptions_api:current-summary"))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
