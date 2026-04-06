from datetime import datetime, time

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from entity.models import SubEntity

from .models import Menu, MenuPermission, Permission, RBACAuditLog, Role, RolePermission, UserRoleAssignment


User = get_user_model()


class DateFriendlyDateTimeField(serializers.DateTimeField):
    """Accept date-only inputs and safely serialize legacy date values."""

    def to_internal_value(self, value):
        if isinstance(value, datetime):
            if timezone.is_naive(value):
                return timezone.make_aware(value, timezone.get_current_timezone())
            return value
        if hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day") and not isinstance(value, str):
            value = datetime.combine(value, time.min)
            return timezone.make_aware(value, timezone.get_current_timezone())
        if isinstance(value, str) and len(value) == 10 and value.count("-") == 2:
            parsed = datetime.strptime(value, "%Y-%m-%d")
            return timezone.make_aware(parsed, timezone.get_current_timezone())
        return super().to_internal_value(value)

    def to_representation(self, value):
        if value is None:
            return None
        if isinstance(value, datetime):
            dt_value = value
        elif hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day"):
            dt_value = datetime.combine(value, time.min)
        else:
            return super().to_representation(value)
        if timezone.is_naive(dt_value):
            dt_value = timezone.make_aware(dt_value, timezone.get_current_timezone())
        return super().to_representation(dt_value)


class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = (
            "id",
            "code",
            "name",
            "module",
            "resource",
            "action",
            "description",
            "scope_type",
            "is_system_defined",
            "isactive",
        )


class RoleSerializer(serializers.ModelSerializer):
    entity_name = serializers.CharField(source="entity.entityname", read_only=True)

    class Meta:
        model = Role
        fields = (
            "id",
            "entity",
            "entity_name",
            "name",
            "code",
            "description",
            "role_level",
            "is_system_role",
            "is_assignable",
            "priority",
            "isactive",
        )


class RecursiveMenuSerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()

    class Meta:
        model = Menu
        fields = (
            "id",
            "name",
            "code",
            "menu_type",
            "route_path",
            "route_name",
            "icon",
            "sort_order",
            "depth",
            "children",
        )

    def get_children(self, obj):
        serializer = RecursiveMenuSerializer(
            obj.children.filter(isactive=True).order_by("sort_order", "name"),
            many=True,
            context=self.context,
        )
        return serializer.data


class MenuNodeSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    code = serializers.CharField()
    menu_code = serializers.CharField()
    menu_type = serializers.CharField()
    route_path = serializers.CharField(allow_blank=True)
    route_name = serializers.CharField(allow_blank=True)
    icon = serializers.CharField(allow_blank=True)
    sort_order = serializers.IntegerField()
    depth = serializers.IntegerField()
    children = serializers.ListField()


class RoleSummarySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    code = serializers.CharField(allow_blank=True)
    description = serializers.CharField(allow_blank=True)
    source = serializers.CharField()
    is_primary = serializers.BooleanField(default=False)


class EffectivePermissionsSerializer(serializers.Serializer):
    entity_id = serializers.IntegerField()
    entity_name = serializers.CharField()
    roles = RoleSummarySerializer(many=True)
    permissions = serializers.ListField(child=serializers.CharField())


class EffectiveMenuTreeSerializer(serializers.Serializer):
    entity_id = serializers.IntegerField()
    entity_name = serializers.CharField()
    roles = RoleSummarySerializer(many=True)
    menus = MenuNodeSerializer(many=True)


