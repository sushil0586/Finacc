from django.conf import settings
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from entity.context_serializers import EntityContextSerializer
from entity.models import Entity, UserRole
from rbac.models import UserRoleAssignment
from rbac.services import EffectivePermissionService


class UserEntitiesV2View(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user

        if getattr(settings, "RBAC_DEV_ALLOW_ALL_ACCESS", False):
            entities = Entity.objects.filter(isactive=True).order_by("entityname", "id")
            serializer = EntityContextSerializer(
                [
                    {
                        "entityid": entity.id,
                        "entityname": entity.entityname,
                        "gstno": entity.gstno,
                        "email": user.email,
                        "role": "Development Full Access",
                        "roleid": 0,
                        "roles": EffectivePermissionService.role_summaries_for_user(user, entity.id),
                    }
                    for entity in entities
                ],
                many=True,
            )
            return Response(serializer.data)

        entity_map = {}

        legacy_user_roles = (
            UserRole.objects.filter(user=user)
            .select_related("entity", "role")
            .order_by("entity__entityname", "id")
        )
        for user_role in legacy_user_roles:
            if not user_role.entity_id:
                continue
            roles = EffectivePermissionService.role_summaries_for_user(user, user_role.entity_id)
            primary_role = next((role for role in roles if role.get("is_primary")), roles[0] if roles else None)
            entity_map[user_role.entity_id] = {
                "entityid": user_role.entity_id,
                "entityname": user_role.entity.entityname,
                "gstno": user_role.entity.gstno,
                "email": user.email,
                "role": primary_role["name"] if primary_role else user_role.role.rolename,
                "roleid": primary_role["id"] if primary_role else user_role.role_id,
                "roles": roles or [
                    {
                        "id": user_role.role_id,
                        "name": user_role.role.rolename,
                        "code": "",
                        "source": "legacy",
                        "is_primary": True,
                    }
                ],
            }

        rbac_assignments = (
            UserRoleAssignment.objects.filter(user=user, isactive=True)
            .select_related("entity", "role")
            .order_by("entity__entityname", "id")
        )
        for assignment in rbac_assignments:
            if assignment.entity_id in entity_map:
                continue
            roles = EffectivePermissionService.role_summaries_for_user(user, assignment.entity_id)
            primary_role = next((role for role in roles if role.get("is_primary")), roles[0] if roles else None)
            entity_map[assignment.entity_id] = {
                "entityid": assignment.entity_id,
                "entityname": assignment.entity.entityname,
                "gstno": assignment.entity.gstno,
                "email": user.email,
                "role": primary_role["name"] if primary_role else assignment.role.name,
                "roleid": primary_role["id"] if primary_role else assignment.role_id,
                "roles": roles,
            }

        serializer = EntityContextSerializer(list(entity_map.values()), many=True)
        return Response(serializer.data)
