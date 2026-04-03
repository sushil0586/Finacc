from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Menu, MenuPermission, Permission, RBACAuditLog, Role, RolePermission, UserRoleAssignment


User = get_user_model()


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

    def get_user_name(self, obj):
        user = obj.user
        full_name = f"{user.first_name} {user.last_name}".strip()
        return full_name or user.email or user.username

    def validate(self, attrs):
        user = attrs.get("user", getattr(self.instance, "user", None))
        entity = attrs.get("entity", getattr(self.instance, "entity", None))
        role = attrs.get("role", getattr(self.instance, "role", None))
        subentity = attrs.get("subentity", getattr(self.instance, "subentity", None))
        qs = UserRoleAssignment.objects.filter(user=user, entity=entity, role=role, subentity=subentity)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if user and entity and role and qs.exists():
            raise serializers.ValidationError("This user already has the same role assignment for this entity/subentity.")
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
    is_primary = serializers.BooleanField(default=False)
    isactive = serializers.BooleanField(default=True)
    scope_data = serializers.JSONField(required=False)


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
