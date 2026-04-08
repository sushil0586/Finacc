from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import serializers

from entity.models import Entity

from .models import UserEntityAccess
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
        if membership.role == UserEntityAccess.Role.OWNER or membership.customer_account.owner_id == membership.user_id:
            raise serializers.ValidationError("Owner membership cannot be changed here.")
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


class TenantMembershipListResponseSerializer(serializers.Serializer):
    entity_id = serializers.IntegerField()
    entity_name = serializers.CharField()
    customer_account_id = serializers.IntegerField()
    customer_account_name = serializers.CharField()
    capabilities = serializers.DictField(child=serializers.BooleanField())
    role_choices = serializers.ListField(child=serializers.DictField())
    members = TenantMembershipSerializer(many=True)


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
