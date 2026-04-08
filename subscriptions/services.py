from datetime import timedelta
from django.apps import apps

from django.db.models import Q
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from entity.models import Entity

from .models import (
    CustomerAccount,
    CustomerSubscription,
    PlanLimit,
    SubscriptionPlan,
    UserEntityAccess,
)


class SubscriptionLimitCodes:
    MAX_ENTITIES = "max_entities"
    MAX_ENTITY_USERS = "max_entity_users"
    FEATURE_FINANCIAL = "feature_financial"
    FEATURE_INVENTORY = "feature_inventory"
    FEATURE_PURCHASE = "feature_purchase"
    FEATURE_SALES = "feature_sales"
    FEATURE_REPORTING = "feature_reporting"
    FEATURE_RBAC = "feature_rbac"
    FEATURE_PAYROLL = "feature_payroll"
    FEATURE_ASSETS = "feature_assets"


class SubscriptionService:
    ACCESS_MODE_SETUP = "setup"
    ACCESS_MODE_OPERATIONAL = "operational"
    ACCESS_MODE_BILLING = "billing"

    INTENT_STANDARD = "standard"
    INTENT_TRIAL = "trial"

    DEFAULT_PLAN_CODE = "starter"
    DEFAULT_PLAN_NAME = "Starter"

    LIMIT_CATALOG = {
        SubscriptionLimitCodes.MAX_ENTITIES: {
            "label": "Maximum Entities",
            "limit_type": PlanLimit.LimitType.INTEGER,
            "default": 1,
        },
        SubscriptionLimitCodes.MAX_ENTITY_USERS: {
            "label": "Maximum Tenant Users",
            "limit_type": PlanLimit.LimitType.INTEGER,
            "default": 5,
        },
        SubscriptionLimitCodes.FEATURE_FINANCIAL: {
            "label": "Financial Module",
            "limit_type": PlanLimit.LimitType.BOOLEAN,
            "default": True,
        },
        SubscriptionLimitCodes.FEATURE_INVENTORY: {
            "label": "Inventory Module",
            "limit_type": PlanLimit.LimitType.BOOLEAN,
            "default": True,
        },
        SubscriptionLimitCodes.FEATURE_PURCHASE: {
            "label": "Purchase Module",
            "limit_type": PlanLimit.LimitType.BOOLEAN,
            "default": True,
        },
        SubscriptionLimitCodes.FEATURE_SALES: {
            "label": "Sales Module",
            "limit_type": PlanLimit.LimitType.BOOLEAN,
            "default": True,
        },
        SubscriptionLimitCodes.FEATURE_REPORTING: {
            "label": "Reporting Module",
            "limit_type": PlanLimit.LimitType.BOOLEAN,
            "default": True,
        },
        SubscriptionLimitCodes.FEATURE_RBAC: {
            "label": "RBAC Module",
            "limit_type": PlanLimit.LimitType.BOOLEAN,
            "default": True,
        },
        SubscriptionLimitCodes.FEATURE_PAYROLL: {
            "label": "Payroll Module",
            "limit_type": PlanLimit.LimitType.BOOLEAN,
            "default": False,
        },
        SubscriptionLimitCodes.FEATURE_ASSETS: {
            "label": "Assets Module",
            "limit_type": PlanLimit.LimitType.BOOLEAN,
            "default": False,
        },
    }

    TENANT_MANAGE_ROLES = {
        UserEntityAccess.Role.OWNER,
        UserEntityAccess.Role.ADMIN,
    }
    BILLING_MANAGE_ROLES = {
        UserEntityAccess.Role.OWNER,
        UserEntityAccess.Role.BILLING,
    }
    TENANT_INVITE_ROLES = {
        UserEntityAccess.Role.OWNER,
        UserEntityAccess.Role.ADMIN,
    }
    ENTITY_CREATE_ROLES = {
        UserEntityAccess.Role.OWNER,
        UserEntityAccess.Role.ADMIN,
    }

    @classmethod
    @transaction.atomic
    def handle_signup(cls, *, user, intent=None):
        return cls.ensure_customer_account(user=user, intent=intent)

    @classmethod
    @transaction.atomic
    def ensure_customer_account(cls, *, user, intent=None):
        account = (
            CustomerAccount.objects.filter(owner=user, is_active=True)
            .order_by("id")
            .first()
        )

        created = False

        if not account:
            account = CustomerAccount.objects.create(
                owner=user,
                name=cls._default_account_name(user),
                slug=cls._default_account_slug(user),
                status=CustomerAccount.Status.ACTIVE,
                legal_name=cls._default_account_name(user),
                trade_name=cls._default_account_name(user),
                primary_contact_name=cls._default_contact_name(user),
                primary_contact_email=getattr(user, "email", None) or None,
                billing_contact_name=cls._default_contact_name(user),
                billing_email=getattr(user, "email", None) or None,
                metadata=cls._build_account_metadata(intent=intent),
            )
            created = True

        if created:
            changed = False
            default_name = cls._default_account_name(user)
            default_contact = cls._default_contact_name(user)
            default_email = getattr(user, "email", None) or None

            if not account.name:
                account.name = default_name
                changed = True
            if not account.legal_name:
                account.legal_name = default_name
                changed = True
            if not account.trade_name:
                account.trade_name = default_name
                changed = True
            if not account.primary_contact_name:
                account.primary_contact_name = default_contact
                changed = True
            if not account.primary_contact_email:
                account.primary_contact_email = default_email
                changed = True
            if not account.billing_contact_name:
                account.billing_contact_name = default_contact
                changed = True
            if not account.billing_email:
                account.billing_email = default_email
                changed = True
            if changed:
                account.save(update_fields=[
                    "name",
                    "legal_name",
                    "trade_name",
                    "primary_contact_name",
                    "primary_contact_email",
                    "billing_contact_name",
                    "billing_email",
                    "updated_at",
                ])

        elif intent:
            metadata = dict(account.metadata or {})
            if metadata.get("signup_intent") != intent:
                metadata["signup_intent"] = intent
                account.metadata = metadata
                account.save(update_fields=["metadata", "updated_at"])

        cls.ensure_owner_membership(customer_account=account, user=user)
        cls.ensure_active_subscription(customer_account=account, intent=intent)

        return account

    @classmethod
    @transaction.atomic
    def ensure_owner_membership(cls, *, customer_account, user):
        access, created = UserEntityAccess.objects.get_or_create(
            user=user,
            customer_account=customer_account,
            defaults={
                "role": UserEntityAccess.Role.OWNER,
                "granted_by": user,
            },
        )

        if not created:
            changed = False

            if access.role != UserEntityAccess.Role.OWNER:
                access.role = UserEntityAccess.Role.OWNER
                changed = True

            if not access.is_active:
                access.is_active = True
                changed = True

            if access.is_expired:
                access.expires_at = None
                changed = True

            if changed:
                access.save()

        return access

    @classmethod
    @transaction.atomic
    def assert_can_create_entity(cls, *, user):
        customer_account = cls.ensure_customer_account(user=user)
        cls._assert_account_setup_accessible(customer_account=customer_account)
        subscription = cls.ensure_active_subscription(customer_account=customer_account)
        cls._assert_subscription_setup_accessible(subscription=subscription)
        if not cls.can_create_entities(user=user, customer_account=customer_account):
            raise ValidationError(
                {
                    "detail": "Your tenant membership does not allow entity creation.",
                    "code": "tenant_membership_entity_create_denied",
                }
            )

        limit = cls.get_plan_limit(
            customer_account=customer_account,
            key=SubscriptionLimitCodes.MAX_ENTITIES,
        )
        if limit is None:
            return customer_account

        entity_count = Entity.objects.filter(
            customer_account=customer_account,
            isactive=True,
        ).count()

        if entity_count >= limit:
            cls._raise_limit_exceeded(
                limit_code=SubscriptionLimitCodes.MAX_ENTITIES,
                limit=limit,
                current=entity_count,
                detail="Your current subscription does not allow more entities.",
            )

        return customer_account

    @classmethod
    @transaction.atomic
    def register_entity_creation(cls, *, entity, owner):
        customer_account = entity.customer_account or cls.assert_can_create_entity(user=owner)

        if entity.customer_account_id != customer_account.id:
            entity.customer_account = customer_account
            entity.save(update_fields=["customer_account", "updated_at"])

        cls.ensure_account_membership(
            customer_account=customer_account,
            user=owner,
            role=UserEntityAccess.Role.OWNER,
            granted_by=owner,
        )

        return customer_account

    @classmethod
    @transaction.atomic
    def assert_can_invite_user(cls, *, entity, user=None):
        customer_account = cls._customer_account_for_entity(entity)
        cls._assert_account_operational(customer_account=customer_account)
        subscription = cls.ensure_active_subscription(customer_account=customer_account)
        cls._assert_subscription_operational(subscription=subscription)

        if user and UserEntityAccess.objects.filter(
            customer_account=customer_account,
            user=user,
            is_active=True,
        ).exists():
            return customer_account

        limit = cls.get_plan_limit(
            customer_account=customer_account,
            key=SubscriptionLimitCodes.MAX_ENTITY_USERS,
        )
        if limit is None:
            return customer_account

        now = timezone.now()
        active_user_count = UserEntityAccess.objects.filter(
            customer_account=customer_account,
            is_active=True,
        ).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=now)
        ).count()

        if active_user_count >= limit:
            cls._raise_limit_exceeded(
                limit_code=SubscriptionLimitCodes.MAX_ENTITY_USERS,
                limit=limit,
                current=active_user_count,
                detail="Your current subscription does not allow more users for this account.",
            )

        return customer_account

    @classmethod
    @transaction.atomic
    def register_user_invite(cls, *, entity, user, invited_by, role=UserEntityAccess.Role.MEMBER):
        customer_account = cls.assert_can_invite_user(entity=entity, user=user)
        if not cls.can_invite_members(user=invited_by, customer_account=customer_account):
            raise ValidationError(
                {
                    "detail": "Your tenant membership does not allow inviting users.",
                    "code": "tenant_membership_invite_denied",
                }
            )

        return cls.ensure_account_membership(
            customer_account=customer_account,
            user=user,
            role=role,
            granted_by=invited_by,
        )

    @classmethod
    @transaction.atomic
    def ensure_account_membership(cls, *, customer_account, user, role, granted_by=None):
        access, created = UserEntityAccess.objects.get_or_create(
            user=user,
            customer_account=customer_account,
            defaults={
                "role": role,
                "granted_by": granted_by,
            },
        )

        if not created:
            changed = False

            if access.role != role:
                access.role = role
                changed = True

            if granted_by and access.granted_by_id != getattr(granted_by, "id", None):
                access.granted_by = granted_by
                changed = True

            if not access.is_active:
                access.is_active = True
                changed = True

            if access.is_expired:
                access.expires_at = None
                changed = True

            if changed:
                access.save()

        return access

    @classmethod
    def assert_account_membership_exists(cls, *, user, customer_account):
        membership = cls.get_account_membership(user=user, customer_account=customer_account)
        if membership is None:
            raise ValidationError(
                {
                    "detail": "User must be a tenant member before entity role assignment.",
                    "code": "tenant_membership_required",
                }
            )
        return membership

    @classmethod
    @transaction.atomic
    def deactivate_account_membership(cls, *, membership, deactivated_by=None):
        if membership.role == UserEntityAccess.Role.OWNER:
            raise ValidationError(
                {
                    "detail": "Owner membership cannot be deactivated from tenant membership management.",
                    "code": "tenant_membership_owner_protected",
                }
            )

        if not membership.is_active:
            return membership

        membership.is_active = False
        metadata = dict(membership.metadata or {})
        if deactivated_by is not None:
            metadata["deactivated_by_id"] = deactivated_by.id
        membership.metadata = metadata
        membership.save(update_fields=["is_active", "metadata", "updated_at"])

        entity_ids = Entity.objects.filter(
            customer_account=membership.customer_account,
            isactive=True,
        ).values_list("id", flat=True)
        UserRoleAssignment = apps.get_model("rbac", "UserRoleAssignment")
        UserRoleAssignment.objects.filter(
            user=membership.user,
            entity_id__in=entity_ids,
            isactive=True,
        ).update(isactive=False, updated_at=timezone.now())

        return membership

    @classmethod
    def active_memberships_queryset(cls, *, user=None, customer_account=None):
        now = timezone.now()
        queryset = UserEntityAccess.objects.filter(is_active=True).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=now)
        )
        if user is not None:
            queryset = queryset.filter(user=user)
        if customer_account is not None:
            queryset = queryset.filter(customer_account=customer_account)
        return queryset

    @classmethod
    def get_account_membership(cls, *, user, customer_account):
        if not user or not getattr(user, "is_authenticated", False):
            return None
        if customer_account is None:
            return None
        return cls.active_memberships_queryset(
            user=user,
            customer_account=customer_account,
        ).order_by("id").first()

    @classmethod
    def has_account_membership(cls, *, user, customer_account):
        return cls.get_account_membership(user=user, customer_account=customer_account) is not None

    @classmethod
    def can_manage_tenant(cls, *, user, customer_account):
        membership = cls.get_account_membership(user=user, customer_account=customer_account)
        return bool(membership and membership.role in cls.TENANT_MANAGE_ROLES)

    @classmethod
    def can_manage_billing(cls, *, user, customer_account):
        membership = cls.get_account_membership(user=user, customer_account=customer_account)
        return bool(membership and membership.role in cls.BILLING_MANAGE_ROLES)

    @classmethod
    def can_invite_members(cls, *, user, customer_account):
        membership = cls.get_account_membership(user=user, customer_account=customer_account)
        return bool(membership and membership.role in cls.TENANT_INVITE_ROLES)

    @classmethod
    def can_create_entities(cls, *, user, customer_account):
        membership = cls.get_account_membership(user=user, customer_account=customer_account)
        return bool(membership and membership.role in cls.ENTITY_CREATE_ROLES)

    @classmethod
    def has_entity_membership(cls, *, user, entity, backfill_owner=False):
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if entity is None:
            return False

        customer_account = cls._customer_account_for_entity(entity)
        try:
            cls._assert_account_operational(customer_account=customer_account)
            subscription = cls.ensure_active_subscription(customer_account=customer_account)
            cls._assert_subscription_operational(subscription=subscription)
        except ValidationError:
            return False

        if cls.has_account_membership(user=user, customer_account=customer_account):
            return True

        if backfill_owner and entity.createdby_id == user.id:
            cls.ensure_account_membership(
                customer_account=customer_account,
                user=user,
                role=UserEntityAccess.Role.OWNER,
                granted_by=user,
            )
            return True

        return False

    @classmethod
    def assert_entity_access(cls, *, user, entity, access_mode=ACCESS_MODE_OPERATIONAL, feature_code=None, backfill_owner=True):
        if entity is None:
            raise ValidationError(
                {
                    "detail": "Entity is required.",
                    "code": "entity_required",
                }
            )

        customer_account = cls._customer_account_for_entity(entity)
        membership = cls.get_account_membership(user=user, customer_account=customer_account)
        if membership is None and backfill_owner and entity.createdby_id == getattr(user, "id", None):
            membership = cls.ensure_account_membership(
                customer_account=customer_account,
                user=user,
                role=UserEntityAccess.Role.OWNER,
                granted_by=user,
            )

        if membership is None:
            raise ValidationError(
                {
                    "detail": "You do not have tenant membership for this entity.",
                    "code": "tenant_membership_required",
                    "entity": entity.id,
                }
            )

        subscription = cls.ensure_active_subscription(customer_account=customer_account)
        if access_mode == cls.ACCESS_MODE_SETUP:
            cls._assert_account_setup_accessible(customer_account=customer_account)
            cls._assert_subscription_setup_accessible(subscription=subscription)
        elif access_mode == cls.ACCESS_MODE_BILLING:
            cls._assert_account_billing_accessible(customer_account=customer_account)
            cls._assert_subscription_billing_accessible(subscription=subscription)
        else:
            cls._assert_account_operational(customer_account=customer_account)
            cls._assert_subscription_operational(subscription=subscription)

        if feature_code and not cls.is_feature_enabled(customer_account=customer_account, key=feature_code):
            raise ValidationError(
                {
                    "detail": "Your current subscription plan does not include this feature.",
                    "code": "subscription_feature_disabled",
                    "feature_code": feature_code,
                }
            )

        return customer_account

    @classmethod
    @transaction.atomic
    def ensure_active_subscription(cls, *, customer_account, intent=None):
        active_subscription = (
            customer_account.subscriptions.filter(
                is_active=True,
                ended_at__isnull=True,
                status__in=[
                    CustomerSubscription.Status.TRIALING,
                    CustomerSubscription.Status.ACTIVE,
                    CustomerSubscription.Status.PAST_DUE,
                    CustomerSubscription.Status.PAUSED,
                    CustomerSubscription.Status.EXPIRED,
                    CustomerSubscription.Status.CANCELED,
                ],
            )
            .select_related("plan")
            .order_by("-started_at", "-id")
            .first()
        )

        if active_subscription:
            cls._normalize_subscription_state(active_subscription)


        if (
            active_subscription
            and active_subscription.status in {CustomerSubscription.Status.EXPIRED, CustomerSubscription.Status.CANCELED}
            and not active_subscription.auto_renew
        ):
            return active_subscription

        if active_subscription and active_subscription.is_current:
            if intent:
                metadata = dict(active_subscription.metadata or {})
                if metadata.get("signup_intent") != intent:
                    metadata["signup_intent"] = intent
                    active_subscription.metadata = metadata
                    active_subscription.save(update_fields=["metadata", "updated_at"])
            return active_subscription

        plan = cls.get_or_create_default_plan()

        now = timezone.now()
        trial_days = plan.trial_days or 0

        return CustomerSubscription.objects.create(
            customer_account=customer_account,
            plan=plan,
            status=(
                CustomerSubscription.Status.TRIALING
                if trial_days > 0 or intent == cls.INTENT_TRIAL
                else CustomerSubscription.Status.ACTIVE
            ),
            started_at=now,
            trial_ends_at=(now + timedelta(days=trial_days)) if trial_days > 0 else None,
            current_period_start=now,
            metadata=cls._build_subscription_metadata(intent=intent),
        )

    @classmethod
    @transaction.atomic
    def change_plan(cls, *, customer_account, new_plan, changed_by=None):
        now = timezone.now()

        current = (
            customer_account.subscriptions.filter(
                is_active=True,
                ended_at__isnull=True,
                status__in=[
                    CustomerSubscription.Status.TRIALING,
                    CustomerSubscription.Status.ACTIVE,
                    CustomerSubscription.Status.PAST_DUE,
                    CustomerSubscription.Status.PAUSED,
                    CustomerSubscription.Status.EXPIRED,
                    CustomerSubscription.Status.CANCELED,
                ],
            )
            .order_by("-started_at", "-id")
            .first()
        )

        if current and current.plan_id == new_plan.id and current.is_current:
            return current

        if current:
            current.status = CustomerSubscription.Status.CANCELED
            current.canceled_at = now
            current.ended_at = now
            current.auto_renew = False
            current.save(
                update_fields=[
                    "status",
                    "canceled_at",
                    "ended_at",
                    "auto_renew",
                    "updated_at",
                ]
            )

        return CustomerSubscription.objects.create(
            customer_account=customer_account,
            plan=new_plan,
            status=CustomerSubscription.Status.ACTIVE,
            started_at=now,
            current_period_start=now,
            metadata={
                "changed_by": getattr(changed_by, "id", None),
            },
        )

    @classmethod
    @transaction.atomic
    def cancel_subscription(cls, *, customer_account, canceled_by=None):
        now = timezone.now()

        subscription = (
            customer_account.subscriptions.filter(
                is_active=True,
                ended_at__isnull=True,
                status__in=[
                    CustomerSubscription.Status.TRIALING,
                    CustomerSubscription.Status.ACTIVE,
                    CustomerSubscription.Status.PAST_DUE,
                    CustomerSubscription.Status.PAUSED,
                    CustomerSubscription.Status.EXPIRED,
                    CustomerSubscription.Status.CANCELED,
                ],
            )
            .order_by("-started_at", "-id")
            .first()
        )

        if not subscription:
            return None

        subscription.status = CustomerSubscription.Status.CANCELED
        subscription.canceled_at = now
        subscription.ended_at = now
        subscription.auto_renew = False

        metadata = dict(subscription.metadata or {})
        metadata["canceled_by"] = getattr(canceled_by, "id", None)
        subscription.metadata = metadata

        subscription.save(
            update_fields=[
                "status",
                "canceled_at",
                "ended_at",
                "auto_renew",
                "metadata",
                "updated_at",
            ]
        )
        return subscription

    @classmethod
    def get_or_create_default_plan(cls):
        plan, created = SubscriptionPlan.objects.get_or_create(
            code=cls.DEFAULT_PLAN_CODE,
            defaults={
                "name": cls.DEFAULT_PLAN_NAME,
                "description": "Default starter plan.",
                "is_default": True,
                "is_public": True,
                "trial_days": 0,
            },
        )

        if not SubscriptionPlan.objects.filter(is_default=True).exists():
            SubscriptionPlan.objects.filter(pk=plan.pk).update(is_default=True)

        cls.ensure_plan_limit_catalog(plan=plan)

        return plan

    @classmethod
    def get_current_subscription(cls, *, customer_account):
        return cls.ensure_active_subscription(customer_account=customer_account)

    @classmethod
    def get_plan_limit(cls, *, customer_account, key):
        subscription = cls.ensure_active_subscription(customer_account=customer_account)

        limit = subscription.plan.limits.filter(key=key).first()
        if not limit:
            definition = cls.LIMIT_CATALOG.get(key)
            return None if not definition else definition.get("default")

        return limit.value

    @classmethod
    def get_all_plan_limits(cls, *, customer_account):
        subscription = cls.ensure_active_subscription(customer_account=customer_account)

        limits = {}
        for key, definition in cls.LIMIT_CATALOG.items():
            limits[key] = definition.get("default")
        for limit in subscription.plan.limits.all():
            limits[limit.key] = limit.value
        return limits

    @classmethod
    def get_feature_flags(cls, *, customer_account):
        limits = cls.get_all_plan_limits(customer_account=customer_account)
        return {
            key: bool(limits.get(key))
            for key in cls.LIMIT_CATALOG
            if cls.LIMIT_CATALOG[key]["limit_type"] == PlanLimit.LimitType.BOOLEAN
        }

    @classmethod
    def is_feature_enabled(cls, *, customer_account, key):
        definition = cls.LIMIT_CATALOG.get(key) or {}
        if definition.get("limit_type") != PlanLimit.LimitType.BOOLEAN:
            raise ValidationError({"detail": f"{key} is not a boolean feature flag."})
        return bool(cls.get_plan_limit(customer_account=customer_account, key=key))

    @classmethod
    def ensure_plan_limit_catalog(cls, *, plan):
        for key, definition in cls.LIMIT_CATALOG.items():
            defaults = {
                "label": definition["label"],
                "limit_type": definition["limit_type"],
            }
            if definition["limit_type"] == PlanLimit.LimitType.INTEGER:
                defaults["int_value"] = definition["default"]
            elif definition["limit_type"] == PlanLimit.LimitType.BOOLEAN:
                defaults["bool_value"] = definition["default"]
            else:
                defaults["text_value"] = definition["default"]
            limit, created = PlanLimit.objects.get_or_create(
                plan=plan,
                key=key,
                defaults=defaults,
            )
            if not created:
                changed = False
                if limit.label != definition["label"]:
                    limit.label = definition["label"]
                    changed = True
                if limit.limit_type != definition["limit_type"]:
                    limit.limit_type = definition["limit_type"]
                    changed = True
                if changed:
                    limit.save(update_fields=["label", "limit_type", "updated_at"])

    @classmethod
    def build_subscription_snapshot(cls, *, customer_account=None, user=None, entity=None):
        if customer_account is None:
            if entity is not None:
                customer_account = cls._customer_account_for_entity(entity)
            elif user is not None:
                customer_account = cls.ensure_customer_account(user=user)
            else:
                raise ValidationError({"detail": "A user, entity, or customer account is required."})

        subscription = cls.ensure_active_subscription(customer_account=customer_account)

        max_entities = cls.get_plan_limit(
            customer_account=customer_account,
            key=SubscriptionLimitCodes.MAX_ENTITIES,
        )
        max_entity_users = cls.get_plan_limit(
            customer_account=customer_account,
            key=SubscriptionLimitCodes.MAX_ENTITY_USERS,
        )
        feature_flags = cls.get_feature_flags(customer_account=customer_account)

        entities_used = Entity.objects.filter(
            customer_account=customer_account,
            isactive=True,
        ).count()

        account_users_used = UserEntityAccess.objects.filter(
            customer_account=customer_account,
            is_active=True,
        ).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())
        ).count()

        snapshot = {
            "customer_account": {
                "id": customer_account.id,
                "name": customer_account.name,
                "legal_name": customer_account.legal_name,
                "trade_name": customer_account.trade_name,
                "slug": customer_account.slug,
                "status": customer_account.status,
                "owner_id": customer_account.owner_id,
                "primary_contact_name": customer_account.primary_contact_name,
                "primary_contact_email": customer_account.primary_contact_email,
                "primary_contact_phone": customer_account.primary_contact_phone,
                "billing_contact_name": customer_account.billing_contact_name,
                "billing_contact_phone": customer_account.billing_contact_phone,
                "billing_email": customer_account.billing_email,
                "support_email": customer_account.support_email,
                "timezone": customer_account.timezone,
                "country": customer_account.country,
                "status_reason": customer_account.status_reason,
                "status_notes": customer_account.status_notes,
                "setup_accessible": customer_account.is_setup_accessible,
                "operational_accessible": customer_account.is_operationally_active,
                "billing_accessible": customer_account.is_billing_accessible,
                "permissions": {
                    "can_manage_tenant": cls.can_manage_tenant(user=user, customer_account=customer_account) if user else None,
                    "can_manage_billing": cls.can_manage_billing(user=user, customer_account=customer_account) if user else None,
                    "can_invite_members": cls.can_invite_members(user=user, customer_account=customer_account) if user else None,
                    "can_create_entities": cls.can_create_entities(user=user, customer_account=customer_account) if user else None,
                },
            },
            "subscription": {
                "id": subscription.id,
                "status": subscription.status,
                "plan_code": subscription.plan.code,
                "plan_name": subscription.plan.name,
                "is_trial": subscription.status == CustomerSubscription.Status.TRIALING,
                "setup_accessible": subscription.is_setup_accessible,
                "operational_accessible": subscription.is_operationally_active,
                "billing_accessible": subscription.is_billing_accessible,
                "started_at": subscription.started_at,
                "trial_ends_at": subscription.trial_ends_at,
                "current_period_start": subscription.current_period_start,
                "current_period_end": subscription.current_period_end,
                "ended_at": subscription.ended_at,
                "metadata": subscription.metadata or {},
            },
            "limits": {
                SubscriptionLimitCodes.MAX_ENTITIES: max_entities,
                SubscriptionLimitCodes.MAX_ENTITY_USERS: max_entity_users,
            },
            "features": feature_flags,
            "usage": {
                "entities_used": entities_used,
                "entities_remaining": cls._remaining(max_entities, entities_used),
                "account_users_used": account_users_used,
                "account_users_remaining": cls._remaining(max_entity_users, account_users_used),
            },
        }

        return snapshot

    @classmethod
    def _customer_account_for_entity(cls, entity):
        if entity.customer_account_id:
            cls.ensure_active_subscription(customer_account=entity.customer_account)
            return entity.customer_account

        owner = getattr(entity, "createdby", None)
        if owner is None:
            raise ValidationError({"detail": "Entity owner is required for subscription setup."})

        customer_account = cls.ensure_customer_account(user=owner)
        entity.customer_account = customer_account
        entity.save(update_fields=["customer_account", "updated_at"])
        return customer_account

    @staticmethod
    def _default_account_name(user):
        full_name = f"{user.first_name} {user.last_name}".strip()
        return full_name or getattr(user, "email", None) or getattr(user, "username", None) or f"user-{user.id}"

    @staticmethod
    def _default_contact_name(user):
        full_name = f"{user.first_name} {user.last_name}".strip()
        return full_name or getattr(user, "username", None) or getattr(user, "email", None) or f"user-{user.id}"

    @staticmethod
    def _default_account_slug(user):
        base = (
            getattr(user, "username", None)
            or getattr(user, "email", "").split("@")[0]
            or f"user-{user.id}"
        )
        return f"{base}-{user.id}"

    @classmethod
    def _raise_limit_exceeded(cls, *, limit_code, limit, current, detail):
        raise ValidationError(
            {
                "detail": detail,
                "code": "subscription_limit_exceeded",
                "limit_code": limit_code,
                "limit": limit,
                "current": current,
            }
        )

    @classmethod
    def _build_account_metadata(cls, *, intent=None):
        return {"signup_intent": intent or cls.INTENT_STANDARD}

    @classmethod
    def _build_subscription_metadata(cls, *, intent=None):
        return {"signup_intent": intent or cls.INTENT_STANDARD}

    @staticmethod
    def _remaining(limit, used):
        if limit is None:
            return None
        return max(limit - used, 0)
    @staticmethod
    def _remaining(limit, used):
        if limit is None:
            return None
        return max(limit - used, 0)

    @classmethod
    def _normalize_subscription_state(cls, subscription):
        now = timezone.now()
        updates = []

        if (
            subscription.status == CustomerSubscription.Status.TRIALING
            and subscription.trial_ends_at
            and subscription.trial_ends_at <= now
        ):
            if subscription.auto_renew:
                subscription.status = CustomerSubscription.Status.ACTIVE
                if not subscription.current_period_start:
                    subscription.current_period_start = now
                    updates.append("current_period_start")
                updates.append("status")
            else:
                subscription.status = CustomerSubscription.Status.EXPIRED
                subscription.ended_at = now
                updates.extend(["status", "ended_at"])

        if updates:
            updates.append("updated_at")
            subscription.save(update_fields=updates)

    @staticmethod
    def _assert_account_setup_accessible(*, customer_account):
        if not customer_account.is_setup_accessible:
            raise ValidationError(
                {
                    "detail": "Customer account does not allow tenant setup access.",
                    "code": "subscription_account_setup_inactive",
                    "status": customer_account.status,
                }
            )

    @staticmethod
    def _assert_account_operational(*, customer_account):
        if not customer_account.is_operationally_active:
            raise ValidationError(
                {
                    "detail": "Customer account is not active for operations.",
                    "code": "subscription_account_inactive",
                    "status": customer_account.status,
                }
            )

    @staticmethod
    def _assert_account_billing_accessible(*, customer_account):
        if not customer_account.is_billing_accessible:
            raise ValidationError(
                {
                    "detail": "Customer account does not allow billing access.",
                    "code": "subscription_account_billing_inactive",
                    "status": customer_account.status,
                }
            )

    @staticmethod
    def _assert_subscription_setup_accessible(*, subscription):
        if not subscription.is_setup_accessible:
            raise ValidationError(
                {
                    "detail": "Subscription does not allow tenant setup access.",
                    "code": "subscription_setup_inactive",
                    "status": subscription.status,
                }
            )

    @staticmethod
    def _assert_subscription_operational(*, subscription):
        if not subscription.is_operationally_active:
            raise ValidationError(
                {
                    "detail": "Subscription is not active for operations.",
                    "code": "subscription_inactive",
                    "status": subscription.status,
                }
            )

    @staticmethod
    def _assert_subscription_billing_accessible(*, subscription):
        if not subscription.is_billing_accessible:
            raise ValidationError(
                {
                    "detail": "Subscription does not allow billing access.",
                    "code": "subscription_billing_inactive",
                    "status": subscription.status,
                }
            )
