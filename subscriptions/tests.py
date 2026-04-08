from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework import status
from rest_framework.test import APITestCase

from Authentication.models import User
from entity.models import Entity

from .models import CustomerAccount, CustomerSubscription, PlanLimit, UserEntityAccess
from .services import SubscriptionLimitCodes, SubscriptionService
from rbac.models import Permission, Role, RolePermission, UserRoleAssignment


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

        self.assertEqual(exc.exception.detail.get("code"), "subscription_account_setup_inactive")

    def test_create_entity_allowed_when_account_pending(self):
        account = SubscriptionService.ensure_customer_account(user=self.user)
        account.status = CustomerAccount.Status.PENDING
        account.save(update_fields=["status", "updated_at"])

        allowed_account = SubscriptionService.assert_can_create_entity(user=self.user)

        self.assertEqual(allowed_account.id, account.id)

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

    def test_get_all_plan_limits_returns_catalog_defaults(self):
        account = SubscriptionService.ensure_customer_account(user=self.user)

        limits = SubscriptionService.get_all_plan_limits(customer_account=account)

        self.assertEqual(limits[SubscriptionLimitCodes.MAX_ENTITIES], 1)
        self.assertEqual(limits[SubscriptionLimitCodes.MAX_ENTITY_USERS], 5)
        self.assertTrue(limits[SubscriptionLimitCodes.FEATURE_FINANCIAL])
        self.assertFalse(limits[SubscriptionLimitCodes.FEATURE_PAYROLL])

    def test_subscription_snapshot_exposes_feature_flags(self):
        account = SubscriptionService.ensure_customer_account(user=self.user)

        snapshot = SubscriptionService.build_subscription_snapshot(customer_account=account)

        self.assertTrue(snapshot["features"][SubscriptionLimitCodes.FEATURE_FINANCIAL])
        self.assertFalse(snapshot["features"][SubscriptionLimitCodes.FEATURE_PAYROLL])

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
        entity = Entity.objects.create(entityname="Feature Entity", createdby=self.user, customer_account=account)
        subscription = SubscriptionService.ensure_active_subscription(customer_account=account)
        purchase_limit = subscription.plan.limits.get(key=SubscriptionLimitCodes.FEATURE_PURCHASE)
        purchase_limit.bool_value = False
        purchase_limit.save(update_fields=["bool_value", "updated_at"])

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
