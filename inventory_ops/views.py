from __future__ import annotations

from django.db import IntegrityError
from django.db.models import Q
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.entitlements import ScopedEntitlementMixin
from entity.models import Godown
from posting.models import TxnType
from rbac.services import EffectivePermissionService

from .serializers import (
    InventoryAdjustmentCreateSerializer,
    InventoryAdjustmentListSerializer,
    InventoryAdjustmentResponseSerializer,
    InventoryTransferListSerializer,
    GodownMasterSerializer,
    GodownWriteSerializer,
    GodownLookupSerializer,
    InventoryTransferCreateSerializer,
    InventoryTransferResponseSerializer,
)
from .services import InventoryAdjustmentService, InventoryTransferService


class _BaseInventoryOpsAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_permission_codes(self, request, entity_id):
        return EffectivePermissionService.permission_codes_for_user(request.user, entity_id)

    def assert_permission(self, request, entity_id: int, permission_code: str):
        if permission_code not in self.get_permission_codes(request, entity_id):
            raise PermissionDenied(f"Missing permission: {permission_code}")


class InventoryGodownListAPIView(_BaseInventoryOpsAPIView):
    def get(self, request):
        entity_id = int(request.query_params.get("entity") or 0)
        if not entity_id:
            return Response({"detail": "entity is required."}, status=status.HTTP_400_BAD_REQUEST)
        subentity_id = int(request.query_params.get("subentity") or 0) or None
        self.enforce_scope(request, entity_id=entity_id)
        self.assert_permission(request, entity_id, "inventory.transfer.view")
        qs = Godown.objects.filter(entity_id=entity_id, is_active=True)
        if subentity_id:
            qs = qs.filter(Q(subentity_id=subentity_id) | Q(subentity__isnull=True))
        serializer = GodownLookupSerializer(qs.select_related("entity", "subentity").order_by("subentity_id", "-is_default", "name"), many=True)
        return Response({"rows": serializer.data})


class InventoryGodownMasterAPIView(_BaseInventoryOpsAPIView):
    def get(self, request):
        entity_id = int(request.query_params.get("entity") or 0)
        if not entity_id:
            return Response({"detail": "entity is required."}, status=status.HTTP_400_BAD_REQUEST)
        subentity_id = int(request.query_params.get("subentity") or 0) or None
        include_inactive = str(request.query_params.get("include_inactive") or "").lower() in {"1", "true", "yes", "on"}
        self.enforce_scope(request, entity_id=entity_id)
        self.assert_permission(request, entity_id, "inventory.location.view")
        qs = Godown.objects.filter(entity_id=entity_id)
        if not include_inactive:
            qs = qs.filter(is_active=True)
        if subentity_id:
            qs = qs.filter(Q(subentity_id=subentity_id) | Q(subentity__isnull=True))
        serializer = GodownMasterSerializer(qs.select_related("entity", "subentity").order_by("subentity_id", "-is_default", "name"), many=True)
        return Response({"rows": serializer.data})

    def post(self, request):
        serializer = GodownWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        self.enforce_scope(
            request,
            entity_id=payload["entity"],
            subentity_id=payload.get("subentity"),
        )
        self.assert_permission(request, payload["entity"], "inventory.location.create")
        try:
            godown = Godown.objects.create(
                entity_id=payload["entity"],
                subentity_id=payload.get("subentity"),
                name=payload["name"],
                code=payload["code"],
                address=payload.get("address") or "",
                city=payload.get("city") or "",
                state=payload.get("state") or "",
                pincode=payload.get("pincode") or "",
                capacity=payload.get("capacity"),
                is_active=payload.get("is_active", True),
                is_default=payload.get("is_default", False),
            )
        except IntegrityError as exc:
            raise ValidationError({"detail": "Stock location code or name already exists for this entity."}) from exc
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict if hasattr(exc, "message_dict") else {"detail": exc.messages}) from exc
        return Response(GodownMasterSerializer(godown).data, status=status.HTTP_201_CREATED)


