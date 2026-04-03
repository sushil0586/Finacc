from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import (
    ListAPIView,
    ListCreateAPIView,
    RetrieveUpdateDestroyAPIView,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Menu, MenuPermission, Permission, RBACAuditLog, Role, RolePermission, UserRoleAssignment
from .serializers import (
    EffectiveMenuTreeSerializer,
    EffectiveAccessPreviewSerializer,
    EffectivePermissionsSerializer,
    BulkAssignmentSerializer,
    MenuAdminSerializer,
    MenuAdminTreeSerializer,
    MenuPermissionsStateSerializer,
    PermissionAdminSerializer,
    PermissionSerializer,
    PermissionGroupSerializer,
    RBACAuditLogSerializer,
    RBACAdminBootstrapSerializer,
    RecursiveMenuSerializer,
    RoleCloneSerializer,
    RoleAdminSerializer,
    RolePermissionsStateSerializer,
    RoleTemplateApplySerializer,
    RoleSerializer,
    UserOptionSerializer,
    UserRoleAssignmentAdminSerializer,
    MenuPermissionBulkSerializer,
    RolePermissionBulkSerializer,
)
from .services import (
    EffectiveMenuService,
    EffectivePermissionService,
    MenuTreeService,
    RBACAuditService,
    RoleCloneService,
    RoleTemplateService,
)


User = get_user_model()


def grouped_permission_payload(permission_queryset):
    groups = {}
    for permission in permission_queryset:
        module_bucket = groups.setdefault(permission.module, {})
        resource_bucket = module_bucket.setdefault(permission.resource, [])
        resource_bucket.append(
            {
                "id": permission.id,
                "code": permission.code,
                "name": permission.name,
                "action": permission.action,
                "scope_type": permission.scope_type,
                "is_system_defined": permission.is_system_defined,
                "isactive": permission.isactive,
            }
        )
    return [
        {
            "module": module,
            "resources": [
                {"resource": resource, "permissions": sorted(permissions, key=lambda item: (item["action"], item["name"]))}
                for resource, permissions in sorted(resource_map.items())
            ],
        }
        for module, resource_map in sorted(groups.items())
    ]


class RBACEntityAccessMixin:
    permission_classes = [IsAuthenticated]

    def _entity_from_request(self, request):
        entity_id = request.query_params.get("entity") or request.data.get("entity")
        if not entity_id:
            return None, Response({"detail": "entity is required."}, status=status.HTTP_400_BAD_REQUEST)

        entity = EffectivePermissionService.entity_for_user(request.user, entity_id)
        if not entity:
            return None, Response({"detail": "You do not have access to this entity."}, status=status.HTTP_403_FORBIDDEN)
        return entity, None

    def _soft_delete(self, obj, *, actor, message):
        obj.isactive = False
        obj.save(update_fields=["isactive", "updated_at"])
        RBACAuditService.log(
            actor=actor,
            entity=getattr(obj, "entity", None),
            object_type=obj.__class__.__name__.lower(),
            object_id=obj.pk,
            action=RBACAuditLog.ACTION_DEACTIVATE,
            message=message,
            changes={"isactive": False},
        )

    def _assert_not_system_role(self, role, action_label="change"):
        if role.is_system_role:
            raise ValidationError({"detail": f"System roles cannot be {action_label}d."})


class RBACHealthView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(
            {
                "permissions": Permission.objects.count(),
                "roles": Role.objects.count(),
                "menus": Menu.objects.count(),
            }
        )


class PermissionListView(ListAPIView):
    serializer_class = PermissionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Permission.objects.filter(isactive=True).order_by("module", "resource", "action", "code")
        module = self.request.query_params.get("module")
        if module:
            queryset = queryset.filter(module=module)
        return queryset


class RoleListView(ListAPIView):
    serializer_class = RoleSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Role.objects.filter(isactive=True).select_related("entity").order_by("role_level", "priority", "name")
        entity_id = self.request.query_params.get("entity")
        if entity_id:
            queryset = queryset.filter(entity_id=entity_id)
        return queryset


class MenuTreeView(ListAPIView):
    serializer_class = RecursiveMenuSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return MenuTreeService.root_queryset()


class UserRolesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        entity_id = request.query_params.get("entity")
        if not entity_id:
            return Response({"detail": "entity is required."}, status=status.HTTP_400_BAD_REQUEST)

        entity = EffectivePermissionService.entity_for_user(request.user, entity_id)
        if not entity:
            return Response({"detail": "You do not have access to this entity."}, status=status.HTTP_403_FORBIDDEN)

        roles = EffectivePermissionService.role_summaries_for_user(request.user, entity.id)
        return Response(
            {
                "entity_id": entity.id,
                "entity_name": entity.entityname,
                "roles": roles,
            }
        )


class UserPermissionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        entity_id = request.query_params.get("entity")
        role_id = request.query_params.get("role")
        if not entity_id:
            return Response({"detail": "entity is required."}, status=status.HTTP_400_BAD_REQUEST)

        entity = EffectivePermissionService.entity_for_user(request.user, entity_id)
        if not entity:
            return Response({"detail": "You do not have access to this entity."}, status=status.HTTP_403_FORBIDDEN)

        payload = {
            "entity_id": entity.id,
            "entity_name": entity.entityname,
            "roles": EffectivePermissionService.role_summaries_for_user(request.user, entity.id),
            "permissions": sorted(
                EffectivePermissionService.permission_codes_for_user(
                    request.user,
                    entity.id,
                    role_id=int(role_id) if role_id else None,
                )
            ),
        }
        serializer = EffectivePermissionsSerializer(payload)
        return Response(serializer.data)


class UserMenusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        entity_id = request.query_params.get("entity")
        role_id = request.query_params.get("role")
        if not entity_id:
            return Response({"detail": "entity is required."}, status=status.HTTP_400_BAD_REQUEST)

        entity = EffectivePermissionService.entity_for_user(request.user, entity_id)
        if not entity:
            return Response({"detail": "You do not have access to this entity."}, status=status.HTTP_403_FORBIDDEN)

        payload = {
            "entity_id": entity.id,
            "entity_name": entity.entityname,
            "roles": EffectivePermissionService.role_summaries_for_user(request.user, entity.id),
            "menus": EffectiveMenuService.menu_tree_for_user(
                request.user,
                entity.id,
                role_id=int(role_id) if role_id else None,
            ),
        }
        serializer = EffectiveMenuTreeSerializer(payload)
        return Response(serializer.data)


class RBACAdminBootstrapView(RBACEntityAccessMixin, APIView):
    def get(self, request):
        entity, error_response = self._entity_from_request(request)
        if error_response:
            return error_response

        roles = list(
            Role.objects.filter(entity=entity, isactive=True)
            .select_related("entity")
            .annotate(
                permission_count=Count("role_permissions", filter=Q(role_permissions__isactive=True), distinct=True),
                assignment_count=Count("user_assignments", filter=Q(user_assignments__isactive=True), distinct=True),
            )
            .order_by("priority", "name")
        )
        permissions = list(Permission.objects.filter(isactive=True).order_by("module", "resource", "action", "name"))
        menus = list(Menu.objects.filter(parent__isnull=True, isactive=True).order_by("sort_order", "name"))
        assignments = list(
            UserRoleAssignment.objects.filter(entity=entity, isactive=True)
            .select_related("user", "role", "entity", "subentity")
            .order_by("user__first_name", "user__email", "role__priority", "role__name")
        )

        user_ids = set(UserRoleAssignment.objects.filter(entity=entity).values_list("user_id", flat=True))
        users = list(User.objects.filter(id__in=user_ids, is_active=True).order_by("first_name", "email"))

        payload = {
            "entity_id": entity.id,
            "entity_name": entity.entityname,
            "roles": roles,
            "permissions": permissions,
            "menus": menus,
            "assignments": assignments,
            "users": users,
            "permission_groups": grouped_permission_payload(permissions),
        }
        serializer = RBACAdminBootstrapSerializer(payload)
        return Response(serializer.data)


class PermissionAdminListCreateView(ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PermissionAdminSerializer

    def get_queryset(self):
        queryset = Permission.objects.all().order_by("module", "resource", "action", "name")
        module = self.request.query_params.get("module")
        if module:
            queryset = queryset.filter(module=module)
        resource = self.request.query_params.get("resource")
        if resource:
            queryset = queryset.filter(resource=resource)
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(Q(code__icontains=search) | Q(name__icontains=search))
        return queryset

    def perform_create(self, serializer):
        permission = serializer.save()
        RBACAuditService.log(
            actor=self.request.user,
            object_type="permission",
            object_id=permission.id,
            action=RBACAuditLog.ACTION_CREATE,
            message=f"Created permission {permission.code}.",
            changes={"code": permission.code},
        )


class PermissionAdminDetailView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PermissionAdminSerializer
    queryset = Permission.objects.all()

    def perform_update(self, serializer):
        permission = serializer.save()
        RBACAuditService.log(
            actor=self.request.user,
            object_type="permission",
            object_id=permission.id,
            action=RBACAuditLog.ACTION_UPDATE,
            message=f"Updated permission {permission.code}.",
        )

    def destroy(self, request, *args, **kwargs):
        permission = self.get_object()
        permission.isactive = False
        permission.save(update_fields=["isactive", "updated_at"])
        RBACAuditService.log(
            actor=request.user,
            object_type="permission",
            object_id=permission.id,
            action=RBACAuditLog.ACTION_DEACTIVATE,
            message=f"Deactivated permission {permission.code}.",
            changes={"isactive": False},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class RoleAdminListCreateView(RBACEntityAccessMixin, ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = RoleAdminSerializer

    def get_queryset(self):
        entity, error_response = self._entity_from_request(self.request)
        if error_response:
            return Role.objects.none()
        queryset = (
            Role.objects.filter(entity=entity)
            .select_related("entity")
            .annotate(
                permission_count=Count("role_permissions", filter=Q(role_permissions__isactive=True), distinct=True),
                assignment_count=Count("user_assignments", filter=Q(user_assignments__isactive=True), distinct=True),
            )
            .order_by("priority", "name")
        )
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(code__icontains=search))
        return queryset

    def perform_create(self, serializer):
        entity, error_response = self._entity_from_request(self.request)
        if error_response:
            raise ValidationError(error_response.data)
        role = serializer.save(entity=entity, role_level=Role.LEVEL_ENTITY, createdby=self.request.user)
        RBACAuditService.log(
            actor=self.request.user,
            entity=entity,
            object_type="role",
            object_id=role.id,
            action=RBACAuditLog.ACTION_CREATE,
            message=f"Created role {role.name}.",
        )


class RoleAdminDetailView(RBACEntityAccessMixin, RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = RoleAdminSerializer

    def get_queryset(self):
        entity, error_response = self._entity_from_request(self.request)
        if error_response:
            return Role.objects.none()
        return (
            Role.objects.filter(role_level=Role.LEVEL_ENTITY, entity=entity)
            .select_related("entity")
            .annotate(
                permission_count=Count("role_permissions", filter=Q(role_permissions__isactive=True), distinct=True),
                assignment_count=Count("user_assignments", filter=Q(user_assignments__isactive=True), distinct=True),
            )
        )

    def perform_update(self, serializer):
        role = self.get_object()
        self._assert_not_system_role(role, "change")
        role = serializer.save()
        RBACAuditService.log(
            actor=self.request.user,
            entity=role.entity,
            object_type="role",
            object_id=role.id,
            action=RBACAuditLog.ACTION_UPDATE,
            message=f"Updated role {role.name}.",
        )

    def destroy(self, request, *args, **kwargs):
        role = self.get_object()
        self._assert_not_system_role(role, "delete")
        self._soft_delete(role, actor=request.user, message=f"Deactivated role {role.name}.")
        return Response(status=status.HTTP_204_NO_CONTENT)


class RolePermissionsStateView(RBACEntityAccessMixin, RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        entity, error_response = self._entity_from_request(self.request)
        if error_response:
            return Role.objects.none()
        return Role.objects.filter(role_level=Role.LEVEL_ENTITY, entity=entity).select_related("entity")

    def get(self, request, *args, **kwargs):
        role = self.get_object()
        if not EffectivePermissionService.entity_for_user(request.user, role.entity_id):
            return Response({"detail": "You do not have access to this entity."}, status=status.HTTP_403_FORBIDDEN)

        payload = {
            "role": role,
            "assigned_permission_ids": list(
                RolePermission.objects.filter(role=role, isactive=True).values_list("permission_id", flat=True)
            ),
            "permissions": list(Permission.objects.filter(isactive=True).order_by("module", "resource", "action", "name")),
        }
        serializer = RolePermissionsStateSerializer(payload)
        return Response(serializer.data)

    def put(self, request, *args, **kwargs):
        role = self.get_object()
        if not EffectivePermissionService.entity_for_user(request.user, role.entity_id):
            return Response({"detail": "You do not have access to this entity."}, status=status.HTTP_403_FORBIDDEN)
        self._assert_not_system_role(role, "change")

        serializer = RolePermissionBulkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        permission_ids = set(serializer.validated_data["permission_ids"])

        permission_ids = set(Permission.objects.filter(id__in=permission_ids, isactive=True).values_list("id", flat=True))
        removed_ids = list(RolePermission.objects.filter(role=role).exclude(permission_id__in=permission_ids).values_list("permission_id", flat=True))
        RolePermission.objects.filter(role=role).exclude(permission_id__in=permission_ids).delete()
        existing_ids = set(RolePermission.objects.filter(role=role).values_list("permission_id", flat=True))
        missing_ids = permission_ids - existing_ids
        RolePermission.objects.bulk_create(
            [
                RolePermission(role=role, permission_id=permission_id, effect=RolePermission.EFFECT_ALLOW)
                for permission_id in missing_ids
            ]
        )
        RBACAuditService.log(
            actor=request.user,
            entity=role.entity,
            object_type="role",
            object_id=role.id,
            action=RBACAuditLog.ACTION_UPDATE,
            message=f"Updated permissions for role {role.name}.",
            changes={"granted_permission_ids": sorted(missing_ids), "removed_permission_ids": sorted(removed_ids)},
        )
        return self.get(request, *args, **kwargs)


class MenuAdminListCreateView(RBACEntityAccessMixin, ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = MenuAdminSerializer

    def get_queryset(self):
        entity, error_response = self._entity_from_request(self.request)
        if error_response:
            return Menu.objects.none()
        queryset = Menu.objects.select_related("parent").order_by("depth", "parent_id", "sort_order", "name")
        parent_id = self.request.query_params.get("parent")
        if parent_id == "null":
            queryset = queryset.filter(parent__isnull=True)
        elif parent_id:
            queryset = queryset.filter(parent_id=parent_id)
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(code__icontains=search) | Q(route_name__icontains=search))
        return queryset

    def perform_create(self, serializer):
        entity, error_response = self._entity_from_request(self.request)
        if error_response:
            raise ValidationError(error_response.data)
        menu = serializer.save()
        RBACAuditService.log(
            actor=self.request.user,
            entity=entity,
            object_type="menu",
            object_id=menu.id,
            action=RBACAuditLog.ACTION_CREATE,
            message=f"Created menu {menu.code}.",
            changes={"parent_id": menu.parent_id},
        )


class MenuAdminDetailView(RBACEntityAccessMixin, RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = MenuAdminSerializer

    def get_queryset(self):
        entity, error_response = self._entity_from_request(self.request)
        if error_response:
            return Menu.objects.none()
        return Menu.objects.select_related("parent")

    def perform_update(self, serializer):
        original = self.get_object()
        previous_parent_id = original.parent_id
        menu = serializer.save()
        action = RBACAuditLog.ACTION_UPDATE
        message = f"Updated menu {menu.code}."
        changes = {"parent_id": menu.parent_id}
        if previous_parent_id != menu.parent_id:
            message = f"Moved menu {menu.code}."
        entity, _ = self._entity_from_request(self.request)
        RBACAuditService.log(
            actor=self.request.user,
            entity=entity,
            object_type="menu",
            object_id=menu.id,
            action=action,
            message=message,
            changes=changes,
        )

    def destroy(self, request, *args, **kwargs):
        menu = self.get_object()
        self._soft_delete(menu, actor=request.user, message=f"Deactivated menu {menu.code}.")
        return Response(status=status.HTTP_204_NO_CONTENT)


class MenuPermissionsStateView(RBACEntityAccessMixin, RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    queryset = Menu.objects.select_related("parent")

    def get(self, request, *args, **kwargs):
        entity, error_response = self._entity_from_request(request)
        if error_response:
            return error_response
        menu = self.get_object()
        relation_type = request.query_params.get("relation_type", MenuPermission.RELATION_VISIBILITY)
        payload = {
            "menu": menu,
            "relation_type": relation_type,
            "assigned_permission_ids": list(
                MenuPermission.objects.filter(
                    menu=menu,
                    relation_type=relation_type,
                    isactive=True,
                ).values_list("permission_id", flat=True)
            ),
            "permissions": list(Permission.objects.filter(isactive=True).order_by("module", "resource", "action", "name")),
        }
        serializer = MenuPermissionsStateSerializer(payload)
        return Response(serializer.data)

    def put(self, request, *args, **kwargs):
        entity, error_response = self._entity_from_request(request)
        if error_response:
            return error_response
        menu = self.get_object()
        serializer = MenuPermissionBulkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        permission_ids = set(serializer.validated_data["permission_ids"])
        relation_type = serializer.validated_data["relation_type"]

        permission_ids = set(Permission.objects.filter(id__in=permission_ids, isactive=True).values_list("id", flat=True))
        removed_ids = list(
            MenuPermission.objects.filter(menu=menu, relation_type=relation_type)
            .exclude(permission_id__in=permission_ids)
            .values_list("permission_id", flat=True)
        )
        MenuPermission.objects.filter(menu=menu, relation_type=relation_type).exclude(permission_id__in=permission_ids).delete()
        existing_ids = set(
            MenuPermission.objects.filter(menu=menu, relation_type=relation_type).values_list("permission_id", flat=True)
        )
        missing_ids = permission_ids - existing_ids
        MenuPermission.objects.bulk_create(
            [
                MenuPermission(menu=menu, permission_id=permission_id, relation_type=relation_type)
                for permission_id in missing_ids
            ]
        )
        RBACAuditService.log(
            actor=request.user,
            entity=entity,
            object_type="menu",
            object_id=menu.id,
            action=RBACAuditLog.ACTION_UPDATE,
            message=f"Updated {relation_type} permissions for menu {menu.code}.",
            changes={"relation_type": relation_type, "granted_permission_ids": sorted(missing_ids), "removed_permission_ids": sorted(removed_ids)},
        )
        request._request.GET = request._request.GET.copy()
        request._request.GET["relation_type"] = relation_type
        return self.get(request, *args, **kwargs)


class MenuAdminTreeView(RBACEntityAccessMixin, ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = MenuAdminTreeSerializer

    def get_queryset(self):
        entity, error_response = self._entity_from_request(self.request)
        if error_response:
            return Menu.objects.none()
        return Menu.objects.filter(parent__isnull=True, isactive=True).order_by("sort_order", "name")


class UserRoleAssignmentAdminListCreateView(RBACEntityAccessMixin, ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserRoleAssignmentAdminSerializer

    def get_queryset(self):
        entity, error_response = self._entity_from_request(self.request)
        if error_response:
            return UserRoleAssignment.objects.none()
        queryset = (
            UserRoleAssignment.objects.filter(entity=entity)
            .select_related("user", "role", "entity", "subentity")
            .order_by("user__first_name", "user__email", "role__priority", "role__name")
        )
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(user__email__icontains=search)
                | Q(user__first_name__icontains=search)
                | Q(user__last_name__icontains=search)
                | Q(role__name__icontains=search)
            )
        return queryset

    def perform_create(self, serializer):
        entity, error_response = self._entity_from_request(self.request)
        if error_response:
            raise ValidationError(error_response.data)
        assignment = serializer.save(entity=entity, assigned_by=self.request.user)
        RBACAuditService.log(
            actor=self.request.user,
            entity=entity,
            object_type="assignment",
            object_id=assignment.id,
            action=RBACAuditLog.ACTION_ASSIGN,
            message=f"Assigned role {assignment.role.name} to user {assignment.user_id}.",
            changes={"role_id": assignment.role_id, "user_id": assignment.user_id},
        )


class UserRoleAssignmentAdminDetailView(RBACEntityAccessMixin, RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserRoleAssignmentAdminSerializer
    queryset = UserRoleAssignment.objects.select_related("user", "role", "entity", "subentity")

    def perform_update(self, serializer):
        assignment = serializer.save()
        RBACAuditService.log(
            actor=self.request.user,
            entity=assignment.entity,
            object_type="assignment",
            object_id=assignment.id,
            action=RBACAuditLog.ACTION_UPDATE,
            message=f"Updated assignment for user {assignment.user_id}.",
        )

    def destroy(self, request, *args, **kwargs):
        assignment = self.get_object()
        self._soft_delete(assignment, actor=request.user, message=f"Deactivated assignment {assignment.id}.")
        return Response(status=status.HTTP_204_NO_CONTENT)


class EntityUserOptionsView(RBACEntityAccessMixin, APIView):
    def get(self, request):
        entity, error_response = self._entity_from_request(request)
        if error_response:
            return error_response

        user_ids = set(UserRoleAssignment.objects.filter(entity=entity).values_list("user_id", flat=True))
        users = User.objects.filter(id__in=user_ids, is_active=True).order_by("first_name", "email")
        serializer = UserOptionSerializer(users, many=True)
        return Response(serializer.data)


class EffectiveAccessPreviewView(RBACEntityAccessMixin, APIView):
    def get(self, request):
        entity, error_response = self._entity_from_request(request)
        if error_response:
            return error_response

        user_id = request.query_params.get("user_id")
        if not user_id:
            return Response({"detail": "user_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(pk=user_id, is_active=True)
        except User.DoesNotExist:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        permissions = sorted(EffectivePermissionService.permission_codes_for_user(user, entity.id))
        permission_objects = list(Permission.objects.filter(code__in=permissions, isactive=True).order_by("module", "resource", "action", "name"))
        payload = {
            "entity_id": entity.id,
            "entity_name": entity.entityname,
            "user": user,
            "roles": EffectivePermissionService.role_summaries_for_user(user, entity.id),
            "permissions": permissions,
            "permission_groups": grouped_permission_payload(permission_objects),
            "menus": EffectiveMenuService.menu_tree_for_user(user, entity.id),
        }
        serializer = EffectiveAccessPreviewSerializer(payload)
        return Response(serializer.data)


class RoleCloneView(RBACEntityAccessMixin, RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    queryset = Role.objects.filter(role_level=Role.LEVEL_ENTITY).select_related("entity")

    def post(self, request, *args, **kwargs):
        source_role = self.get_object()
        if not EffectivePermissionService.entity_for_user(request.user, source_role.entity_id):
            return Response({"detail": "You do not have access to this entity."}, status=status.HTTP_403_FORBIDDEN)

        serializer = RoleCloneSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        clone = RoleCloneService.clone_role(
            source_role,
            name=serializer.validated_data["name"],
            code=serializer.validated_data["code"],
            description=serializer.validated_data.get("description"),
            actor=request.user,
        )
        output = RoleAdminSerializer(
            Role.objects.filter(pk=clone.pk)
            .select_related("entity")
            .annotate(
                permission_count=Count("role_permissions", filter=Q(role_permissions__isactive=True), distinct=True),
                assignment_count=Count("user_assignments", filter=Q(user_assignments__isactive=True), distinct=True),
            )
            .first()
        )
        return Response(output.data, status=status.HTTP_201_CREATED)


class RoleTemplatesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"templates": RoleTemplateService.template_catalog()})


class RoleTemplateApplyView(RBACEntityAccessMixin, RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    queryset = Role.objects.filter(role_level=Role.LEVEL_ENTITY).select_related("entity")

    def post(self, request, *args, **kwargs):
        role = self.get_object()
        if not EffectivePermissionService.entity_for_user(request.user, role.entity_id):
            return Response({"detail": "You do not have access to this entity."}, status=status.HTTP_403_FORBIDDEN)
        self._assert_not_system_role(role, "change")

        serializer = RoleTemplateApplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        selected_ids = RoleTemplateService.apply_template(
            role,
            serializer.validated_data["template_code"],
            serializer.validated_data.get("permission_ids", []),
            actor=request.user,
        )
        return Response({"role_id": role.id, "template_code": serializer.validated_data["template_code"], "permission_ids": sorted(selected_ids)})


class BulkAssignmentView(RBACEntityAccessMixin, APIView):
    def post(self, request):
        entity, error_response = self._entity_from_request(request)
        if error_response:
            return error_response

        serializer = BulkAssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        role_id = serializer.validated_data["role"]
        try:
            role = Role.objects.get(pk=role_id, entity=entity, isactive=True)
        except Role.DoesNotExist:
            return Response({"detail": "Role not found for this entity."}, status=status.HTTP_404_NOT_FOUND)

        created_ids = []
        reactivated_ids = []
        for user_id in serializer.validated_data["user_ids"]:
            assignment, created = UserRoleAssignment.objects.get_or_create(
                user_id=user_id,
                entity=entity,
                role=role,
                subentity_id=serializer.validated_data.get("subentity"),
                defaults={
                    "assigned_by": request.user,
                    "is_primary": serializer.validated_data["is_primary"],
                    "scope_data": serializer.validated_data.get("scope_data", {}),
                    "isactive": serializer.validated_data["isactive"],
                },
            )
            if created:
                created_ids.append(assignment.id)
            else:
                assignment.is_primary = serializer.validated_data["is_primary"]
                assignment.scope_data = serializer.validated_data.get("scope_data", {})
                assignment.isactive = serializer.validated_data["isactive"]
                assignment.assigned_by = request.user
                assignment.save()
                reactivated_ids.append(assignment.id)

        RBACAuditService.log(
            actor=request.user,
            entity=entity,
            object_type="assignment_bulk",
            object_id=role.id,
            action=RBACAuditLog.ACTION_ASSIGN,
            message=f"Bulk assigned role {role.name}.",
            changes={"created_assignment_ids": created_ids, "updated_assignment_ids": reactivated_ids, "user_ids": serializer.validated_data["user_ids"]},
        )
        return Response(
            {
                "entity_id": entity.id,
                "role_id": role.id,
                "created_assignment_ids": created_ids,
                "updated_assignment_ids": reactivated_ids,
            },
            status=status.HTTP_200_OK,
        )


class AuditLogListView(RBACEntityAccessMixin, ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = RBACAuditLogSerializer

    def get_queryset(self):
        entity, error_response = self._entity_from_request(self.request)
        if error_response:
            return RBACAuditLog.objects.none()
        queryset = RBACAuditLog.objects.filter(entity=entity).select_related("actor", "entity")
        object_type = self.request.query_params.get("object_type")
        if object_type:
            queryset = queryset.filter(object_type=object_type)
        action = self.request.query_params.get("action")
        if action:
            queryset = queryset.filter(action=action)
        return queryset.order_by("-created_at")


