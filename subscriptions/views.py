from __future__ import annotations

from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from entity.models import Entity
from rbac.services import EffectivePermissionService

from .models import UserEntityAccess
from .serializers import (
    TenantMembershipCreateSerializer,
    TenantMembershipListResponseSerializer,
    TenantMembershipSerializer,
    TenantMembershipUpdateSerializer,
    tenant_membership_queryset_for_entity,
)
from .services import SubscriptionService


User = get_user_model()


class TenantMembershipAccessMixin:
    permission_classes = [permissions.IsAuthenticated]

    def _entity_from_request(self, request):
        entity_id = request.query_params.get("entity") or request.data.get("entity")
        if entity_id in (None, "", "null"):
            return None, Response({"detail": "entity is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            entity_id = int(entity_id)
        except (TypeError, ValueError):
            return None, Response({"detail": "entity must be an integer."}, status=status.HTTP_400_BAD_REQUEST)

        entity = EffectivePermissionService.entity_for_user(request.user, entity_id)
        if entity is None:
            return None, Response({"detail": "Entity not found or inaccessible."}, status=status.HTTP_404_NOT_FOUND)

        permission_codes = EffectivePermissionService.permission_codes_for_user(request.user, entity.id)
        if not any(code in permission_codes for code in ("admin.user.view", "admin.user.create", "admin.user.update")):
            return None, Response({"detail": "Missing user-management permission."}, status=status.HTTP_403_FORBIDDEN)

        customer_account = SubscriptionService._customer_account_for_entity(entity)
        if not SubscriptionService.can_manage_tenant(user=request.user, customer_account=customer_account):
            return None, Response({"detail": "Your tenant membership does not allow membership management."}, status=status.HTTP_403_FORBIDDEN)

        return entity, None

    def _role_choices(self):
        return [
            {"value": role_value, "label": role_label}
            for role_value, role_label in UserEntityAccess.Role.choices
            if role_value != UserEntityAccess.Role.OWNER
        ]


class TenantMembershipListCreateView(TenantMembershipAccessMixin, APIView):
    def get(self, request):
        entity, error_response = self._entity_from_request(request)
        if error_response:
            return error_response

        queryset = tenant_membership_queryset_for_entity(entity)
        serializer = TenantMembershipSerializer(queryset, many=True)
        payload = {
            "entity_id": entity.id,
            "entity_name": entity.entityname,
            "customer_account_id": entity.customer_account_id,
            "customer_account_name": entity.customer_account.name if entity.customer_account_id else "",
            "capabilities": {
                "can_view_members": True,
                "can_manage_members": True,
            },
            "role_choices": self._role_choices(),
            "members": serializer.data,
        }
        return Response(payload)

    def post(self, request):
        entity, error_response = self._entity_from_request(request)
        if error_response:
            return error_response

        serializer = TenantMembershipCreateSerializer(
            data=request.data,
            context={
                "customer_account": entity.customer_account,
                "actor": request.user,
            },
        )
        serializer.is_valid(raise_exception=True)
        membership = serializer.save()

        queryset = tenant_membership_queryset_for_entity(entity)
        membership = queryset.get(pk=membership.pk)
        return Response(TenantMembershipSerializer(membership).data, status=status.HTTP_201_CREATED)


class TenantMembershipDetailView(TenantMembershipAccessMixin, APIView):
    def get_object(self, *, entity, membership_id):
        return get_object_or_404(
            tenant_membership_queryset_for_entity(entity),
            pk=membership_id,
        )

    def get(self, request, membership_id: int):
        entity, error_response = self._entity_from_request(request)
        if error_response:
            return error_response
        membership = self.get_object(entity=entity, membership_id=membership_id)
        return Response(TenantMembershipSerializer(membership).data)

    def patch(self, request, membership_id: int):
        entity, error_response = self._entity_from_request(request)
        if error_response:
            return error_response
        membership = self.get_object(entity=entity, membership_id=membership_id)
        serializer = TenantMembershipUpdateSerializer(
            data=request.data,
            context={"membership": membership, "actor": request.user},
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        updated_membership = serializer.save()
        updated_membership = tenant_membership_queryset_for_entity(entity).get(pk=updated_membership.pk)
        return Response(TenantMembershipSerializer(updated_membership).data)

    def delete(self, request, membership_id: int):
        entity, error_response = self._entity_from_request(request)
        if error_response:
            return error_response
        membership = self.get_object(entity=entity, membership_id=membership_id)
        SubscriptionService.deactivate_account_membership(
            membership=membership,
            deactivated_by=request.user,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