class InventoryGodownMasterDetailAPIView(_BaseInventoryOpsAPIView):
    def get_object(self, pk: int) -> Godown:
        return get_object_or_404(Godown.objects.select_related("entity", "subentity"), pk=pk)

    def get(self, request, pk: int):
        godown = self.get_object(pk)
        self.enforce_scope(request, entity_id=godown.entity_id, subentity_id=godown.subentity_id)
        self.assert_permission(request, godown.entity_id, "inventory.location.view")
        return Response(GodownMasterSerializer(godown).data)

    def patch(self, request, pk: int):
        godown = self.get_object(pk)
        self.enforce_scope(request, entity_id=godown.entity_id, subentity_id=godown.subentity_id)
        self.assert_permission(request, godown.entity_id, "inventory.location.update")
        serializer = GodownWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        if int(payload["entity"]) != int(godown.entity_id):
            raise PermissionDenied("Godown entity cannot be changed.")
        godown.entity_id = payload["entity"]
        godown.subentity_id = payload.get("subentity")
        godown.name = payload["name"]
        godown.code = payload["code"]
        godown.address = payload.get("address") or ""
        godown.city = payload.get("city") or ""
        godown.state = payload.get("state") or ""
        godown.pincode = payload.get("pincode") or ""
        godown.capacity = payload.get("capacity")
        godown.is_active = payload.get("is_active", True)
        godown.is_default = payload.get("is_default", False)
        try:
            godown.save()
        except IntegrityError as exc:
            raise ValidationError({"detail": "Stock location code or name already exists for this entity."}) from exc
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict if hasattr(exc, "message_dict") else {"detail": exc.messages}) from exc
        return Response(GodownMasterSerializer(godown).data)

    def delete(self, request, pk: int):
        godown = self.get_object(pk)
        self.enforce_scope(request, entity_id=godown.entity_id, subentity_id=godown.subentity_id)
        self.assert_permission(request, godown.entity_id, "inventory.location.delete")
        godown.is_active = False
        godown.is_default = False
        godown.save(update_fields=["is_active", "is_default", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class InventoryTransferCreateAPIView(_BaseInventoryOpsAPIView):
    def post(self, request):
        serializer = InventoryTransferCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        self.enforce_scope(
            request,
            entity_id=payload["entity"],
            entityfinid_id=payload.get("entityfinid"),
            subentity_id=payload.get("subentity"),
        )
        self.assert_permission(request, payload["entity"], "inventory.transfer.create")
        result = InventoryTransferService.create_transfer(payload=payload, user_id=request.user.id)
        response = InventoryTransferResponseSerializer(result.transfer)
        return Response(
            {
                "report_code": "inventory_transfer_entry",
                "transfer": response.data,
                "entry_id": result.entry_id,
            },
            status=status.HTTP_201_CREATED,
        )


class InventoryTransferListAPIView(_BaseInventoryOpsAPIView):
    def get(self, request):
        entity_id = int(request.query_params.get("entity") or 0)
        if not entity_id:
            return Response({"detail": "entity is required."}, status=status.HTTP_400_BAD_REQUEST)
        self.enforce_scope(request, entity_id=entity_id)
        self.assert_permission(request, entity_id, "inventory.transfer.view")
        from .models import InventoryTransfer

        qs = (
            InventoryTransfer.objects.filter(entity_id=entity_id)
            .select_related("source_location", "destination_location")
            .prefetch_related("lines")
            .order_by("-transfer_date", "-id")
        )
        serializer = InventoryTransferListSerializer(qs, many=True)
        return Response({"rows": serializer.data})


class InventoryTransferDetailAPIView(_BaseInventoryOpsAPIView):
    def get(self, request, pk: int):
        from .models import InventoryTransfer

        transfer = get_object_or_404(
            InventoryTransfer.objects.select_related("source_location", "destination_location").prefetch_related("lines__product", "lines__uom"),
            pk=pk,
        )
        self.enforce_scope(request, entity_id=transfer.entity_id, entityfinid_id=transfer.entityfin_id, subentity_id=transfer.subentity_id)
        self.assert_permission(request, transfer.entity_id, "inventory.transfer.view")
        return Response(InventoryTransferResponseSerializer(transfer).data)


class InventoryAdjustmentCreateAPIView(_BaseInventoryOpsAPIView):
    def post(self, request):
        serializer = InventoryAdjustmentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        self.enforce_scope(
            request,
            entity_id=payload["entity"],
            entityfinid_id=payload.get("entityfinid"),
            subentity_id=payload.get("subentity"),
        )
        self.assert_permission(request, payload["entity"], "inventory.adjustment.create")
        result = InventoryAdjustmentService.create_adjustment(payload=payload, user_id=request.user.id)
        response = InventoryAdjustmentResponseSerializer(result.adjustment)
        return Response(
            {
                "report_code": "inventory_adjustment_entry",
                "adjustment": response.data,
                "entry_id": result.entry_id,
            },
            status=status.HTTP_201_CREATED,
        )


class InventoryAdjustmentListAPIView(_BaseInventoryOpsAPIView):
    def get(self, request):
        entity_id = int(request.query_params.get("entity") or 0)
        if not entity_id:
            return Response({"detail": "entity is required."}, status=status.HTTP_400_BAD_REQUEST)
        self.enforce_scope(request, entity_id=entity_id)
        self.assert_permission(request, entity_id, "inventory.adjustment.view")
        from .models import InventoryAdjustment

        qs = (
            InventoryAdjustment.objects.filter(entity_id=entity_id)
            .select_related("location")
            .prefetch_related("lines")
            .order_by("-adjustment_date", "-id")
        )
        serializer = InventoryAdjustmentListSerializer(qs, many=True)
        return Response({"rows": serializer.data})


class InventoryAdjustmentDetailAPIView(_BaseInventoryOpsAPIView):
    def get(self, request, pk: int):
        from .models import InventoryAdjustment

        adjustment = get_object_or_404(
            InventoryAdjustment.objects.select_related("location").prefetch_related("lines__product", "lines__uom"),
            pk=pk,
        )
        self.enforce_scope(request, entity_id=adjustment.entity_id, entityfinid_id=adjustment.entityfin_id, subentity_id=adjustment.subentity_id)
        self.assert_permission(request, adjustment.entity_id, "inventory.adjustment.view")
        return Response(InventoryAdjustmentResponseSerializer(adjustment).data)
