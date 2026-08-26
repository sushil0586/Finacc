from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import serializers

from entity.models import Entity

from .models import PlanLimit, SubscriptionPlan, UserEntityAccess
from .services import SubscriptionService


User = get_user_model()


class TenantMembershipSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)
    full_name = serializers.SerializerMethodField()
    user_id = serializers.IntegerField(read_only=True)
    granted_by_name = serializers.SerializerMethodField()
    entity_assignment_count = serializers.IntegerField(read_only=True)
    account_assignment_count = serializers.IntegerField(read_only=True)
    is_owner_membership = serializers.SerializerMethodField()
    is_current_user = serializers.SerializerMethodField()
    email_verified = serializers.BooleanField(source="user.email_verified", read_only=True)
    is_expired = serializers.SerializerMethodField()
    invitation_status = serializers.SerializerMethodField()
    last_invite_sent_at = serializers.SerializerMethodField()
    can_resend_invite = serializers.SerializerMethodField()

    class Meta:
        model = UserEntityAccess
        fields = (
            "id",
            "user_id",
            "email",
            "username",
            "first_name",
            "last_name",
            "full_name",
            "role",
            "is_active",
            "granted_at",
            "expires_at",
            "granted_by_name",
            "entity_assignment_count",
            "account_assignment_count",
            "is_owner_membership",
            "is_current_user",
            "email_verified",
            "is_expired",
            "invitation_status",
            "last_invite_sent_at",
            "can_resend_invite",
        )

    def get_full_name(self, obj):
        full_name = f"{obj.user.first_name} {obj.user.last_name}".strip()
        return full_name or obj.user.email or obj.user.username

    def get_granted_by_name(self, obj):
        if not obj.granted_by_id:
            return ""
        full_name = f"{obj.granted_by.first_name} {obj.granted_by.last_name}".strip()
        return full_name or obj.granted_by.email or obj.granted_by.username

    def get_is_owner_membership(self, obj):
        customer_account = getattr(obj, "customer_account", None)
        return bool(customer_account and customer_account.owner_id == obj.user_id)

    def get_is_current_user(self, obj):
        actor = self.context.get("actor")
        return bool(actor and obj.user_id == actor.id)

    def get_is_expired(self, obj):
        return obj.is_expired

    def get_invitation_status(self, obj):
        if self.get_is_owner_membership(obj):
            return "owner"
        if not obj.is_active:
            return "inactive"
        if obj.is_expired:
            return "expired"
        if not obj.user.email_verified:
            return "pending_verification"
        return "active"

    def get_last_invite_sent_at(self, obj):
        metadata = obj.metadata or {}
        return metadata.get("invite_last_sent_at") or metadata.get("created_invite_at") or obj.granted_at.isoformat()

    def get_can_resend_invite(self, obj):
        return bool(
            obj.is_active
            and not obj.is_expired
            and not obj.user.email_verified
            and not self.get_is_owner_membership(obj)
            and not self.get_is_current_user(obj)
        )


class TenantMembershipCreateSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    email = serializers.EmailField()
    username = serializers.CharField(max_length=150, required=False, allow_blank=True)
    password = serializers.CharField(max_length=128, min_length=6, write_only=True, required=False, allow_blank=True)
    role = serializers.ChoiceField(choices=UserEntityAccess.Role.choices)
    expires_at = serializers.DateTimeField(required=False, allow_null=True)

    def validate_email(self, value):
        return (value or "").strip().lower()

    def validate_role(self, value):
        if value == UserEntityAccess.Role.OWNER:
            raise serializers.ValidationError("Owner membership cannot be created from tenant membership management.")
        return value

    def validate(self, attrs):
        customer_account = self.context["customer_account"]
        email = attrs["email"]
        existing_user = User.objects.filter(email__iexact=email).first()
        attrs["existing_user"] = existing_user

        if existing_user is not None:
            existing_membership = UserEntityAccess.objects.filter(
                user=existing_user,
                customer_account=customer_account,
                is_active=True,
            ).first()
            if existing_membership:
                raise serializers.ValidationError({"email": "This user is already a tenant member."})
        else:
            password = (attrs.get("password") or "").strip()
            if not password:
                raise serializers.ValidationError({"password": "Password is required when creating a new user."})
            validate_password(password)
            attrs["resolved_username"] = self._resolve_username(
                requested_username=(attrs.get("username") or "").strip(),
                email=email,
            )

        expires_at = attrs.get("expires_at")
        if expires_at and expires_at <= timezone.now():
            raise serializers.ValidationError({"expires_at": "Expiry must be in the future."})
        return attrs

    def _resolve_username(self, *, requested_username: str, email: str) -> str:
        base = (requested_username or email.split("@", 1)[0] or "user").strip()
        candidate = base
        counter = 1
        while User.objects.filter(username__iexact=candidate).exists():
            counter += 1
            candidate = f"{base}{counter}"
        return candidate

    @transaction.atomic
    def create(self, validated_data):
        customer_account = self.context["customer_account"]
        actor = self.context["actor"]
        existing_user = validated_data.pop("existing_user", None)
        role = validated_data["role"]
        expires_at = validated_data.get("expires_at")

        if existing_user is None:
            user = User.objects.create_user(
                username=validated_data["resolved_username"],
                email=validated_data["email"],
                password=validated_data["password"],
                first_name=(validated_data.get("first_name") or "").strip(),
                last_name=(validated_data.get("last_name") or "").strip(),
                is_active=True,
            )
        else:
            user = existing_user

        membership = SubscriptionService.ensure_account_membership(
            customer_account=customer_account,
            user=user,
            role=role,
            granted_by=actor,
        )
        if membership.expires_at != expires_at:
            membership.expires_at = expires_at
            membership.save(update_fields=["expires_at", "updated_at"])
        metadata = dict(membership.metadata or {})
        if not metadata.get("created_invite_at"):
            metadata["created_invite_at"] = timezone.now().isoformat()
            membership.metadata = metadata
            membership.save(update_fields=["metadata", "updated_at"])
        return membership


class TenantMembershipUpdateSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=UserEntityAccess.Role.choices, required=False)
    is_active = serializers.BooleanField(required=False)
    expires_at = serializers.DateTimeField(required=False, allow_null=True)

    def validate_role(self, value):
        if value == UserEntityAccess.Role.OWNER:
            raise serializers.ValidationError("Owner membership cannot be managed from this screen.")
        return value

    def validate(self, attrs):
        membership = self.context["membership"]
        actor = self.context["actor"]
        if membership.role == UserEntityAccess.Role.OWNER or membership.customer_account.owner_id == membership.user_id:
            raise serializers.ValidationError({
                "detail": "Owner membership cannot be changed here.",
                "code": "tenant_membership_owner_protected",
            })
        if membership.user_id == actor.id and any(field in attrs for field in ("role", "is_active", "expires_at")):
            raise serializers.ValidationError({
                "detail": "Use another tenant admin to change your own membership so you do not lock yourself out.",
                "code": "tenant_membership_self_management_denied",
            })
        expires_at = attrs.get("expires_at")
        if expires_at and expires_at <= timezone.now():
            raise serializers.ValidationError({"expires_at": "Expiry must be in the future."})
        return attrs

    @transaction.atomic
    def save(self, **kwargs):
        membership = self.context["membership"]
        actor = self.context["actor"]
        validated_data = self.validated_data

        if validated_data.get("is_active") is False:
            return SubscriptionService.deactivate_account_membership(
                membership=membership,
                deactivated_by=actor,
            )

        changed = False
        if "role" in validated_data and membership.role != validated_data["role"]:
            membership.role = validated_data["role"]
            changed = True
        if "expires_at" in validated_data and membership.expires_at != validated_data["expires_at"]:
            membership.expires_at = validated_data["expires_at"]
            changed = True
        if validated_data.get("is_active") is True and not membership.is_active:
            membership.is_active = True
            changed = True
        if changed:
            membership.save(update_fields=["role", "expires_at", "is_active", "updated_at"])
        return membership


class TenantMembershipPasswordResetSerializer(serializers.Serializer):
    new_password = serializers.CharField(max_length=128, min_length=6, write_only=True)

    def validate_new_password(self, value):
        validate_password(value)
        return value

    def validate(self, attrs):
        membership = self.context["membership"]
        actor = self.context["actor"]
        if membership.role == UserEntityAccess.Role.OWNER or membership.customer_account.owner_id == membership.user_id:
            raise serializers.ValidationError({
                "detail": "Owner password cannot be reset from tenant membership management.",
                "code": "tenant_membership_owner_protected",
            })
        if membership.user_id == actor.id:
            raise serializers.ValidationError({
                "detail": "Use Change Password to update your own password.",
                "code": "tenant_membership_self_password_reset_denied",
            })
        if not membership.is_active:
            raise serializers.ValidationError({
                "detail": "Reactivate the membership before resetting password.",
                "code": "tenant_membership_inactive",
            })
        return attrs

    @transaction.atomic
    def save(self, **kwargs):
        from Authentication.services import AuthPasswordService

        membership = self.context["membership"]
        AuthPasswordService.reset_password(
            user=membership.user,
            new_password=self.validated_data["new_password"],
        )
        return membership


