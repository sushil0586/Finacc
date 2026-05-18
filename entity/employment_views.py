from django.db.models import Q
from rest_framework import permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.entitlements import ScopedEntitlementMixin
from entity.employment_serializers import (
    EntityEmploymentHierarchySerializer,
    EntityEmploymentHierarchyNodeSerializer,
    EntityEmploymentManagerSerializer,
    EntityEmploymentProfileSerializer,
)
from entity.models import EntityEmploymentProfile
from subscriptions.services import SubscriptionService


class EntityEmploymentScopedAPIView(ScopedEntitlementMixin, APIView):
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
        self.enforce_scope(request, entity_id=obj.entity_id, subentity_id=obj.subentity_id)


class EntityEmploymentMetaAPIView(EntityEmploymentScopedAPIView):
    def get(self, request):
        payload = {
            "statuses": [{"key": key, "label": label} for key, label in EntityEmploymentProfile.EmploymentStatus.choices],
            "employment_types": [{"key": key, "label": label} for key, label in EntityEmploymentProfile.EmploymentType.choices],
            "work_types": [{"key": key, "label": label} for key, label in EntityEmploymentProfile.WorkType.choices],
            "exit_statuses": [{"key": key, "label": label} for key, label in EntityEmploymentProfile.ExitStatus.choices],
        }
        return Response(payload)


