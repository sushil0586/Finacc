from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
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
    CreateUserWithAssignmentResponseSerializer,
    CreateUserWithAssignmentSerializer,
    RBACAuditLogSerializer,
    RBACAdminBootstrapSerializer,
    RecursiveMenuSerializer,
    RoleCloneSerializer,
    RoleAdminSerializer,
    RolePermissionsStateSerializer,
    RoleTemplateApplySerializer,
    RoleSerializer,
    UserOptionSerializer,
    UserSearchResultSerializer,
    UserRoleAssignmentAdminSerializer,
    MenuPermissionBulkSerializer,
    RolePermissionBulkSerializer,
)
from .services import (
    AssignmentSemanticsService,
    EffectiveMenuService,
    EffectivePermissionService,
    MenuTreeService,
    RBACAuditService,
    RoleCloneService,
    RoleTemplateService,
)
from subscriptions.services import SubscriptionService


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

    def _has_any_permission(self, request, entity, permission_codes):
        current_codes = EffectivePermissionService.permission_codes_for_user(request.user, entity.id)
        return any(code in current_codes for code in permission_codes)

    def _require_any_permission(self, request, entity, permission_codes):
        if self._has_any_permission(request, entity, permission_codes):
            return None
        return Response(
            {"detail": "You do not have permission to perform this action for this entity."},
            status=status.HTTP_403_FORBIDDEN,
        )

    def _require_platform_admin(self, request):
        if request.user and request.user.is_superuser:
            return None
        return Response(
            {"detail": "Only platform administrators can manage the global RBAC catalog."},
            status=status.HTTP_403_FORBIDDEN,
        )

    def _admin_capabilities(self, request, entity):
        current_codes = set(EffectivePermissionService.permission_codes_for_user(request.user, entity.id))

        def has_any(*codes):
            return any(code in current_codes for code in codes)

        return {
            "can_view_roles": has_any("admin.role.view"),
            "can_manage_roles": has_any("admin.role.create", "admin.role.update", "admin.role.delete"),
            "can_view_menus": has_any("admin.role.view"),
            "can_manage_menus": has_any("admin.role.create", "admin.role.update", "admin.role.delete"),
            "can_view_role_access": has_any("admin.role.view"),
            "can_manage_role_access": has_any("admin.role.update"),
            "can_view_user_access": has_any("admin.user.view"),
            "can_manage_user_access": has_any("admin.user.create", "admin.user.update", "admin.user.delete"),
            "can_preview_access": has_any("admin.user.view", "admin.role.view"),
            "can_view_audit": has_any("admin.role.view"),
        }

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
        permission_error = self._require_any_permission(request, entity, ("admin.user.view", "admin.role.view"))
        if permission_error:
            return permission_error

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

        customer_account = SubscriptionService._customer_account_for_entity(entity)
        member_user_ids = set(
            SubscriptionService.active_memberships_queryset(customer_account=customer_account).values_list("user_id", flat=True)
        )
        assigned_user_ids = set(UserRoleAssignment.objects.filter(entity=entity).values_list("user_id", flat=True))
        users = list(
            User.objects.filter(id__in=(member_user_ids | assigned_user_ids), is_active=True).order_by("first_name", "email")
        )

        payload = {
            "entity_id": entity.id,
            "entity_name": entity.entityname,
            "roles": roles,
            "permissions": permissions,
            "menus": menus,
            "assignments": assignments,
            "users": users,
            "permission_groups": grouped_permission_payload(permissions),
            "capabilities": self._admin_capabilities(request, entity),
        }
        serializer = RBACAdminBootstrapSerializer(payload)
        return Response(serializer.data)


class PermissionAdminListCreateView(RBACEntityAccessMixin, ListCreateAPIView):
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

    def list(self, request, *args, **kwargs):
        permission_error = self._require_platform_admin(request)
        if permission_error:
            return permission_error
        return super().list(request, *args, **kwargs)

    def perform_create(self, serializer):
        permission_error = self._require_platform_admin(self.request)
        if permission_error:
            raise PermissionDenied(permission_error.data["detail"])
        permission = serializer.save()
        RBACAuditService.log(
            actor=self.request.user,
            object_type="permission",
            object_id=permission.id,
            action=RBACAuditLog.ACTION_CREATE,
            message=f"Created permission {permission.code}.",
            changes={"code": permission.code},
        )


