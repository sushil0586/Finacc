from django.db import transaction
from django.db.models import Count
from rest_framework.exceptions import ValidationError

from entity.models import Entity

from .models import CustomerAccount, CustomerSubscription, PlanLimit, SubscriptionPlan, UserEntityAccess


class SubscriptionLimitCodes:
    MAX_ENTITIES = "max_entities"
    MAX_ENTITY_USERS = "max_entity_users"


class SubscriptionService:
    INTENT_STANDARD = "standard"
    INTENT_TRIAL = "trial"
    DEFAULT_PLAN_CODE = "starter"
    DEFAULT_PLAN_NAME = "Starter"
    DEFAULT_LIMITS = {
        SubscriptionLimitCodes.MAX_ENTITIES: 1,
        SubscriptionLimitCodes.MAX_ENTITY_USERS: 5,
    }

    @classmethod
    @transaction.atomic
    def handle_signup(cls, *, user, intent=None):
        return cls.ensure_customer_account(user=user, intent=intent)

    @classmethod
    @transaction.atomic
    def ensure_customer_account(cls, *, user, intent=None):
        account, created = CustomerAccount.objects.get_or_create(
            primary_user=user,
            defaults={
                "name": cls._default_account_name(user),
                "metadata": cls._build_account_metadata(intent=intent),
            },
        )
        if created and not account.name:
            account.name = cls._default_account_name(user)
            account.save(update_fields=["name", "updated_at"])
        elif intent:
            metadata = dict(account.metadata or {})
            if metadata.get("signup_intent") != intent:
                metadata["signup_intent"] = intent
                account.metadata = metadata
                account.save(update_fields=["metadata", "updated_at"])
        cls.ensure_active_subscription(customer_account=account, intent=intent)
        return account

    @classmethod
    @transaction.atomic
    def assert_can_create_entity(cls, *, user):
        customer_account = cls.ensure_customer_account(user=user)
        limit = cls.get_plan_limit(customer_account=customer_account, code=SubscriptionLimitCodes.MAX_ENTITIES)
        if limit is None:
            return customer_account
        entity_count = Entity.objects.filter(customer_account=customer_account, isactive=True).count()
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
    def register_entity_creation(cls, *, entity, owner, source=UserEntityAccess.SOURCE_ENTITY_CREATE):
        customer_account = entity.customer_account or cls.assert_can_create_entity(user=owner)
        if entity.customer_account_id != customer_account.id:
            entity.customer_account = customer_account
            entity.save(update_fields=["customer_account", "updated_at"])
        cls.grant_entity_access(
            entity=entity,
            user=owner,
            granted_by=owner,
            source=source,
            is_owner=True,
        )
        return customer_account

    @classmethod
    @transaction.atomic
    def assert_can_invite_user(cls, *, entity, user=None):
        customer_account = cls._customer_account_for_entity(entity)
        if user and UserEntityAccess.objects.filter(entity=entity, user=user, isactive=True).exists():
            return customer_account
        limit = cls.get_plan_limit(customer_account=customer_account, code=SubscriptionLimitCodes.MAX_ENTITY_USERS)
        if limit is None:
            return customer_account
        active_user_count = (
            UserEntityAccess.objects.filter(entity=entity, isactive=True)
            .values("entity_id")
            .annotate(user_count=Count("user_id", distinct=True))
            .values_list("user_count", flat=True)
            .first()
            or 0
        )
        if active_user_count >= limit:
            cls._raise_limit_exceeded(
                limit_code=SubscriptionLimitCodes.MAX_ENTITY_USERS,
                limit=limit,
                current=active_user_count,
                detail="Your current subscription does not allow more users for this entity.",
            )
        return customer_account

    @classmethod
    @transaction.atomic
    def register_user_invite(cls, *, entity, user, invited_by):
        cls.assert_can_invite_user(entity=entity, user=user)
        return cls.grant_entity_access(
            entity=entity,
            user=user,
            granted_by=invited_by,
            source=UserEntityAccess.SOURCE_INVITE,
            is_owner=False,
        )

    @classmethod
    @transaction.atomic
    def grant_entity_access(cls, *, entity, user, granted_by=None, source=UserEntityAccess.SOURCE_INVITE, is_owner=False):
        customer_account = cls._customer_account_for_entity(entity)
        access, created = UserEntityAccess.objects.get_or_create(
            entity=entity,
            user=user,
            defaults={
                "customer_account": customer_account,
                "granted_by": granted_by,
                "source": source,
                "is_owner": is_owner,
            },
        )
        if not created:
            changed = False
            if access.customer_account_id != customer_account.id:
                access.customer_account = customer_account
                changed = True
            if granted_by and access.granted_by_id != getattr(granted_by, "id", None):
                access.granted_by = granted_by
                changed = True
            if access.source != source:
                access.source = source
                changed = True
            if is_owner and not access.is_owner:
                access.is_owner = True
                changed = True
            if not access.isactive:
                access.isactive = True
                changed = True
            if changed:
                access.save()
        return access

    @classmethod
    def ensure_active_subscription(cls, *, customer_account, intent=None):
        active_subscription = (
            customer_account.subscriptions.filter(isactive=True)
            .select_related("plan")
            .order_by("-starts_at", "-id")
            .first()
        )
        if active_subscription and active_subscription.is_current:
            if intent:
                metadata = dict(active_subscription.metadata or {})
                if metadata.get("signup_intent") != intent:
                    metadata["signup_intent"] = intent
                    active_subscription.metadata = metadata
                    active_subscription.save(update_fields=["metadata", "updated_at"])
            return active_subscription
        plan = cls.get_or_create_default_plan()
        return CustomerSubscription.objects.create(
            customer_account=customer_account,
            plan=plan,
            status=CustomerSubscription.STATUS_TRIAL,
            metadata=cls._build_subscription_metadata(intent=intent),
        )

    @classmethod
    def get_or_create_default_plan(cls):
        plan, created = SubscriptionPlan.objects.get_or_create(
            code=cls.DEFAULT_PLAN_CODE,
            defaults={
                "name": cls.DEFAULT_PLAN_NAME,
                "description": "Default starter plan.",
                "is_default": True,
            },
        )
        if created:
            PlanLimit.objects.bulk_create(
                [
                    PlanLimit(plan=plan, code=code, value=value)
                    for code, value in cls.DEFAULT_LIMITS.items()
                ]
            )
        else:
            if not SubscriptionPlan.objects.filter(is_default=True).exists():
                SubscriptionPlan.objects.filter(pk=plan.pk).update(is_default=True)
            for code, value in cls.DEFAULT_LIMITS.items():
                PlanLimit.objects.get_or_create(plan=plan, code=code, defaults={"value": value})
        return plan

    @classmethod
    def get_plan_limit(cls, *, customer_account, code):
        subscription = cls.ensure_active_subscription(customer_account=customer_account)
        limit = subscription.plan.limits.filter(code=code, isactive=True).values_list("value", flat=True).first()
        return limit

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
        max_entities = cls.get_plan_limit(customer_account=customer_account, code=SubscriptionLimitCodes.MAX_ENTITIES)
        entities_used = Entity.objects.filter(customer_account=customer_account, isactive=True).count()

        snapshot = {
            "customer_account": {
                "id": customer_account.id,
                "name": customer_account.name,
                "status": customer_account.status,
            },
            "subscription": {
                "id": subscription.id,
                "status": subscription.status,
                "plan_code": subscription.plan.code,
                "plan_name": subscription.plan.name,
                "is_trial": subscription.status == CustomerSubscription.STATUS_TRIAL,
                "starts_at": subscription.starts_at,
                "ends_at": subscription.ends_at,
                "current_period_end": subscription.current_period_end,
                "metadata": subscription.metadata or {},
            },
            "limits": {
                SubscriptionLimitCodes.MAX_ENTITIES: max_entities,
                SubscriptionLimitCodes.MAX_ENTITY_USERS: cls.get_plan_limit(
                    customer_account=customer_account,
                    code=SubscriptionLimitCodes.MAX_ENTITY_USERS,
                ),
            },
            "usage": {
                "entities_used": entities_used,
                "entities_remaining": cls._remaining(max_entities, entities_used),
            },
        }

        if entity is not None:
            entity_users_limit = snapshot["limits"][SubscriptionLimitCodes.MAX_ENTITY_USERS]
            entity_users_used = (
                UserEntityAccess.objects.filter(entity=entity, isactive=True)
                .values("entity_id")
                .annotate(user_count=Count("user_id", distinct=True))
                .values_list("user_count", flat=True)
                .first()
                or 0
            )
            snapshot["usage"].update(
                {
                    "entity_users_used": entity_users_used,
                    "entity_users_remaining": cls._remaining(entity_users_limit, entity_users_used),
                }
            )

        return snapshot

    @classmethod
    def _customer_account_for_entity(cls, entity):
        if entity.customer_account_id:
            cls.ensure_active_subscription(customer_account=entity.customer_account)
            return entity.customer_account
        owner = entity.createdby
        if owner is None:
            raise ValidationError({"detail": "Entity owner is required for subscription setup."})
        customer_account = cls.ensure_customer_account(user=owner)
        entity.customer_account = customer_account
        entity.save(update_fields=["customer_account", "updated_at"])
        return customer_account

    @staticmethod
    def _default_account_name(user):
        full_name = f"{user.first_name} {user.last_name}".strip()
        return full_name or user.email or user.username

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
