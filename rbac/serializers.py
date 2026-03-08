from rest_framework import serializers

from entity.models import Entity
from .models import Menu, Permission, Role


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