class PermissionAdminDetailView(RBACEntityAccessMixin, RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PermissionAdminSerializer
    queryset = Permission.objects.all()

    def retrieve(self, request, *args, **kwargs):
        permission_error = self._require_platform_admin(request)
        if permission_error:
            return permission_error
        return super().retrieve(request, *args, **kwargs)

    def perform_update(self, serializer):
        permission_error = self._require_platform_admin(self.request)
        if permission_error:
            raise PermissionDenied(permission_error.data["detail"])
        permission = serializer.save()
        RBACAuditService.log(
            actor=self.request.user,
            object_type="permission",
            object_id=permission.id,
            action=RBACAuditLog.ACTION_UPDATE,
            message=f"Updated permission {permission.code}.",
        )

    def destroy(self, request, *args, **kwargs):
        permission_error = self._require_platform_admin(request)
        if permission_error:
            return permission_error
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

    def list(self, request, *args, **kwargs):
        entity, error_response = self._entity_from_request(request)
        if error_response:
            return error_response
        permission_error = self._require_any_permission(request, entity, ("admin.role.view",))
        if permission_error:
            return permission_error
        return super().list(request, *args, **kwargs)

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
        permission_error = self._require_any_permission(self.request, entity, ("admin.role.create",))
        if permission_error:
            raise PermissionDenied(permission_error.data["detail"])
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
        entity_id = self.request.query_params.get("entity")
        queryset = (
            Role.objects.filter(role_level=Role.LEVEL_ENTITY)
            .select_related("entity")
            .annotate(
                permission_count=Count("role_permissions", filter=Q(role_permissions__isactive=True), distinct=True),
                assignment_count=Count("user_assignments", filter=Q(user_assignments__isactive=True), distinct=True),
            )
        )
        if not entity_id:
            return queryset

        entity, error_response = self._entity_from_request(self.request)
        if error_response:
            return Role.objects.none()
        return queryset.filter(entity=entity)

    def get_object(self):
        role = super().get_object()
        if not EffectivePermissionService.entity_for_user(self.request.user, role.entity_id):
            raise PermissionDenied("You do not have access to this entity.")
        return role

    def retrieve(self, request, *args, **kwargs):
        role = self.get_object()
        permission_error = self._require_any_permission(request, role.entity, ("admin.role.view",))
        if permission_error:
            return permission_error
        serializer = self.get_serializer(role)
        return Response(serializer.data)

    def perform_update(self, serializer):
        role = self.get_object()
        permission_error = self._require_any_permission(self.request, role.entity, ("admin.role.update",))
        if permission_error:
            raise PermissionDenied(permission_error.data["detail"])
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
        permission_error = self._require_any_permission(request, role.entity, ("admin.role.delete",))
        if permission_error:
            return permission_error
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
        permission_error = self._require_any_permission(request, role.entity, ("admin.role.view",))
        if permission_error:
            return permission_error

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
        permission_error = self._require_any_permission(request, role.entity, ("admin.role.update",))
        if permission_error:
            return permission_error
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

    def list(self, request, *args, **kwargs):
        entity, error_response = self._entity_from_request(request)
        if error_response:
            return error_response
        permission_error = self._require_any_permission(request, entity, ("admin.role.view",))
        if permission_error:
            return permission_error
        return super().list(request, *args, **kwargs)

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
        permission_error = self._require_any_permission(self.request, entity, ("admin.role.update",))
        if permission_error:
            raise PermissionDenied(permission_error.data["detail"])
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

    def retrieve(self, request, *args, **kwargs):
        entity, error_response = self._entity_from_request(request)
        if error_response:
            return error_response
        permission_error = self._require_any_permission(request, entity, ("admin.role.view",))
        if permission_error:
            return permission_error
        return super().retrieve(request, *args, **kwargs)

    def perform_update(self, serializer):
        original = self.get_object()
        entity, error_response = self._entity_from_request(self.request)
        if error_response:
            raise ValidationError(error_response.data)
        permission_error = self._require_any_permission(self.request, entity, ("admin.role.update",))
        if permission_error:
            raise PermissionDenied(permission_error.data["detail"])
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
        entity, error_response = self._entity_from_request(request)
        if error_response:
            return error_response
        permission_error = self._require_any_permission(request, entity, ("admin.role.delete",))
        if permission_error:
            return permission_error
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
        permission_error = self._require_any_permission(request, entity, ("admin.role.view",))
        if permission_error:
            return permission_error
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
        permission_error = self._require_any_permission(request, entity, ("admin.role.update",))
        if permission_error:
            return permission_error
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

    def list(self, request, *args, **kwargs):
        entity, error_response = self._entity_from_request(request)
        if error_response:
            return error_response
        permission_error = self._require_any_permission(request, entity, ("admin.role.view",))
        if permission_error:
            return permission_error
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        entity, error_response = self._entity_from_request(self.request)
        if error_response:
            return Menu.objects.none()
        return Menu.objects.filter(parent__isnull=True, isactive=True).order_by("sort_order", "name")


class UserRoleAssignmentAdminListCreateView(RBACEntityAccessMixin, ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserRoleAssignmentAdminSerializer

    def list(self, request, *args, **kwargs):
        entity, error_response = self._entity_from_request(request)
        if error_response:
            return error_response
        permission_error = self._require_any_permission(request, entity, ("admin.user.view",))
        if permission_error:
            return permission_error
        return super().list(request, *args, **kwargs)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        entity, _ = self._entity_from_request(self.request)
        context["entity"] = entity
        context["actor"] = self.request.user
        return context

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
        permission_error = self._require_any_permission(self.request, entity, ("admin.user.create", "admin.user.update"))
        if permission_error:
            raise ValidationError(permission_error.data)
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

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["entity"] = getattr(self.get_object(), "entity", None)
        context["actor"] = self.request.user
        return context

    def get_object(self):
        assignment = super().get_object()
        if not self._has_any_permission(self.request, assignment.entity, ("admin.user.view", "admin.user.update", "admin.user.delete")):
            raise PermissionDenied("You do not have permission to perform this action for this entity.")
        return assignment

    def retrieve(self, request, *args, **kwargs):
        assignment = self.get_object()
        permission_error = self._require_any_permission(request, assignment.entity, ("admin.user.view",))
        if permission_error:
            return permission_error
        serializer = self.get_serializer(assignment)
        return Response(serializer.data)

    def perform_update(self, serializer):
        assignment = self.get_object()
        permission_error = self._require_any_permission(self.request, assignment.entity, ("admin.user.update",))
        if permission_error:
            raise PermissionDenied(permission_error.data["detail"])
        assignment = serializer.save()
        SubscriptionService.register_user_invite(
            entity=assignment.entity,
            user=assignment.user,
            invited_by=self.request.user,
        )
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
        permission_error = self._require_any_permission(request, assignment.entity, ("admin.user.delete",))
        if permission_error:
            return permission_error
        affected_user = assignment.user
        affected_entity = assignment.entity
        self._soft_delete(assignment, actor=request.user, message=f"Deactivated assignment {assignment.id}.")
        AssignmentSemanticsService.normalize_primary_assignments(user=affected_user, entity=affected_entity)
        return Response(status=status.HTTP_204_NO_CONTENT)


class EntityUserOptionsView(RBACEntityAccessMixin, APIView):
    def get(self, request):
        entity, error_response = self._entity_from_request(request)
        if error_response:
            return error_response
        permission_error = self._require_any_permission(request, entity, ("admin.user.view", "admin.user.create"))
        if permission_error:
            return permission_error

        customer_account = SubscriptionService._customer_account_for_entity(entity)
        member_user_ids = SubscriptionService.active_memberships_queryset(
            customer_account=customer_account
        ).values_list("user_id", flat=True)
        search = (request.query_params.get("q") or "").strip()
        if search:
            users = (
                User.objects.filter(is_active=True, id__in=member_user_ids)
                .filter(
                    Q(email__icontains=search)
                    | Q(username__icontains=search)
                    | Q(first_name__icontains=search)
                    | Q(last_name__icontains=search)
                )
                .annotate(
                    entity_assignment_count=Count(
                        "rbac_role_assignments",
                        filter=Q(rbac_role_assignments__entity=entity, rbac_role_assignments__isactive=True),
                        distinct=True,
                    )
                )
                .order_by("first_name", "email")[:25]
            )
            serializer = UserSearchResultSerializer(users, many=True)
            return Response(serializer.data)

        assigned_user_ids = set(UserRoleAssignment.objects.filter(entity=entity).values_list("user_id", flat=True))
        users = User.objects.filter(
            id__in=(set(member_user_ids) | assigned_user_ids),
            is_active=True,
        ).order_by("first_name", "email")
        serializer = UserOptionSerializer(users, many=True)
        return Response(serializer.data)


class EffectiveAccessPreviewView(RBACEntityAccessMixin, APIView):
    def get(self, request):
        entity, error_response = self._entity_from_request(request)
        if error_response:
            return error_response
        permission_error = self._require_any_permission(request, entity, ("admin.user.view", "admin.role.view"))
        if permission_error:
            return permission_error

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
        permission_error = self._require_any_permission(request, source_role.entity, ("admin.role.create",))
        if permission_error:
            return permission_error

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


class RoleTemplatesView(RBACEntityAccessMixin, APIView):
    def get(self, request):
        entity, error_response = self._entity_from_request(request)
        if error_response:
            return error_response
        permission_error = self._require_any_permission(request, entity, ("admin.role.view",))
        if permission_error:
            return permission_error
        return Response({"templates": RoleTemplateService.template_catalog()})


class RoleTemplateApplyView(RBACEntityAccessMixin, RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    queryset = Role.objects.filter(role_level=Role.LEVEL_ENTITY).select_related("entity")

    def post(self, request, *args, **kwargs):
        role = self.get_object()
        permission_error = self._require_any_permission(request, role.entity, ("admin.role.update",))
        if permission_error:
            return permission_error
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
        permission_error = self._require_any_permission(request, entity, ("admin.user.create", "admin.user.update"))
        if permission_error:
            return permission_error

        serializer = BulkAssignmentSerializer(data=request.data, context={"entity": entity})
        serializer.is_valid(raise_exception=True)
        role_id = serializer.validated_data["role"]
        try:
            role = Role.objects.get(pk=role_id, entity=entity, isactive=True)
        except Role.DoesNotExist:
            return Response({"detail": "Role not found for this entity."}, status=status.HTTP_404_NOT_FOUND)

        created_ids = []
        reactivated_ids = []
        for user_id in serializer.validated_data["user_ids"]:
            user = User.objects.filter(pk=user_id, is_active=True).first()
            if user is None:
                continue
            assignment, created = UserRoleAssignment.objects.get_or_create(
                user=user,
                entity=entity,
                role=role,
                subentity_id=serializer.validated_data.get("subentity"),
                defaults={
                    "assigned_by": request.user,
                    "effective_from": serializer.validated_data.get("effective_from"),
                    "effective_to": serializer.validated_data.get("effective_to"),
                    "is_primary": serializer.validated_data["is_primary"],
                    "scope_data": serializer.validated_data.get("scope_data", {}),
                    "isactive": serializer.validated_data["isactive"],
                },
            )
            if created:
                created_ids.append(assignment.id)
            else:
                assignment.is_primary = serializer.validated_data["is_primary"]
                assignment.effective_from = serializer.validated_data.get("effective_from")
                assignment.effective_to = serializer.validated_data.get("effective_to")
                assignment.scope_data = serializer.validated_data.get("scope_data", {})
                assignment.isactive = serializer.validated_data["isactive"]
                assignment.assigned_by = request.user
                assignment.save()
                reactivated_ids.append(assignment.id)
            AssignmentSemanticsService.finalize_assignment(assignment)

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


class CreateUserWithAssignmentView(RBACEntityAccessMixin, APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        entity, error_response = self._entity_from_request(request)
        if error_response:
            return error_response
        permission_error = self._require_any_permission(request, entity, ("admin.user.create",))
        if permission_error:
            return permission_error

        serializer = CreateUserWithAssignmentSerializer(
            data=request.data,
            context={"entity": entity, "actor": request.user},
        )
        serializer.is_valid(raise_exception=True)
        result = serializer.save()

        RBACAuditService.log(
            actor=request.user,
            entity=entity,
            object_type="assignment",
            object_id=result["assignment"].id,
            action=RBACAuditLog.ACTION_ASSIGN,
            message=f"Created user {result['user'].email} and assigned role {result['assignment'].role.name}.",
            changes={"role_id": result["assignment"].role_id, "user_id": result["user"].id},
        )

        output = CreateUserWithAssignmentResponseSerializer(result)
        return Response(output.data, status=status.HTTP_201_CREATED)


class AuditLogListView(RBACEntityAccessMixin, ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = RBACAuditLogSerializer

    def list(self, request, *args, **kwargs):
        entity, error_response = self._entity_from_request(request)
        if error_response:
            return error_response
        permission_error = self._require_any_permission(request, entity, ("admin.role.view",))
        if permission_error:
            return permission_error
        return super().list(request, *args, **kwargs)

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