class PermissionAdminSerializer(serializers.ModelSerializer):
    def validate_code(self, value):
        qs = Permission.objects.filter(code__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Permission code must be unique.")
        return value

    class Meta:
        model = Permission
        fields = (
            "id",
            "code",
            "name",
            "module",
            "resource",
            "action",
            "description",
            "scope_type",
            "is_system_defined",
            "metadata",
            "isactive",
        )


class RoleAdminSerializer(serializers.ModelSerializer):
    entity_name = serializers.CharField(source="entity.entityname", read_only=True)
    permission_count = serializers.IntegerField(read_only=True)
    assignment_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Role
        fields = (
            "id",
            "entity",
            "entity_name",
            "name",
            "code",
            "description",
            "role_level",
            "is_system_role",
            "is_assignable",
            "priority",
            "metadata",
            "permission_count",
            "assignment_count",
            "isactive",
        )

    def validate(self, attrs):
        entity = attrs.get("entity", getattr(self.instance, "entity", None))
        code = attrs.get("code", getattr(self.instance, "code", None))
        if entity and code:
            qs = Role.objects.filter(entity=entity, code__iexact=code)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({"code": "Role code must be unique within the entity."})
        return attrs


class MenuAdminSerializer(serializers.ModelSerializer):
    parent_name = serializers.CharField(source="parent.name", read_only=True)
    permission_ids = serializers.SerializerMethodField()

    class Meta:
        model = Menu
        fields = (
            "id",
            "parent",
            "parent_name",
            "name",
            "code",
            "menu_type",
            "route_path",
            "route_name",
            "icon",
            "sort_order",
            "depth",
            "is_system_menu",
            "metadata",
            "permission_ids",
            "isactive",
        )

    def get_permission_ids(self, obj):
        return list(
            obj.menu_permissions.filter(
                isactive=True,
                relation_type=MenuPermission.RELATION_VISIBILITY,
            ).values_list("permission_id", flat=True)
        )

    def validate_code(self, value):
        qs = Menu.objects.filter(code__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Menu code must be unique.")
        return value


class MenuAdminTreeSerializer(serializers.ModelSerializer):
    permission_ids = serializers.SerializerMethodField()
    children = serializers.SerializerMethodField()

    class Meta:
        model = Menu
        fields = (
            "id",
            "parent",
            "name",
            "code",
            "menu_type",
            "route_path",
            "route_name",
            "icon",
            "sort_order",
            "depth",
            "is_system_menu",
            "permission_ids",
            "children",
            "isactive",
        )

    def get_permission_ids(self, obj):
        return list(
            obj.menu_permissions.filter(
                isactive=True,
                relation_type=MenuPermission.RELATION_VISIBILITY,
            ).values_list("permission_id", flat=True)
        )

    def get_children(self, obj):
        serializer = MenuAdminTreeSerializer(
            obj.children.filter(isactive=True).order_by("sort_order", "name"),
            many=True,
            context=self.context,
        )
        return serializer.data


class RolePermissionBulkSerializer(serializers.Serializer):
    permission_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=True,
    )


class MenuPermissionBulkSerializer(serializers.Serializer):
    permission_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=True,
    )
    relation_type = serializers.ChoiceField(
        choices=MenuPermission.RELATION_CHOICES,
        default=MenuPermission.RELATION_VISIBILITY,
    )


class UserOptionSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "email", "username", "first_name", "last_name", "full_name", "is_active")

    def get_full_name(self, obj):
        full_name = f"{obj.first_name} {obj.last_name}".strip()
        return full_name or obj.email or obj.username


