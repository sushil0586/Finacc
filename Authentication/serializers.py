from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers

from Authentication.models import User
from rbac.models import UserRoleAssignment
from subscriptions.services import SubscriptionService


class RegisterSerializer(serializers.ModelSerializer):
    intent = serializers.ChoiceField(
        choices=(
            SubscriptionService.INTENT_STANDARD,
            SubscriptionService.INTENT_TRIAL,
        ),
        required=False,
        write_only=True,
        default=SubscriptionService.INTENT_STANDARD,
    )
    password = serializers.CharField(
        max_length=128,
        min_length=6,
        write_only=True,
        style={"input_type": "password"},
    )

    class Meta:
        model = User
        fields = (
            "username",
            "first_name",
            "last_name",
            "email",
            "password",
            "intent",
        )

    def validate_email(self, value):
        value = (value or "").strip().lower()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_username(self, value):
        return (value or "").strip()

    def validate_password(self, value):
        validate_password(value)
        return value

    @transaction.atomic
    def create(self, validated_data):
        intent = validated_data.pop("intent", SubscriptionService.INTENT_STANDARD)

        validated_data["email"] = (validated_data.get("email") or "").strip().lower()
        validated_data["username"] = (validated_data.get("username") or "").strip()
        validated_data["first_name"] = (validated_data.get("first_name") or "").strip()
        validated_data["last_name"] = (validated_data.get("last_name") or "").strip()

        user = User.objects.create_user(**validated_data)

        SubscriptionService.handle_signup(
            user=user,
            intent=intent,
        )

        user._signup_intent = intent
        return user


class UserEntitySummarySerializer(serializers.Serializer):
    entityid = serializers.IntegerField()
    entityname = serializers.CharField(allow_null=True)
    email = serializers.EmailField()
    gstno = serializers.CharField(allow_null=True)
    role = serializers.IntegerField(allow_null=True)
    roleid = serializers.IntegerField(allow_null=True)


class UserSerializer(serializers.ModelSerializer):
    uentity = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "uentity",
        )

    def get_uentity(self, obj):
        now = timezone.now()
        assignments = (
            UserRoleAssignment.objects.filter(
                user=obj,
                isactive=True,
                role__isactive=True,
            )
            .filter(
                Q(effective_from__isnull=True) | Q(effective_from__lte=now),
                Q(effective_to__isnull=True) | Q(effective_to__gte=now),
            )
            .select_related("entity", "role")
        )

        def _entity_gst(entity):
            row = entity.gst_registrations.filter(isactive=True, is_primary=True).first()
            return row.gstin if row else None

        return [
            {
                "entityid": item.entity_id,
                "entityname": item.entity.entityname,
                "email": obj.email,
                "gstno": _entity_gst(item.entity),
                "role": item.role_id,
                "roleid": item.role_id,
            }
            for item in assignments
        ]


class AuthenticatedUserSerializer(serializers.ModelSerializer):
    entity_count = serializers.SerializerMethodField()
    is_locked = serializers.ReadOnlyField()

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "email_verified",
            "is_active",
            "is_staff",
            "is_locked",
            "entity_count",
        )

    def get_entity_count(self, obj):
        now = timezone.now()
        return (
            UserRoleAssignment.objects.filter(
                user=obj,
                isactive=True,
                role__isactive=True,
            )
            .filter(
                Q(effective_from__isnull=True) | Q(effective_from__lte=now),
                Q(effective_to__isnull=True) | Q(effective_to__gte=now),
            )
            .values("entity_id")
            .distinct()
            .count()
        )


class LoginSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        max_length=128,
        min_length=6,
        write_only=True,
        style={"input_type": "password"},
    )
    token = serializers.CharField(read_only=True)
    id = serializers.IntegerField(read_only=True)

    class Meta:
        model = User
        fields = ("email", "password", "token", "id")
        extra_kwargs = {"email": {"validators": []}}

    def validate_email(self, value):
        return (value or "").strip().lower()


class LogoutSerializer(serializers.Serializer):
    token = serializers.CharField(required=False, allow_blank=True)


class RefreshTokenSerializer(serializers.Serializer):
    refresh_token = serializers.CharField()


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        return (value or "").strip().lower()


class ResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6)
    new_password = serializers.CharField(
        max_length=128,
        min_length=6,
        write_only=True,
        style={"input_type": "password"},
    )

    def validate_email(self, value):
        return (value or "").strip().lower()

    def validate_new_password(self, value):
        validate_password(value)
        return value


class RequestEmailVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False)

    def validate_email(self, value):
        return (value or "").strip().lower()


class ResendEmailVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        return (value or "").strip().lower()


class VerifyEmailSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6)

    def validate_email(self, value):
        return (value or "").strip().lower()


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(
        required=True,
        write_only=True,
        style={"input_type": "password"},
    )
    new_password = serializers.CharField(
        required=True,
        write_only=True,
        style={"input_type": "password"},
    )

    def validate_new_password(self, value):
        validate_password(value)
        return value

# Compatibility alias retained for external imports that still use the old class name.
Registerserializers = RegisterSerializer

