from __future__ import annotations

from typing import Any, Optional

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import Product
from core.entitlements import ScopedEntitlementMixin
from entity.models import Godown
from numbering.models import DocumentNumberSeries
from numbering.services import ensure_document_type, ensure_series
from rbac.services import EffectivePermissionService

from .models import ManufacturingBOM, ManufacturingRoute, ManufacturingSettings, ManufacturingWorkOrder
from .serializers import (
    ManufacturingBOMListSerializer,
    ManufacturingBOMResponseSerializer,
    ManufacturingBOMWriteSerializer,
    ManufacturingOperationActionSerializer,
    ManufacturingRouteListSerializer,
    ManufacturingRouteResponseSerializer,
    ManufacturingRouteWriteSerializer,
    ManufacturingWorkOrderListSerializer,
    ManufacturingWorkOrderResponseSerializer,
    ManufacturingWorkOrderWriteSerializer,
)
from .services import ManufacturingWorkOrderService


def _choice_payload(choices) -> list[dict]:
    return [{"value": value, "label": label} for value, label in choices]


MANUFACTURING_SETTINGS_SCHEMA = [
    {"name": "default_doc_code_work_order", "label": "Default Work Order Doc Code", "type": "string", "group": "numbering_defaults"},
    {"name": "default_workflow_action", "label": "Default Workflow", "type": "choice", "group": "workflow", "choices": _choice_payload(ManufacturingSettings.DefaultWorkflowAction.choices)},
    {"name": "auto_explode_materials_from_bom", "label": "Auto Explode Materials From BOM", "type": "boolean", "group": "bom_controls"},
    {"name": "allow_manual_material_override", "label": "Allow Manual Material Override", "type": "boolean", "group": "bom_controls"},
    {"name": "require_batch_for_batch_managed_items", "label": "Require Batch For Batch Managed Items", "type": "boolean", "group": "batch_validation"},
    {"name": "require_expiry_when_expiry_tracked", "label": "Require Expiry When Expiry Tracked", "type": "boolean", "group": "batch_validation"},
    {"name": "block_negative_stock", "label": "Block Negative Stock", "type": "boolean", "group": "stock_controls"},
    {"name": "default_output_batch_mode", "label": "Default Output Batch Mode", "type": "choice", "group": "batch_validation", "choices": _choice_payload([("manual", "Manual"), ("copy_from_reference", "Copy From Reference")])},
]

EDITABLE_SETTINGS_FIELDS = {
    "default_doc_code_work_order",
    "default_workflow_action",
    "auto_explode_materials_from_bom",
    "allow_manual_material_override",
    "require_batch_for_batch_managed_items",
    "require_expiry_when_expiry_tracked",
    "block_negative_stock",
    "default_output_batch_mode",
}


class _BaseManufacturingAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_permission_codes(self, request, entity_id):
        return EffectivePermissionService.permission_codes_for_user(request.user, entity_id)

    def assert_permission(self, request, entity_id: int, permission_code: str):
        if permission_code not in self.get_permission_codes(request, entity_id):
            raise PermissionDenied(f"Missing permission: {permission_code}")

    @staticmethod
    def _parse_int(raw_value: Any, field_name: str, *, required: bool) -> Optional[int]:
        if raw_value in (None, "", "null", "None"):
            if required:
                raise ValidationError({field_name: f"{field_name} is required."})
            return None
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            raise ValidationError({field_name: f"{field_name} must be an integer."})
        return None if field_name == "subentity_id" and value == 0 else value

    def _scope(self, request, *, require_entityfinid: bool) -> tuple[int, Optional[int], Optional[int]]:
        entity_id = self._parse_int(request.query_params.get("entity"), "entity", required=True)
        subentity_id = self._parse_int(request.query_params.get("subentity"), "subentity_id", required=False)
        entityfinid_id = self._parse_int(request.query_params.get("entityfinid"), "entityfinid", required=require_entityfinid)
        self.enforce_scope(request, entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id)
        return entity_id, subentity_id, entityfinid_id


