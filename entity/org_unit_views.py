from django.db.models import Q
from rest_framework import permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.entitlements import ScopedEntitlementMixin
from entity.models import EntityOrgUnit
from entity.org_unit_serializers import EntityOrgUnitMetaSerializer, EntityOrgUnitSerializer
from subscriptions.services import SubscriptionService


class EntityOrgUnitScopedAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    subscription_access_mode = SubscriptionService.ACCESS_MODE_SETUP

    @staticmethod
    def _parse_int(raw_value, field_name, *, required):
        if raw_value in (None, "", "null", "None"):
            if required:
                raise ValidationError({field_name: f"{field_name} is required."})
            return None
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            raise ValidationError({field_name: f"{field_name} must be an integer."})
        return None if field_name == "subentity" and value == 0 else value

    def _scope_from_query(self, request, *, require_entity=True):
        entity_id = self._parse_int(request.query_params.get("entity"), "entity", required=require_entity)
        subentity_id = self._parse_int(request.query_params.get("subentity"), "subentity", required=False)
        if entity_id is not None:
            self.enforce_scope(request, entity_id=entity_id, subentity_id=subentity_id)
        return entity_id, subentity_id

    def _scope_from_payload(self, request, payload):
        entity_id = self._parse_int(payload.get("entity"), "entity", required=True)
        subentity_id = self._parse_int(payload.get("subentity"), "subentity", required=False)
        self.enforce_scope(request, entity_id=entity_id, subentity_id=subentity_id)
        return entity_id, subentity_id

    def _enforce_object_scope(self, request, obj):
        self.enforce_scope(
            request,
            entity_id=obj.entity_id,
            subentity_id=obj.subentity_id,
        )


class EntityOrgUnitMetaAPIView(EntityOrgUnitScopedAPIView):
    def get(self, request):
        payload = {
            "unit_types": [
                {"key": key, "label": label}
                for key, label in EntityOrgUnit.UnitType.choices
            ],
            "resolution_modes": [
                {
                    "key": "entity_only",
                    "label": "Entity Only",
                    "description": "Return only shared entity-level org units.",
                },
                {
                    "key": "subentity_only",
                    "label": "Subentity Only",
                    "description": "Return only rows attached to the selected subentity.",
                },
                {
                    "key": "resolved",
                    "label": "Resolved",
                    "description": "Return shared rows plus subentity-specific overrides.",
                },
            ],
        }
        serializer = EntityOrgUnitMetaSerializer(payload)
        return Response(serializer.data)


class EntityOrgUnitListCreateAPIView(EntityOrgUnitScopedAPIView):
    def get_queryset(self, request):
        entity_id, subentity_id = self._scope_from_query(request)
        unit_type = (request.query_params.get("unit_type") or "").strip().lower() or None
        resolution_mode = (request.query_params.get("resolution_mode") or "resolved").strip().lower()
        active_only = (request.query_params.get("active_only") or "true").strip().lower() != "false"
        status_filter = (request.query_params.get("status") or "").strip().lower() or None
        search = (request.query_params.get("search") or "").strip()

        queryset = EntityOrgUnit.objects.filter(entity_id=entity_id)
        if active_only:
            queryset = queryset.filter(isactive=True)
        if unit_type:
            queryset = queryset.filter(unit_type=unit_type)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if subentity_id is not None:
            if resolution_mode == "subentity_only":
                queryset = queryset.filter(subentity_id=subentity_id)
            elif resolution_mode == "entity_only":
                queryset = queryset.filter(subentity__isnull=True)
            else:
                queryset = queryset.filter(Q(subentity__isnull=True) | Q(subentity_id=subentity_id))
        elif resolution_mode == "entity_only":
            queryset = queryset.filter(subentity__isnull=True)

        if search:
            queryset = queryset.filter(
                Q(code__icontains=search)
                | Q(name__icontains=search)
                | Q(short_name__icontains=search)
                | Q(description__icontains=search)
            )

        return queryset.select_related("entity", "subentity", "parent")

    def get(self, request):
        serializer = EntityOrgUnitSerializer(self.get_queryset(request), many=True)
        return Response(serializer.data)

    def post(self, request):
        payload = request.data.copy()
        self._scope_from_payload(request, payload)
        serializer = EntityOrgUnitSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        serializer.save(createdby=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class EntityOrgUnitDetailAPIView(EntityOrgUnitScopedAPIView):
    def get_object(self, request, pk):
        obj = EntityOrgUnit.objects.select_related("entity", "subentity", "parent").filter(pk=pk, isactive=True).first()
        if obj is None:
            return None
        self._enforce_object_scope(request, obj)
        return obj

    def get(self, request, pk):
        obj = self.get_object(request, pk)
        if obj is None:
            return Response({"detail": "Org unit not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(EntityOrgUnitSerializer(obj).data)

    def put(self, request, pk):
        obj = self.get_object(request, pk)
        if obj is None:
            return Response({"detail": "Org unit not found."}, status=status.HTTP_404_NOT_FOUND)
        payload = request.data.copy()
        payload["entity"] = obj.entity_id
        if "subentity" not in payload:
            payload["subentity"] = obj.subentity_id
        serializer = EntityOrgUnitSerializer(instance=obj, data=payload)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def patch(self, request, pk):
        obj = self.get_object(request, pk)
        if obj is None:
            return Response({"detail": "Org unit not found."}, status=status.HTTP_404_NOT_FOUND)
        payload = request.data.copy()
        payload["entity"] = obj.entity_id
        if "subentity" not in payload:
            payload["subentity"] = obj.subentity_id
        serializer = EntityOrgUnitSerializer(instance=obj, data=payload, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