class TenantMembershipResendInviteSerializer(serializers.Serializer):
    def validate(self, attrs):
        membership = self.context["membership"]
        actor = self.context["actor"]
        if membership.role == UserEntityAccess.Role.OWNER or membership.customer_account.owner_id == membership.user_id:
            raise serializers.ValidationError({
                "detail": "Owner membership invite cannot be resent from tenant membership management.",
                "code": "tenant_membership_owner_protected",
            })
        if membership.user_id == actor.id:
            raise serializers.ValidationError({
                "detail": "Use your email verification screen to resend your own verification OTP.",
                "code": "tenant_membership_self_invite_resend_denied",
            })
        if not membership.is_active:
            raise serializers.ValidationError({
                "detail": "Reactivate the membership before resending invite verification.",
                "code": "tenant_membership_inactive",
            })
        if membership.is_expired:
            raise serializers.ValidationError({
                "detail": "Extend the membership expiry before resending invite verification.",
                "code": "tenant_membership_expired",
            })
        return attrs

    @transaction.atomic
    def save(self, **kwargs):
        from Authentication.services import AuthOTPService

        membership = self.context["membership"]
        actor = self.context["actor"]
        if not membership.user.email_verified:
            AuthOTPService.create_otp(
                user=membership.user,
                email=membership.user.email,
                purpose="email_verification",
            )

        metadata = dict(membership.metadata or {})
        metadata["invite_last_sent_at"] = timezone.now().isoformat()
        metadata["invite_last_sent_by_id"] = actor.id
        metadata["invite_resend_count"] = int(metadata.get("invite_resend_count") or 0) + 1
        membership.metadata = metadata
        membership.save(update_fields=["metadata", "updated_at"])
        return membership


class TenantMembershipListResponseSerializer(serializers.Serializer):
    entity_id = serializers.IntegerField()
    entity_name = serializers.CharField()
    customer_account_id = serializers.IntegerField()
    customer_account_name = serializers.CharField()
    capabilities = serializers.DictField(child=serializers.BooleanField())
    role_choices = serializers.ListField(child=serializers.DictField())
    members = TenantMembershipSerializer(many=True)


class SubscriptionPublicPlanSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    code = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    tier = serializers.CharField(allow_null=True)
    billing_interval = serializers.CharField(allow_null=True)
    price_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    currency = serializers.CharField(allow_null=True)
    trial_days = serializers.IntegerField()
    is_default = serializers.BooleanField()
    is_public = serializers.BooleanField()
    is_selectable_for_signup = serializers.BooleanField()
    sort_order = serializers.IntegerField()
    features = serializers.DictField(child=serializers.BooleanField())
    limits = serializers.DictField(child=serializers.IntegerField(allow_null=True))
    metadata = serializers.JSONField()


class SubscriptionSnapshotSerializer(serializers.Serializer):
    customer_account = serializers.JSONField()
    subscription = serializers.JSONField()
    plan = SubscriptionPublicPlanSerializer()
    limits = serializers.JSONField()
    features = serializers.JSONField()
    feature_summary = serializers.JSONField()
    locked_features = serializers.JSONField()
    usage = serializers.JSONField()
    quota_summary = serializers.JSONField()
    block_reasons = serializers.JSONField()


class SubscriptionAccountActionSerializer(serializers.Serializer):
    plan_id = serializers.IntegerField(required=False)
    status_reason = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    status_notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate(self, attrs):
        action = self.context["action"]
        if action == "change_plan":
            if not attrs.get("plan_id"):
                raise serializers.ValidationError({"plan_id": "plan_id is required for change_plan."})
        return attrs


class SubscriptionPlanLimitAdminSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    key = serializers.CharField(max_length=100)
    label = serializers.CharField(max_length=150, required=False, allow_blank=True)
    limit_type = serializers.ChoiceField(choices=PlanLimit.LimitType.choices)
    int_value = serializers.IntegerField(required=False, allow_null=True)
    bool_value = serializers.BooleanField(required=False, allow_null=True)
    text_value = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    is_unlimited = serializers.BooleanField(required=False, default=False)
    value = serializers.JSONField(read_only=True)
    metadata = serializers.JSONField(required=False)

    def validate(self, attrs):
        is_unlimited = attrs.get("is_unlimited", False)
        limit_type = attrs["limit_type"]
        int_value = attrs.get("int_value")
        bool_value = attrs.get("bool_value")
        text_value = attrs.get("text_value")

        value_count = sum([
            int_value is not None,
            bool_value is not None,
            bool(text_value),
        ])

        if is_unlimited:
            if value_count > 0:
                raise serializers.ValidationError("Unlimited limits cannot also store a concrete value.")
            return attrs

        if limit_type == PlanLimit.LimitType.INTEGER:
            if int_value is None:
                raise serializers.ValidationError({"int_value": "Required for integer limits."})
            if bool_value is not None or text_value:
                raise serializers.ValidationError("Only int_value may be set for integer limits.")
        elif limit_type == PlanLimit.LimitType.BOOLEAN:
            if bool_value is None:
                raise serializers.ValidationError({"bool_value": "Required for boolean limits."})
            if int_value is not None or text_value:
                raise serializers.ValidationError("Only bool_value may be set for boolean limits.")
        else:
            if not text_value:
                raise serializers.ValidationError({"text_value": "Required for text limits."})
            if int_value is not None or bool_value is not None:
                raise serializers.ValidationError("Only text_value may be set for text limits.")
        return attrs


class SubscriptionPlanAdminSerializer(serializers.ModelSerializer):
    raw_limits = SubscriptionPlanLimitAdminSerializer(many=True, required=False)
    features = serializers.DictField(read_only=True)
    limits = serializers.DictField(read_only=True)

    class Meta:
        model = SubscriptionPlan
        fields = (
            "id",
            "code",
            "name",
            "description",
            "tier",
            "billing_interval",
            "price_amount",
            "currency",
            "trial_days",
            "sort_order",
            "is_public",
            "is_default",
            "is_selectable_for_signup",
            "is_active",
            "external_price_id",
            "billing_provider",
            "metadata",
            "features",
            "limits",
            "raw_limits",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("created_at", "updated_at")

    def validate(self, attrs):
        instance = getattr(self, "instance", None)

        def resolved(field, default=None):
            if field in attrs:
                return attrs[field]
            if instance is not None:
                return getattr(instance, field)
            return default

        is_public = resolved("is_public", True)
        is_selectable_for_signup = resolved("is_selectable_for_signup", True)
        is_default = resolved("is_default", False)
        is_active = resolved("is_active", True)

        errors = {}

        if is_selectable_for_signup and not is_public:
            errors["is_selectable_for_signup"] = (
                "Signup-selectable plans must also be public."
            )

        if is_default:
            if not is_active:
                errors["is_active"] = "Default plan must remain active."
            if not is_public:
                errors["is_public"] = "Default plan must remain public."
            if not is_selectable_for_signup:
                errors["is_selectable_for_signup"] = (
                    "Default plan must remain selectable for signup."
                )

        if errors:
            raise serializers.ValidationError(errors)

        return attrs

    def create(self, validated_data):
        return SubscriptionService.create_or_update_plan(data=validated_data)

    def update(self, instance, validated_data):
        return SubscriptionService.create_or_update_plan(plan=instance, data=validated_data)

    def to_representation(self, instance):
        if isinstance(instance, dict):
            return super().to_representation(instance)
        return super().to_representation(
            SubscriptionService.serialize_internal_plan(plan=instance)
        )


def tenant_membership_queryset_for_entity(entity: Entity):
    account_entity_ids = Entity.objects.filter(
        customer_account=entity.customer_account,
        isactive=True,
    ).values_list("id", flat=True)
    return (
        UserEntityAccess.objects.filter(customer_account=entity.customer_account)
        .select_related("user", "granted_by", "customer_account")
        .annotate(
            entity_assignment_count=Count(
                "user__rbac_role_assignments",
                filter=Q(
                    user__rbac_role_assignments__entity=entity,
                    user__rbac_role_assignments__isactive=True,
                ),
                distinct=True,
            ),
            account_assignment_count=Count(
                "user__rbac_role_assignments",
                filter=Q(
                    user__rbac_role_assignments__entity_id__in=account_entity_ids,
                    user__rbac_role_assignments__isactive=True,
                ),
                distinct=True,
            ),
        )
        .order_by("user__first_name", "user__email", "id")
    )
