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
    SubscriptionAccountActionSerializer,
    SubscriptionPlanAdminSerializer,
    SubscriptionPublicPlanSerializer,
    SubscriptionSnapshotSerializer,
    TenantMembershipCreateSerializer,
    TenantMembershipListResponseSerializer,
    TenantMembershipSerializer,
    TenantMembershipUpdateSerializer,
    tenant_membership_queryset_for_entity,
)
from .services import SubscriptionService


User = get_user_model()


class SubscriptionAccountAdminMixin:
    permission_classes = [permissions.IsAdminUser]

    def get_account(self, account_id: int):
        return get_object_or_404(SubscriptionService.account_queryset(), pk=account_id)


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


class PublicSubscriptionPlanListView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        plans = SubscriptionService.get_public_plan_catalog()
        serializer = SubscriptionPublicPlanSerializer(plans, many=True)
        return Response({"plans": serializer.data})


class CurrentSubscriptionSnapshotView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        snapshot = SubscriptionService.build_subscription_snapshot(user=request.user)
        serializer = SubscriptionSnapshotSerializer(snapshot)
        return Response(serializer.data)


class SubscriptionAccountAdminDetailView(SubscriptionAccountAdminMixin, APIView):
    def get(self, request, account_id: int):
        account = self.get_account(account_id)
        snapshot = SubscriptionService.build_subscription_snapshot(customer_account=account)
        serializer = SubscriptionSnapshotSerializer(snapshot)
        return Response(serializer.data)


class SubscriptionAccountPlanChangeView(SubscriptionAccountAdminMixin, APIView):
    def post(self, request, account_id: int):
        account = self.get_account(account_id)
        serializer = SubscriptionAccountActionSerializer(
            data=request.data,
            context={"action": "change_plan"},
        )
        serializer.is_valid(raise_exception=True)
        plan = get_object_or_404(SubscriptionService.plan_queryset(), pk=serializer.validated_data["plan_id"])
        updated_subscription = SubscriptionService.change_plan(
            customer_account=account,
            new_plan=plan,
            changed_by=request.user,
        )
        if "status_reason" in serializer.validated_data or "status_notes" in serializer.validated_data:
            account.status_reason = serializer.validated_data.get("status_reason")
            account.status_notes = serializer.validated_data.get("status_notes")
            account.save(update_fields=["status_reason", "status_notes", "updated_at"])
        snapshot = SubscriptionService.build_subscription_snapshot(customer_account=account)
        response_serializer = SubscriptionSnapshotSerializer(snapshot)
        return Response(
            {
                "detail": "Subscription plan changed successfully.",
                "subscription_id": updated_subscription.id,
                "snapshot": response_serializer.data,
            }
        )


class SubscriptionAccountCancelView(SubscriptionAccountAdminMixin, APIView):
    def post(self, request, account_id: int):
        account = self.get_account(account_id)
        serializer = SubscriptionAccountActionSerializer(
            data=request.data,
            context={"action": "cancel"},
        )
        serializer.is_valid(raise_exception=True)
        canceled = SubscriptionService.cancel_subscription(
            customer_account=account,
            canceled_by=request.user,
        )
        if "status_reason" in serializer.validated_data or "status_notes" in serializer.validated_data:
            account.status_reason = serializer.validated_data.get("status_reason")
            account.status_notes = serializer.validated_data.get("status_notes")
            account.save(update_fields=["status_reason", "status_notes", "updated_at"])
        snapshot = SubscriptionService.build_subscription_snapshot(customer_account=account)
        response_serializer = SubscriptionSnapshotSerializer(snapshot)
        return Response(
            {
                "detail": "Subscription canceled successfully." if canceled else "No active subscription found.",
                "subscription_id": getattr(canceled, "id", None),
                "snapshot": response_serializer.data,
            }
        )


class SubscriptionPlanAdminListCreateView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        plans = SubscriptionService.get_internal_plan_catalog()
        serializer = SubscriptionPlanAdminSerializer(plans, many=True)
        return Response({"plans": serializer.data})

    def post(self, request):
        serializer = SubscriptionPlanAdminSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        plan = serializer.save()
        response_serializer = SubscriptionPlanAdminSerializer(
            SubscriptionService.serialize_internal_plan(plan=plan)
        )
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class SubscriptionPlanAdminDetailView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get_object(self, plan_id: int):
        return get_object_or_404(SubscriptionService.plan_queryset(), pk=plan_id)

    def get(self, request, plan_id: int):
        plan = self.get_object(plan_id)
        serializer = SubscriptionPlanAdminSerializer(
            SubscriptionService.serialize_internal_plan(plan=plan)
        )
        return Response(serializer.data)

    def patch(self, request, plan_id: int):
        plan = self.get_object(plan_id)
        serializer = SubscriptionPlanAdminSerializer(plan, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated_plan = serializer.save()
        response_serializer = SubscriptionPlanAdminSerializer(
            SubscriptionService.serialize_internal_plan(plan=updated_plan)
        )
        return Response(response_serializer.data)

    def delete(self, request, plan_id: int):
        plan = self.get_object(plan_id)
        if plan.is_default:
            return Response(
                {"detail": "Default plan cannot be deactivated.", "code": "default_plan_protected"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        plan.is_active = False
        plan.save(update_fields=["is_active", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


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