class UserRoleAssignmentAdminSerializer(serializers.ModelSerializer):
    entity = serializers.PrimaryKeyRelatedField(read_only=True)
    scope_data = serializers.JSONField(required=False, allow_null=True, default=dict)
    effective_from = DateFriendlyDateTimeField(required=False, allow_null=True)
    effective_to = DateFriendlyDateTimeField(required=False, allow_null=True)
    user_name = serializers.SerializerMethodField()
    role_name = serializers.CharField(source="role.name", read_only=True)
    entity_name = serializers.CharField(source="entity.entityname", read_only=True)
    subentity_name = serializers.CharField(source="subentity.subentityname", read_only=True)

    class Meta:
        model = UserRoleAssignment
        fields = (
            "id",
            "user",
            "user_name",
            "entity",
            "entity_name",
            "role",
            "role_name",
            "subentity",
            "subentity_name",
            "effective_from",
            "effective_to",
            "is_primary",
            "scope_data",
            "isactive",
        )

    def validate_scope_data(self, value):
        return value or {}

    def get_user_name(self, obj):
        user = obj.user
        full_name = f"{user.first_name} {user.last_name}".strip()
        return full_name or user.email or user.username

    def validate(self, attrs):
        user = attrs.get("user", getattr(self.instance, "user", None))
        entity = attrs.get("entity", getattr(self.instance, "entity", None))
        role = attrs.get("role", getattr(self.instance, "role", None))
        subentity = attrs.get("subentity", getattr(self.instance, "subentity", None))
        effective_from = attrs.get("effective_from", getattr(self.instance, "effective_from", None))
        effective_to = attrs.get("effective_to", getattr(self.instance, "effective_to", None))
        qs = UserRoleAssignment.objects.filter(user=user, entity=entity, role=role, subentity=subentity)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if user and entity and role and qs.exists():
            raise serializers.ValidationError("This user already has the same role assignment for this entity/subentity.")
        if effective_from and effective_to and effective_from > effective_to:
            raise serializers.ValidationError({"effective_to": "effective_to cannot be before effective_from."})
        if role and entity and role.role_level == Role.LEVEL_ENTITY and role.entity_id != entity.id:
            raise serializers.ValidationError({"role": "Selected role does not belong to this entity."})
        if subentity and entity and subentity.entity_id != entity.id:
            raise serializers.ValidationError({"subentity": "Selected subentity does not belong to this entity."})
        return attrs


class RolePermissionsStateSerializer(serializers.Serializer):
    role = RoleAdminSerializer()
    assigned_permission_ids = serializers.ListField(child=serializers.IntegerField())
    permissions = PermissionAdminSerializer(many=True)


class MenuPermissionsStateSerializer(serializers.Serializer):
    menu = MenuAdminSerializer()
    relation_type = serializers.CharField()
    assigned_permission_ids = serializers.ListField(child=serializers.IntegerField())
    permissions = PermissionAdminSerializer(many=True)


class RBACAdminBootstrapSerializer(serializers.Serializer):
    entity_id = serializers.IntegerField()
    entity_name = serializers.CharField()
    roles = RoleAdminSerializer(many=True)
    permissions = PermissionAdminSerializer(many=True)
    menus = MenuAdminTreeSerializer(many=True)
    assignments = UserRoleAssignmentAdminSerializer(many=True)
    users = UserOptionSerializer(many=True)
    permission_groups = serializers.ListField()


class PermissionGroupSerializer(serializers.Serializer):
    module = serializers.CharField()
    resources = serializers.ListField()


class EffectiveAccessPreviewSerializer(serializers.Serializer):
    entity_id = serializers.IntegerField()
    entity_name = serializers.CharField()
    user = UserOptionSerializer()
    roles = RoleSummarySerializer(many=True)
    permissions = serializers.ListField(child=serializers.CharField())
    permission_groups = serializers.ListField()
    menus = MenuNodeSerializer(many=True)


class RoleCloneSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    code = serializers.CharField(max_length=100)
    description = serializers.CharField(required=False, allow_blank=True)


class RoleTemplateApplySerializer(serializers.Serializer):
    template_code = serializers.CharField(max_length=100)
    permission_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=True,
        required=False,
    )


class BulkAssignmentSerializer(serializers.Serializer):
    user_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), allow_empty=False)
    role = serializers.IntegerField(min_value=1)
    subentity = serializers.IntegerField(required=False, allow_null=True)
    effective_from = DateFriendlyDateTimeField(required=False, allow_null=True)
    effective_to = DateFriendlyDateTimeField(required=False, allow_null=True)
    is_primary = serializers.BooleanField(default=False)
    isactive = serializers.BooleanField(default=True)
    scope_data = serializers.JSONField(required=False, allow_null=True, default=dict)

    def validate(self, attrs):
        effective_from = attrs.get("effective_from")
        effective_to = attrs.get("effective_to")
        if effective_from and effective_to and effective_from > effective_to:
            raise serializers.ValidationError({"effective_to": "effective_to cannot be before effective_from."})
        return attrs


class UserSearchResultSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    entity_assignment_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "username",
            "first_name",
            "last_name",
            "full_name",
            "is_active",
            "entity_assignment_count",
        )

    def get_full_name(self, obj):
        full_name = f"{obj.first_name} {obj.last_name}".strip()
        return full_name or obj.email or obj.username


class CreateUserWithAssignmentSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    email = serializers.EmailField()
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(max_length=128, min_length=6, write_only=True)
    role = serializers.PrimaryKeyRelatedField(queryset=Role.objects.filter(isactive=True))
    subentity = serializers.PrimaryKeyRelatedField(queryset=SubEntity.objects.filter(isactive=True), required=False, allow_null=True)
    effective_from = DateFriendlyDateTimeField(required=False, allow_null=True)
    effective_to = DateFriendlyDateTimeField(required=False, allow_null=True)
    is_primary = serializers.BooleanField(default=False)
    isactive = serializers.BooleanField(default=True)
    scope_data = serializers.JSONField(required=False, allow_null=True, default=dict)

    def validate_email(self, value):
        normalized = (value or "").strip().lower()
        if User.objects.filter(email__iexact=normalized).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return normalized

    def validate_username(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Username is required.")
        return value

    def validate_password(self, value):
        validate_password(value)
        return value

    def validate(self, attrs):
        entity = self.context["entity"]
        role = attrs["role"]
        subentity = attrs.get("subentity")
        effective_from = attrs.get("effective_from")
        effective_to = attrs.get("effective_to")
        if role.role_level == Role.LEVEL_ENTITY and role.entity_id != entity.id:
            raise serializers.ValidationError({"role": "Selected role does not belong to this entity."})
        if subentity and subentity.entity_id != entity.id:
            raise serializers.ValidationError({"subentity": "Selected subentity does not belong to this entity."})
        if effective_from and effective_to and effective_from > effective_to:
            raise serializers.ValidationError({"effective_to": "effective_to cannot be before effective_from."})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        entity = self.context["entity"]
        actor = self.context["actor"]
        role = validated_data.pop("role")
        subentity = validated_data.pop("subentity", None)
        user = User.objects.create_user(
            username=validated_data.pop("username"),
            email=validated_data.pop("email"),
            password=validated_data.pop("password"),
            first_name=(validated_data.pop("first_name", "") or "").strip(),
            last_name=(validated_data.pop("last_name", "") or "").strip(),
            is_active=True,
        )
        assignment = UserRoleAssignment.objects.create(
            user=user,
            entity=entity,
            role=role,
            subentity=subentity,
            assigned_by=actor,
            effective_from=validated_data.get("effective_from"),
            effective_to=validated_data.get("effective_to"),
            is_primary=validated_data.get("is_primary", False),
            isactive=validated_data.get("isactive", True),
            scope_data=validated_data.get("scope_data") or {},
        )
        return {
            "user": user,
            "assignment": assignment,
        }


class CreateUserWithAssignmentResponseSerializer(serializers.Serializer):
    user = UserOptionSerializer()
    assignment = UserRoleAssignmentAdminSerializer()


class RBACAuditLogSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()
    entity_name = serializers.CharField(source="entity.entityname", read_only=True)

    class Meta:
        model = RBACAuditLog
        fields = (
            "id",
            "object_type",
            "object_id",
            "entity",
            "entity_name",
            "action",
            "actor",
            "actor_name",
            "message",
            "changes",
            "created_at",
        )

    def get_actor_name(self, obj):
        if not obj.actor_id:
            return ""
        actor = obj.actor
        full_name = f"{actor.first_name} {actor.last_name}".strip()
        return full_name or actor.email or actor.username
