from rest_framework.generics import ListAPIView
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Menu, Permission, Role
from .serializers import (
    EffectiveMenuTreeSerializer,
    EffectivePermissionsSerializer,
    PermissionSerializer,
    RecursiveMenuSerializer,
    RoleSerializer,
)
from .services import EffectiveMenuService, EffectivePermissionService, MenuTreeService


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