class ManufacturingSettingsAPIView(_BaseManufacturingAPIView):
    def _get_settings(self, *, entity_id: int, subentity_id: Optional[int]) -> ManufacturingSettings:
        settings_obj, _ = ManufacturingSettings.objects.get_or_create(entity_id=entity_id, subentity_id=subentity_id)
        return settings_obj

    @staticmethod
    def _settings_payload(settings_obj: ManufacturingSettings) -> dict[str, Any]:
        payload = {
            "default_doc_code_work_order": settings_obj.default_doc_code_work_order,
            "default_workflow_action": settings_obj.default_workflow_action,
        }
        payload.update(settings_obj.policy_controls or {})
        return payload

    @staticmethod
    def _ensure_doc_type(settings_obj: ManufacturingSettings):
        doc_code = settings_obj.default_doc_code_work_order or "MWO"
        return ensure_document_type(
            module="manufacturing",
            doc_key="MANUFACTURING_WORK_ORDER",
            name="Manufacturing Work Order",
            default_code=doc_code,
        )

    def _series_payload(self, *, entity_id: int, entityfinid_id: int, subentity_id: Optional[int], settings_obj: ManufacturingSettings) -> list[dict]:
        doc_type = self._ensure_doc_type(settings_obj)
        doc_code = settings_obj.default_doc_code_work_order or "MWO"
        series = DocumentNumberSeries.objects.filter(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            doc_type_id=doc_type.id,
            doc_code=doc_code,
        ).first()
        if not series:
            series, _ = ensure_series(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                subentity_id=subentity_id,
                doc_type_id=doc_type.id,
                doc_code=doc_code,
                prefix=doc_code,
                start=1,
                padding=4,
                reset="yearly",
                include_year=False,
                include_month=False,
            )
        return [{
            "series_key": "manufacturing_work_order",
            "label": "Manufacturing Work Order",
            "doc_code": series.doc_code,
            "prefix": series.prefix,
            "suffix": series.suffix,
            "starting_number": series.starting_number,
            "current_number": series.current_number,
            "number_padding": series.number_padding,
            "separator": series.separator,
            "reset_frequency": series.reset_frequency,
            "include_year": series.include_year,
            "include_month": series.include_month,
            "custom_format": series.custom_format,
            "is_active": series.is_active,
        }]

    @staticmethod
    def _validate_settings_updates(settings_updates: dict[str, Any]) -> None:
        workflow_values = {v for v, _ in ManufacturingSettings.DefaultWorkflowAction.choices}
        if "default_doc_code_work_order" in settings_updates:
            code = str(settings_updates["default_doc_code_work_order"] or "").strip()
            if not code:
                raise ValidationError({"default_doc_code_work_order": "This field cannot be blank."})
            if len(code) > 10:
                raise ValidationError({"default_doc_code_work_order": "Ensure this value has at most 10 characters."})
        if "default_workflow_action" in settings_updates and settings_updates["default_workflow_action"] not in workflow_values:
            raise ValidationError({"default_workflow_action": f"Invalid value. Allowed: {', '.join(sorted(workflow_values))}."})
        if "default_output_batch_mode" in settings_updates and settings_updates["default_output_batch_mode"] not in {"manual", "copy_from_reference"}:
            raise ValidationError({"default_output_batch_mode": "Allowed values: manual, copy_from_reference."})

    def get(self, request):
        entity_id, subentity_id, entityfinid_id = self._scope(request, require_entityfinid=False)
        self.assert_permission(request, entity_id, "manufacturing.settings.view")
        settings_obj = self._get_settings(entity_id=entity_id, subentity_id=subentity_id)
        return Response({
            "settings": self._settings_payload(settings_obj),
            "numbering_series": self._series_payload(entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id, settings_obj=settings_obj) if entityfinid_id else [],
            "capabilities": {"has_numbering_management": bool(entityfinid_id)},
        })

    @transaction.atomic
    def patch(self, request):
        entity_id = self._parse_int(request.data.get("entity"), "entity", required=True)
        subentity_id = self._parse_int(request.data.get("subentity"), "subentity_id", required=False)
        entityfinid_id = self._parse_int(request.data.get("entityfinid"), "entityfinid", required=False)
        self.enforce_scope(request, entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id)
        self.assert_permission(request, entity_id, "manufacturing.settings.view")
        settings_obj = self._get_settings(entity_id=entity_id, subentity_id=subentity_id)

        settings_payload = request.data.get("settings")
        if settings_payload is not None:
            if not isinstance(settings_payload, dict):
                raise ValidationError({"settings": "Provide settings as an object."})
            settings_updates = {key: settings_payload[key] for key in EDITABLE_SETTINGS_FIELDS if key in settings_payload}
            self._validate_settings_updates(settings_updates)
            policy_controls = dict(settings_obj.policy_controls or {})
            for key, value in settings_updates.items():
                if key in {"default_doc_code_work_order", "default_workflow_action"}:
                    setattr(settings_obj, key, value)
                else:
                    policy_controls[key] = value
            settings_obj.policy_controls = policy_controls
            settings_obj.save()

        return Response({
            "settings": self._settings_payload(settings_obj),
            "numbering_series": self._series_payload(entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id, settings_obj=settings_obj) if entityfinid_id else [],
            "capabilities": {"has_numbering_management": bool(entityfinid_id)},
        })


