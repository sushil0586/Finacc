from django.db.models import Case, IntegerField, Q, Value, When
from rest_framework import permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.entitlements import ScopedEntitlementMixin
from entity.approval_policy_serializers import EntityApprovalPolicyMetaSerializer, EntityApprovalPolicySerializer
from entity.models import EntityApprovalPolicy
from subscriptions.services import SubscriptionService


class EntityApprovalPolicyScopedAPIView(ScopedEntitlementMixin, APIView):
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
        return None if field_name in {"subentity", "org_unit"} and value == 0 else value

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


class EntityApprovalPolicyMetaAPIView(EntityApprovalPolicyScopedAPIView):
    def get(self, request):
        payload = {
            "policy_keys": [{"key": key, "label": label} for key, label in EntityApprovalPolicy.PolicyKey.choices],
            "approval_modes": [{"key": key, "label": label} for key, label in EntityApprovalPolicy.ApprovalMode.choices],
            "statuses": [{"key": key, "label": label} for key, label in EntityApprovalPolicy.Status.choices],
            "resolution_modes": [
                {"key": "entity_only", "label": "Entity Only"},
                {"key": "subentity_only", "label": "Subentity Only"},
                {"key": "org_unit_only", "label": "Org Unit Only"},
                {"key": "resolved", "label": "Resolved"},
            ],
        }
        return Response(EntityApprovalPolicyMetaSerializer(payload).data)


class EntityApprovalPolicyListCreateAPIView(EntityApprovalPolicyScopedAPIView):
    def get_queryset(self, request):
        entity_id, subentity_id = self._scope_from_query(request)
        org_unit_id = self._parse_int(request.query_params.get("org_unit"), "org_unit", required=False)
        policy_key = (request.query_params.get("policy_key") or "").strip().lower() or None
        status_filter = (request.query_params.get("status") or "").strip().lower() or None
        resolution_mode = (request.query_params.get("resolution_mode") or "resolved").strip().lower()
        active_only = (request.query_params.get("active_only") or "true").strip().lower() != "false"
        search = (request.query_params.get("search") or "").strip()

        queryset = EntityApprovalPolicy.objects.filter(entity_id=entity_id)
        if active_only:
            queryset = queryset.filter(isactive=True)
        if policy_key:
            queryset = queryset.filter(policy_key=policy_key)
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        if org_unit_id is not None:
            if resolution_mode == "org_unit_only":
                queryset = queryset.filter(org_unit_id=org_unit_id)
            elif resolution_mode == "subentity_only" and subentity_id is not None:
                queryset = queryset.filter(subentity_id=subentity_id, org_unit__isnull=True)
            elif resolution_mode == "entity_only":
                queryset = queryset.filter(subentity__isnull=True, org_unit__isnull=True)
            else:
                filters = Q(subentity__isnull=True, org_unit__isnull=True) | Q(org_unit_id=org_unit_id)
                if subentity_id is not None:
                    filters |= Q(subentity_id=subentity_id, org_unit__isnull=True)
                queryset = queryset.filter(filters)
        elif subentity_id is not None:
            if resolution_mode == "subentity_only":
                queryset = queryset.filter(subentity_id=subentity_id, org_unit__isnull=True)
            elif resolution_mode == "entity_only":
                queryset = queryset.filter(subentity__isnull=True, org_unit__isnull=True)
            else:
                queryset = queryset.filter(
                    Q(subentity__isnull=True, org_unit__isnull=True)
                    | Q(subentity_id=subentity_id, org_unit__isnull=True)
                )
        elif resolution_mode == "entity_only":
            queryset = queryset.filter(subentity__isnull=True, org_unit__isnull=True)

        if search:
            queryset = queryset.filter(
                Q(code__icontains=search)
                | Q(name__icontains=search)
                | Q(policy_key__icontains=search)
            )

        specificity_order = Case(
            When(org_unit__isnull=False, then=Value(0)),
            When(subentity__isnull=False, then=Value(1)),
            default=Value(2),
            output_field=IntegerField(),
        )
        return queryset.select_related("entity", "subentity", "org_unit").order_by(
            specificity_order,
            "name",
            "id",
        )

    def get(self, request):
        serializer = EntityApprovalPolicySerializer(self.get_queryset(request), many=True)
        return Response(serializer.data)

    def post(self, request):
        payload = request.data.copy()
        self._scope_from_payload(request, payload)
        serializer = EntityApprovalPolicySerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        serializer.save(createdby=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class EntityApprovalPolicyDetailAPIView(EntityApprovalPolicyScopedAPIView):
    def get_object(self, request, pk):
        obj = EntityApprovalPolicy.objects.select_related("entity", "subentity", "org_unit").filter(pk=pk, isactive=True).first()
        if obj is None:
            return None
        self._enforce_object_scope(request, obj)
        return obj

    def get(self, request, pk):
        obj = self.get_object(request, pk)
        if obj is None:
            return Response({"detail": "Approval policy not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(EntityApprovalPolicySerializer(obj).data)

    def put(self, request, pk):
        obj = self.get_object(request, pk)
        if obj is None:
            return Response({"detail": "Approval policy not found."}, status=status.HTTP_404_NOT_FOUND)
        payload = request.data.copy()
        payload["entity"] = obj.entity_id
        if "subentity" not in payload:
            payload["subentity"] = obj.subentity_id
        serializer = EntityApprovalPolicySerializer(instance=obj, data=payload)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def patch(self, request, pk):
        obj = self.get_object(request, pk)
        if obj is None:
            return Response({"detail": "Approval policy not found."}, status=status.HTTP_404_NOT_FOUND)
        payload = request.data.copy()
        payload["entity"] = obj.entity_id
        if "subentity" not in payload:
            payload["subentity"] = obj.subentity_id
        serializer = EntityApprovalPolicySerializer(instance=obj, data=payload, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