class EntityEmploymentProfileListCreateAPIView(EntityEmploymentScopedAPIView):
    def get_queryset(self, request):
        entity_id, subentity_id = self._scope_from_query(request)
        employee_user_id = self._parse_int(request.query_params.get("employee_user"), "employee_user", required=False)
        manager_user_id = self._parse_int(request.query_params.get("manager_user"), "manager_user", required=False)
        status_filter = (request.query_params.get("status") or "").strip().lower() or None
        current_only = (request.query_params.get("current_only") or "false").strip().lower() == "true"
        search = (request.query_params.get("search") or "").strip()

        qs = EntityEmploymentProfile.objects.filter(entity_id=entity_id, isactive=True)
        if subentity_id is not None:
            qs = qs.filter(subentity_id=subentity_id)
        if employee_user_id is not None:
            qs = qs.filter(employee_user_id=employee_user_id)
        if manager_user_id is not None:
            qs = qs.filter(manager_user_id=manager_user_id)
        if status_filter:
            qs = qs.filter(status=status_filter)
        if current_only:
            qs = qs.filter(effective_to__isnull=True)
        if search:
            qs = qs.filter(
                Q(employee_code__icontains=search)
                | Q(full_name__icontains=search)
                | Q(work_email__icontains=search)
            )
        return qs.select_related(
            "entity",
            "subentity",
            "employee_user",
            "business_unit",
            "department",
            "work_location",
            "cost_center",
            "grade",
            "designation",
            "manager_user",
        )

    def get(self, request):
        serializer = EntityEmploymentProfileSerializer(self.get_queryset(request), many=True)
        return Response(serializer.data)

    def post(self, request):
        if not isinstance(request.data, dict):
            raise ValidationError({"detail": "Expected an object payload."})
        self._scope_from_payload(request, request.data)
        serializer = EntityEmploymentProfileSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(createdby=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class EntityEmploymentProfileDetailAPIView(EntityEmploymentScopedAPIView):
    def get_object(self, request, pk):
        obj = EntityEmploymentProfile.objects.select_related(
            "entity",
            "subentity",
            "employee_user",
            "business_unit",
            "department",
            "work_location",
            "cost_center",
            "grade",
            "designation",
            "manager_user",
        ).filter(pk=pk, isactive=True).first()
        if obj is None:
            return None
        self._enforce_object_scope(request, obj)
        return obj

    def get(self, request, pk):
        obj = self.get_object(request, pk)
        if obj is None:
            return Response({"detail": "Employment profile not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(EntityEmploymentProfileSerializer(obj).data)

    def put(self, request, pk):
        obj = self.get_object(request, pk)
        if obj is None:
            return Response({"detail": "Employment profile not found."}, status=status.HTTP_404_NOT_FOUND)
        payload = request.data.copy()
        payload["entity"] = obj.entity_id
        if "subentity" not in payload:
            payload["subentity"] = obj.subentity_id
        serializer = EntityEmploymentProfileSerializer(instance=obj, data=payload)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def patch(self, request, pk):
        obj = self.get_object(request, pk)
        if obj is None:
            return Response({"detail": "Employment profile not found."}, status=status.HTTP_404_NOT_FOUND)
        payload = request.data.copy()
        payload["entity"] = obj.entity_id
        if "subentity" not in payload:
            payload["subentity"] = obj.subentity_id
        serializer = EntityEmploymentProfileSerializer(instance=obj, data=payload, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class EntityEmploymentManagerListAPIView(EntityEmploymentScopedAPIView):
    def get(self, request):
        entity_id, subentity_id = self._scope_from_query(request)
        search = (request.query_params.get("search") or "").strip()

        qs = EntityEmploymentProfile.objects.filter(
            entity_id=entity_id,
            isactive=True,
        ).exclude(
            status=EntityEmploymentProfile.EmploymentStatus.EXITED,
        )
        if subentity_id is not None:
            qs = qs.filter(subentity_id=subentity_id)
        if (request.query_params.get("current_only") or "true").strip().lower() != "false":
            qs = qs.filter(effective_to__isnull=True)
        if search:
            qs = qs.filter(
                Q(employee_code__icontains=search)
                | Q(full_name__icontains=search)
                | Q(work_email__icontains=search)
            )

        serializer = EntityEmploymentManagerSerializer(
            qs.select_related("department", "designation", "subentity", "manager_user").order_by("full_name", "id"),
            many=True,
        )
        return Response(serializer.data)


class EntityEmploymentHierarchyAPIView(EntityEmploymentScopedAPIView):
    def _resolve_current_profile(self, *, entity_id, employee_user_id, subentity_id=None):
        queryset = EntityEmploymentProfile.objects.filter(
            entity_id=entity_id,
            employee_user_id=employee_user_id,
            isactive=True,
        ).exclude(status=EntityEmploymentProfile.EmploymentStatus.EXITED)
        if subentity_id is not None:
            queryset = queryset.filter(Q(subentity_id=subentity_id) | Q(subentity__isnull=True))
        current = queryset.filter(effective_to__isnull=True).order_by("-effective_from", "-id").first()
        if current is not None:
            return current
        return queryset.order_by("-effective_from", "-id").first()

    def get(self, request):
        entity_id, subentity_id = self._scope_from_query(request)
        employee_user_id = self._parse_int(request.query_params.get("employee_user"), "employee_user", required=True)

        root = self._resolve_current_profile(
            entity_id=entity_id,
            employee_user_id=employee_user_id,
            subentity_id=subentity_id,
        )
        if root is None:
            return Response({"detail": "Employment profile not found."}, status=status.HTTP_404_NOT_FOUND)

        chain = []
        visited_user_ids = {root.employee_user_id}
        current_manager_user_id = root.manager_user_id
        while current_manager_user_id and len(chain) < 10:
            if current_manager_user_id in visited_user_ids:
                break
            manager_profile = self._resolve_current_profile(
                entity_id=entity_id,
                employee_user_id=current_manager_user_id,
                subentity_id=subentity_id,
            )
            if manager_profile is None:
                break
            chain.append(manager_profile)
            visited_user_ids.add(current_manager_user_id)
            current_manager_user_id = manager_profile.manager_user_id

        payload = {
            "employee_user": root.employee_user_id,
            "employee_code": root.employee_code,
            "full_name": root.full_name,
            "chain": EntityEmploymentHierarchyNodeSerializer(chain, many=True).data,
            "depth": len(chain),
        }
        return Response(EntityEmploymentHierarchySerializer(payload).data)