class ManufacturingSettingsMetaAPIView(ManufacturingSettingsAPIView):
    def get(self, request):
        response = super().get(request)
        payload = dict(response.data)
        payload["schema"] = MANUFACTURING_SETTINGS_SCHEMA
        return Response(payload)


class ManufacturingRouteListCreateAPIView(_BaseManufacturingAPIView, generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        entity_id, subentity_id, _ = self._scope(self.request, require_entityfinid=False)
        self.assert_permission(self.request, entity_id, "manufacturing.bom.view")
        qs = ManufacturingRoute.objects.filter(entity_id=entity_id).prefetch_related("steps")
        if subentity_id is None:
            qs = qs.filter(subentity_id__isnull=True)
        else:
            qs = qs.filter(subentity_id=subentity_id)
        return qs.order_by("code", "id")

    def get_serializer_class(self):
        if self.request.method.upper() == "GET":
            return ManufacturingRouteListSerializer
        return ManufacturingRouteWriteSerializer

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = ManufacturingRouteListSerializer(queryset, many=True)
        return Response({"rows": serializer.data})

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        entity_id = payload["entity"]
        self.enforce_scope(request, entity_id=entity_id, entityfinid_id=None, subentity_id=payload.get("subentity"))
        self.assert_permission(request, entity_id, "manufacturing.bom.create")

        route = ManufacturingRoute.objects.create(
            entity_id=entity_id,
            subentity_id=payload.get("subentity"),
            code=payload["code"],
            name=payload["name"],
            description=payload.get("description") or "",
            is_active=payload.get("is_active", True),
            created_by=request.user,
            updated_by=request.user,
        )
        steps = [
            route.steps.model(
                route=route,
                sequence_no=row.get("sequence_no") or index,
                step_code=row.get("step_code") or "",
                step_name=row["step_name"],
                description=row.get("description") or "",
                default_duration_mins=row.get("default_duration_mins"),
                requires_qc=row.get("requires_qc", False),
                is_mandatory=row.get("is_mandatory", True),
            )
            for index, row in enumerate(payload["steps"], start=1)
        ]
        if steps:
            route.steps.model.objects.bulk_create(steps)
        route.refresh_from_db()
        return Response(ManufacturingRouteResponseSerializer(route).data, status=status.HTTP_201_CREATED)


class ManufacturingRouteDetailAPIView(_BaseManufacturingAPIView, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return ManufacturingRoute.objects.prefetch_related("steps")

    def get_serializer_class(self):
        if self.request.method.upper() == "GET":
            return ManufacturingRouteResponseSerializer
        return ManufacturingRouteWriteSerializer

    def retrieve(self, request, *args, **kwargs):
        route = self.get_object()
        self.enforce_scope(request, entity_id=route.entity_id, entityfinid_id=None, subentity_id=route.subentity_id)
        self.assert_permission(request, route.entity_id, "manufacturing.bom.view")
        return Response(ManufacturingRouteResponseSerializer(route).data)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        route = self.get_object()
        self.enforce_scope(request, entity_id=route.entity_id, entityfinid_id=None, subentity_id=route.subentity_id)
        self.assert_permission(request, route.entity_id, "manufacturing.bom.update")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        route.subentity_id = payload.get("subentity")
        route.code = payload["code"]
        route.name = payload["name"]
        route.description = payload.get("description") or ""
        route.is_active = payload.get("is_active", True)
        route.updated_by = request.user
        route.save()
        route.steps.all().delete()
        steps = [
            route.steps.model(
                route=route,
                sequence_no=row.get("sequence_no") or index,
                step_code=row.get("step_code") or "",
                step_name=row["step_name"],
                description=row.get("description") or "",
                default_duration_mins=row.get("default_duration_mins"),
                requires_qc=row.get("requires_qc", False),
                is_mandatory=row.get("is_mandatory", True),
            )
            for index, row in enumerate(payload["steps"], start=1)
        ]
        if steps:
            route.steps.model.objects.bulk_create(steps)
        route.refresh_from_db()
        return Response(ManufacturingRouteResponseSerializer(route).data)

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        route = self.get_object()
        self.enforce_scope(request, entity_id=route.entity_id, entityfinid_id=None, subentity_id=route.subentity_id)
        self.assert_permission(request, route.entity_id, "manufacturing.bom.delete")
        route.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ManufacturingBOMListCreateAPIView(_BaseManufacturingAPIView, generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        entity_id, subentity_id, _ = self._scope(self.request, require_entityfinid=False)
        self.assert_permission(self.request, entity_id, "manufacturing.bom.view")
        qs = ManufacturingBOM.objects.filter(entity_id=entity_id).select_related("finished_product", "output_uom", "route").prefetch_related("materials")
        if subentity_id is None:
            qs = qs.filter(subentity_id__isnull=True)
        else:
            qs = qs.filter(subentity_id=subentity_id)
        return qs.order_by("code", "id")

    def get_serializer_class(self):
        if self.request.method.upper() == "GET":
            return ManufacturingBOMListSerializer
        return ManufacturingBOMWriteSerializer

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = ManufacturingBOMListSerializer(queryset, many=True)
        return Response({"rows": serializer.data})

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        entity_id = payload["entity"]
        self.enforce_scope(request, entity_id=entity_id, entityfinid_id=None, subentity_id=payload.get("subentity"))
        self.assert_permission(request, entity_id, "manufacturing.bom.create")

        bom = ManufacturingBOM.objects.create(
            entity_id=entity_id,
            subentity_id=payload.get("subentity"),
            code=payload["code"],
            name=payload["name"],
            description=payload.get("description") or "",
            finished_product_id=payload["finished_product"],
            route_id=get_object_or_404(ManufacturingRoute, id=payload.get("route"), entity_id=entity_id).id if payload.get("route") else None,
            output_qty=payload["output_qty"],
            output_uom_id=Product.objects.filter(id=payload["finished_product"]).values_list("base_uom_id", flat=True).first(),
            is_active=payload.get("is_active", True),
            created_by=request.user,
            updated_by=request.user,
        )
        material_rows = []
        for idx, row in enumerate(payload["materials"], start=1):
            material_product = get_object_or_404(Product, id=row["material_product"], entity_id=entity_id)
            material_rows.append(
                bom.materials.model(
                    bom=bom,
                    line_no=idx,
                    material_product=material_product,
                    qty=row["qty"],
                    uom=getattr(material_product, "base_uom", None),
                    waste_percent=row.get("waste_percent") or 0,
                    note=row.get("note") or "",
                )
            )
        if material_rows:
            bom.materials.model.objects.bulk_create(material_rows)
        bom.refresh_from_db()
        return Response(ManufacturingBOMResponseSerializer(bom).data, status=status.HTTP_201_CREATED)


class ManufacturingBOMDetailAPIView(_BaseManufacturingAPIView, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return ManufacturingBOM.objects.select_related("finished_product", "output_uom").prefetch_related("materials__material_product", "materials__uom")

    def get_serializer_class(self):
        if self.request.method.upper() == "GET":
            return ManufacturingBOMResponseSerializer
        return ManufacturingBOMWriteSerializer

    def retrieve(self, request, *args, **kwargs):
        bom = self.get_object()
        self.enforce_scope(request, entity_id=bom.entity_id, entityfinid_id=None, subentity_id=bom.subentity_id)
        self.assert_permission(request, bom.entity_id, "manufacturing.bom.view")
        return Response(ManufacturingBOMResponseSerializer(bom).data)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        bom = self.get_object()
        self.enforce_scope(request, entity_id=bom.entity_id, entityfinid_id=None, subentity_id=bom.subentity_id)
        self.assert_permission(request, bom.entity_id, "manufacturing.bom.update")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        bom.subentity_id = payload.get("subentity")
        bom.code = payload["code"]
        bom.name = payload["name"]
        bom.description = payload.get("description") or ""
        bom.finished_product_id = payload["finished_product"]
        bom.route_id = payload.get("route")
        if payload.get("route"):
            route = get_object_or_404(ManufacturingRoute, id=payload.get("route"), entity_id=bom.entity_id)
            bom.route_id = route.id
        else:
            bom.route_id = None
        bom.output_qty = payload["output_qty"]
        bom.output_uom_id = Product.objects.filter(id=payload["finished_product"]).values_list("base_uom_id", flat=True).first()
        bom.is_active = payload.get("is_active", True)
        bom.updated_by = request.user
        bom.save()
        bom.materials.all().delete()
        material_rows = []
        for idx, row in enumerate(payload["materials"], start=1):
            material_product = get_object_or_404(Product, id=row["material_product"], entity_id=bom.entity_id)
            material_rows.append(
                bom.materials.model(
                    bom=bom,
                    line_no=idx,
                    material_product=material_product,
                    qty=row["qty"],
                    uom=getattr(material_product, "base_uom", None),
                    waste_percent=row.get("waste_percent") or 0,
                    note=row.get("note") or "",
                )
            )
        if material_rows:
            bom.materials.model.objects.bulk_create(material_rows)
        bom.refresh_from_db()
        return Response(ManufacturingBOMResponseSerializer(bom).data)

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        bom = self.get_object()
        self.enforce_scope(request, entity_id=bom.entity_id, entityfinid_id=None, subentity_id=bom.subentity_id)
        self.assert_permission(request, bom.entity_id, "manufacturing.bom.delete")
        bom.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ManufacturingWorkOrderListCreateAPIView(_BaseManufacturingAPIView, generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        entity_id, subentity_id, _ = self._scope(self.request, require_entityfinid=False)
        self.assert_permission(self.request, entity_id, "manufacturing.workorder.view")
        qs = ManufacturingWorkOrder.objects.filter(entity_id=entity_id).select_related("bom", "bom__route").prefetch_related(
            "materials",
            "outputs",
            "additional_costs",
            "operations",
            "trace_links__input_product",
            "trace_links__output_product",
        )
        if subentity_id is None:
            qs = qs.filter(subentity_id__isnull=True)
        else:
            qs = qs.filter(subentity_id=subentity_id)
        return qs.order_by("-production_date", "-id")

    def get_serializer_class(self):
        if self.request.method.upper() == "GET":
            return ManufacturingWorkOrderListSerializer
        return ManufacturingWorkOrderWriteSerializer

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = ManufacturingWorkOrderListSerializer(queryset, many=True)
        return Response({"rows": serializer.data})

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        entity_id = payload["entity"]
        self.enforce_scope(request, entity_id=entity_id, entityfinid_id=payload.get("entityfinid"), subentity_id=payload.get("subentity"))
        self.assert_permission(request, entity_id, "manufacturing.workorder.create")
        result = ManufacturingWorkOrderService.create_work_order(payload=payload, user_id=request.user.id)
        return Response({"work_order": ManufacturingWorkOrderResponseSerializer(result.work_order).data}, status=status.HTTP_201_CREATED)


class ManufacturingWorkOrderDetailAPIView(_BaseManufacturingAPIView, generics.RetrieveUpdateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ManufacturingWorkOrderWriteSerializer

    def get_queryset(self):
        return ManufacturingWorkOrder.objects.select_related("bom", "bom__route", "source_location", "destination_location").prefetch_related(
            "materials__material_product",
            "outputs__finished_product",
            "additional_costs",
            "operations__route_step",
            "trace_links__input_product",
            "trace_links__output_product",
        )

    def retrieve(self, request, *args, **kwargs):
        work_order = self.get_object()
        self.enforce_scope(request, entity_id=work_order.entity_id, entityfinid_id=work_order.entityfin_id, subentity_id=work_order.subentity_id)
        self.assert_permission(request, work_order.entity_id, "manufacturing.workorder.view")
        return Response(ManufacturingWorkOrderResponseSerializer(work_order).data)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        work_order = self.get_object()
        self.enforce_scope(request, entity_id=work_order.entity_id, entityfinid_id=work_order.entityfin_id, subentity_id=work_order.subentity_id)
        self.assert_permission(request, work_order.entity_id, "manufacturing.workorder.update")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = ManufacturingWorkOrderService.update_work_order(
            work_order_id=work_order.id,
            payload=serializer.validated_data,
            user_id=request.user.id,
        )
        return Response({"work_order": ManufacturingWorkOrderResponseSerializer(result.work_order).data})


class ManufacturingWorkOrderPostAPIView(_BaseManufacturingAPIView):
    def post(self, request, pk: int):
        work_order = get_object_or_404(ManufacturingWorkOrder, pk=pk)
        self.enforce_scope(request, entity_id=work_order.entity_id, entityfinid_id=work_order.entityfin_id, subentity_id=work_order.subentity_id)
        self.assert_permission(request, work_order.entity_id, "manufacturing.workorder.post")
        result = ManufacturingWorkOrderService.post_work_order(work_order_id=pk, user_id=request.user.id)
        return Response({"work_order": ManufacturingWorkOrderResponseSerializer(result.work_order).data})


class ManufacturingWorkOrderOperationStartAPIView(_BaseManufacturingAPIView):
    def post(self, request, pk: int, operation_pk: int):
        work_order = get_object_or_404(ManufacturingWorkOrder, pk=pk)
        self.enforce_scope(request, entity_id=work_order.entity_id, entityfinid_id=work_order.entityfin_id, subentity_id=work_order.subentity_id)
        self.assert_permission(request, work_order.entity_id, "manufacturing.workorder.update")
        result = ManufacturingWorkOrderService.start_operation(work_order_id=pk, operation_id=operation_pk, user_id=request.user.id)
        return Response({"work_order": ManufacturingWorkOrderResponseSerializer(result.work_order).data})


class ManufacturingWorkOrderOperationCompleteAPIView(_BaseManufacturingAPIView):
    def post(self, request, pk: int, operation_pk: int):
        work_order = get_object_or_404(ManufacturingWorkOrder, pk=pk)
        self.enforce_scope(request, entity_id=work_order.entity_id, entityfinid_id=work_order.entityfin_id, subentity_id=work_order.subentity_id)
        self.assert_permission(request, work_order.entity_id, "manufacturing.workorder.update")
        serializer = ManufacturingOperationActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = ManufacturingWorkOrderService.complete_operation(
            work_order_id=pk,
            operation_id=operation_pk,
            payload=serializer.validated_data,
            user_id=request.user.id,
        )
        return Response({"work_order": ManufacturingWorkOrderResponseSerializer(result.work_order).data})


class ManufacturingWorkOrderOperationSkipAPIView(_BaseManufacturingAPIView):
    def post(self, request, pk: int, operation_pk: int):
        work_order = get_object_or_404(ManufacturingWorkOrder, pk=pk)
        self.enforce_scope(request, entity_id=work_order.entity_id, entityfinid_id=work_order.entityfin_id, subentity_id=work_order.subentity_id)
        self.assert_permission(request, work_order.entity_id, "manufacturing.workorder.update")
        serializer = ManufacturingOperationActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = ManufacturingWorkOrderService.skip_operation(
            work_order_id=pk,
            operation_id=operation_pk,
            payload=serializer.validated_data,
            user_id=request.user.id,
        )
        return Response({"work_order": ManufacturingWorkOrderResponseSerializer(result.work_order).data})


class ManufacturingWorkOrderUnpostAPIView(_BaseManufacturingAPIView):
    def post(self, request, pk: int):
        work_order = get_object_or_404(ManufacturingWorkOrder, pk=pk)
        self.enforce_scope(request, entity_id=work_order.entity_id, entityfinid_id=work_order.entityfin_id, subentity_id=work_order.subentity_id)
        self.assert_permission(request, work_order.entity_id, "manufacturing.workorder.unpost")
        result = ManufacturingWorkOrderService.unpost_work_order(
            work_order_id=pk,
            user_id=request.user.id,
            reason=request.data.get("reason"),
        )
        return Response({"work_order": ManufacturingWorkOrderResponseSerializer(result.work_order).data})


class ManufacturingWorkOrderCancelAPIView(_BaseManufacturingAPIView):
    def post(self, request, pk: int):
        work_order = get_object_or_404(ManufacturingWorkOrder, pk=pk)
        self.enforce_scope(request, entity_id=work_order.entity_id, entityfinid_id=work_order.entityfin_id, subentity_id=work_order.subentity_id)
        self.assert_permission(request, work_order.entity_id, "manufacturing.workorder.cancel")
        result = ManufacturingWorkOrderService.cancel_work_order(
            work_order_id=pk,
            user_id=request.user.id,
            reason=request.data.get("reason"),
        )
        return Response({"work_order": ManufacturingWorkOrderResponseSerializer(result.work_order).data})


class ManufacturingBOMFormMetaAPIView(_BaseManufacturingAPIView):
    def get(self, request):
        entity_id, subentity_id, _ = self._scope(request, require_entityfinid=False)
        self.assert_permission(request, entity_id, "manufacturing.bom.view")
        products = Product.objects.filter(entity_id=entity_id, isactive=True, is_service=False).order_by("productname", "id")
        routes = ManufacturingRoute.objects.filter(entity_id=entity_id, is_active=True)
        if subentity_id is not None:
            boms = ManufacturingBOM.objects.filter(entity_id=entity_id, subentity_id=subentity_id, is_active=True).order_by("code", "id")
            routes = routes.filter(subentity_id=subentity_id)
        else:
            boms = ManufacturingBOM.objects.filter(entity_id=entity_id, subentity_id__isnull=True, is_active=True).order_by("code", "id")
            routes = routes.filter(subentity_id__isnull=True)
        return Response({
            "products": [
                {
                    "id": product.id,
                    "productname": product.productname,
                    "sku": product.sku,
                    "base_uom_id": product.base_uom_id,
                    "base_uom_code": getattr(product.base_uom, "code", None),
                    "is_batch_managed": bool(getattr(product, "is_batch_managed", False)),
                    "is_expiry_tracked": bool(getattr(product, "is_expiry_tracked", False)),
                }
                for product in products.select_related("base_uom")
            ],
            "boms": [{"id": bom.id, "code": bom.code, "name": bom.name} for bom in boms],
            "routes": [{"id": route.id, "code": route.code, "name": route.name} for route in routes.order_by("code", "id")],
        })


class ManufacturingWorkOrderFormMetaAPIView(_BaseManufacturingAPIView):
    def get(self, request):
        entity_id, subentity_id, entityfinid_id = self._scope(request, require_entityfinid=False)
        self.assert_permission(request, entity_id, "manufacturing.workorder.view")
        settings_obj, _ = ManufacturingSettings.objects.get_or_create(entity_id=entity_id, subentity_id=subentity_id)
        products = Product.objects.filter(entity_id=entity_id, isactive=True, is_service=False).select_related("base_uom").order_by("productname", "id")
        boms = ManufacturingBOM.objects.filter(entity_id=entity_id, is_active=True).select_related("finished_product", "route")
        routes = ManufacturingRoute.objects.filter(entity_id=entity_id, is_active=True)
        if subentity_id is None:
            boms = boms.filter(subentity_id__isnull=True)
            routes = routes.filter(subentity_id__isnull=True)
            godowns = Godown.objects.filter(entity_id=entity_id, subentity_id__isnull=True, is_active=True).order_by("name", "id")
        else:
            boms = boms.filter(subentity_id=subentity_id)
            routes = routes.filter(subentity_id=subentity_id)
            godowns = Godown.objects.filter(entity_id=entity_id, subentity_id=subentity_id, is_active=True).order_by("name", "id")
        return Response({
            "products": [
                {
                    "id": product.id,
                    "productname": product.productname,
                    "sku": product.sku,
                    "base_uom_id": product.base_uom_id,
                    "base_uom_code": getattr(product.base_uom, "code", None),
                    "is_batch_managed": bool(getattr(product, "is_batch_managed", False)),
                    "is_expiry_tracked": bool(getattr(product, "is_expiry_tracked", False)),
                }
                for product in products
            ],
            "boms": [
                {
                    "id": bom.id,
                    "code": bom.code,
                    "name": bom.name,
                    "finished_product_id": bom.finished_product_id,
                    "finished_product_name": getattr(bom.finished_product, "productname", ""),
                    "route_id": bom.route_id,
                    "route_code": getattr(bom.route, "code", None),
                    "output_qty": bom.output_qty,
                }
                for bom in boms.order_by("code", "id")
            ],
            "routes": [
                {
                    "id": route.id,
                    "code": route.code,
                    "name": route.name,
                    "step_count": route.steps.count(),
                }
                for route in routes.prefetch_related("steps").order_by("code", "id")
            ],
            "godowns": [
                {
                    "id": godown.id,
                    "name": godown.name,
                    "code": godown.code,
                    "display_name": getattr(godown, "display_name", godown.name),
                }
                for godown in godowns
            ],
            "settings": ManufacturingSettingsAPIView._settings_payload(settings_obj),
            "current_doc_numbers": {
                "manufacturing_work_order": settings_obj.default_doc_code_work_order if not entityfinid_id else settings_obj.default_doc_code_work_order
            },
        })
