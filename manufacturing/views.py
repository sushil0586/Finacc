from __future__ import annotations

from typing import Any, Optional

from django.db import transaction
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_date
from rest_framework import generics, permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import Product
from core.entitlements import ScopedEntitlementMixin
from entity.models import Godown
from numbering.models import DocumentNumberSeries
from numbering.services import ensure_document_type, ensure_series, validate_unique_series_pattern
from posting.models import EntityStaticAccountMap
from rbac.services import EffectivePermissionService

from .models import (
    DEFAULT_MANUFACTURING_ADDITIONAL_COST_TYPES,
    ManufacturingBOM,
    ManufacturingRoute,
    ManufacturingSettings,
    ManufacturingWorkOrder,
    ManufacturingWorkOrderStatus,
    ManufacturingWorkOrderAdditionalCost,
    ManufacturingWorkOrderMaterial,
    ManufacturingWorkOrderOperation,
    ManufacturingWorkOrderOutput,
)
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
    {"name": "output_valuation_basis", "label": "Output Valuation Basis", "type": "choice", "group": "accounting_controls", "choices": _choice_payload([("actual_cost", "Actual Cost"), ("standard_cost", "Standard Cost With Variances")])},
    {"name": "capitalized_additional_cost_types", "label": "Capitalized Additional Cost Types", "type": "multi_choice", "group": "accounting_controls", "choices": _choice_payload([(value, value.title()) for value in DEFAULT_MANUFACTURING_ADDITIONAL_COST_TYPES])},
]

NUMBERING_SERIES_SCHEMA = [
    {"name": "doc_code", "label": "Series Code", "type": "string"},
    {"name": "prefix", "label": "Prefix", "type": "string"},
    {"name": "suffix", "label": "Suffix", "type": "string"},
    {"name": "starting_number", "label": "Starting Number", "type": "integer"},
    {"name": "current_number", "label": "Next Number", "type": "integer"},
    {"name": "number_padding", "label": "Padding", "type": "integer"},
    {"name": "separator", "label": "Separator", "type": "string"},
    {"name": "reset_frequency", "label": "Reset Frequency", "type": "choice", "choices": _choice_payload(DocumentNumberSeries.RESET_CHOICES)},
    {"name": "include_year", "label": "Include Year", "type": "boolean"},
    {"name": "include_month", "label": "Include Month", "type": "boolean"},
    {"name": "custom_format", "label": "Custom Format", "type": "string"},
    {"name": "is_active", "label": "Active", "type": "boolean"},
]


def _parse_optional_date(raw_value: Any, field_name: str):
    if raw_value in (None, "", "null", "None"):
        return None
    if hasattr(raw_value, "year") and hasattr(raw_value, "month") and hasattr(raw_value, "day"):
        return raw_value
    parsed = parse_date(str(raw_value))
    if parsed is None:
        raise ValidationError({field_name: f"{field_name} must use YYYY-MM-DD format."})
    return parsed


def _parse_positive_int(raw_value: Any, field_name: str, *, default: int, minimum: int = 1, maximum: Optional[int] = None) -> int:
    if raw_value in (None, "", "null", "None"):
        return default
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        raise ValidationError({field_name: f"{field_name} must be an integer."})
    if value < minimum:
        raise ValidationError({field_name: f"{field_name} must be at least {minimum}."})
    if maximum is not None and value > maximum:
        raise ValidationError({field_name: f"{field_name} must be at most {maximum}."})
    return value


def _yield_variance_value_from_row(row: dict[str, Any]) -> float:
    standard_material_cost = row.get("standard_material_cost_snapshot") or 0
    actual_output_qty = row.get("actual_output_qty_snapshot") or 0
    standard_unit_cost = row.get("standard_unit_cost_snapshot") or 0
    actual_recovery_value = row.get("actual_recovery_value_snapshot") or 0
    return float((standard_material_cost - ((actual_output_qty * standard_unit_cost) + actual_recovery_value)) or 0)


def _manufacturing_accounting_payload(settings_obj: ManufacturingSettings) -> dict[str, Any]:
    valuation_basis = ManufacturingWorkOrderService._output_valuation_basis(settings_obj)
    uses_standard_cost = valuation_basis == ManufacturingWorkOrderService.OUTPUT_VALUATION_STANDARD_COST
    return {
        "output_valuation_basis": valuation_basis,
        "output_valuation_label": "Standard Cost With Variances" if uses_standard_cost else "Actual Cost",
        "uses_variance_ledgers": uses_standard_cost,
        "required_static_account_codes": list(
            ManufacturingWorkOrderService._required_posting_codes(settings_obj=settings_obj)
        ),
    }


def _manufacturing_work_orders_queryset(
    *,
    entity_id: int,
    subentity_id: Optional[int],
    entityfinid_id: Optional[int],
    from_date=None,
    to_date=None,
):
    qs = ManufacturingWorkOrder.objects.filter(entity_id=entity_id)
    if entityfinid_id:
        qs = qs.filter(entityfin_id=entityfinid_id)
    if subentity_id is None:
        qs = qs.filter(subentity_id__isnull=True)
    else:
        qs = qs.filter(subentity_id=subentity_id)
    if from_date:
        qs = qs.filter(production_date__gte=from_date)
    if to_date:
        qs = qs.filter(production_date__lte=to_date)
    return qs


def _subentity_scope_q(
    subentity_id: Optional[int],
    *,
    include_shared_when_scoped: bool = False,
) -> Q:
    if subentity_id is None:
        return Q(subentity_id__isnull=True)
    if include_shared_when_scoped:
        return Q(subentity_id=subentity_id) | Q(subentity_id__isnull=True)
    return Q(subentity_id=subentity_id)


def _assert_field_is_unchanged(*, field_name: str, current_value: Any, payload_value: Any, label: str) -> None:
    if current_value != payload_value:
        raise ValidationError({field_name: f"{label} cannot be changed after creation."})


def _get_scoped_route_for_bom(*, entity_id: int, subentity_id: Optional[int], route_id: int) -> ManufacturingRoute:
    route = (
        ManufacturingRoute.objects
        .filter(entity_id=entity_id, id=route_id)
        .filter(_subentity_scope_q(subentity_id, include_shared_when_scoped=True))
        .first()
    )
    if route is None:
        raise ValidationError({"route": "Selected route is not available in this manufacturing scope."})
    return route


def _assert_master_visible_in_context(*, record_subentity_id: Optional[int], context_subentity_id: Optional[int], label: str) -> None:
    if context_subentity_id is None:
        return
    if record_subentity_id in (None, context_subentity_id):
        return
    raise PermissionDenied(f"{label} is not available in the current branch scope.")


def _assert_master_writable_in_context(*, record_subentity_id: Optional[int], context_subentity_id: Optional[int], label: str) -> None:
    _assert_master_visible_in_context(
        record_subentity_id=record_subentity_id,
        context_subentity_id=context_subentity_id,
        label=label,
    )
    if context_subentity_id is not None and record_subentity_id is None:
        raise PermissionDenied(f"Shared root {label.lower()}s are read-only from branch scope.")

EDITABLE_SETTINGS_FIELDS = {
    "default_doc_code_work_order",
    "default_workflow_action",
    "auto_explode_materials_from_bom",
    "allow_manual_material_override",
    "require_batch_for_batch_managed_items",
    "require_expiry_when_expiry_tracked",
    "block_negative_stock",
    "default_output_batch_mode",
    "output_valuation_basis",
    "capitalized_additional_cost_types",
}


class _BaseManufacturingAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_permission_codes(self, request, entity_id):
        return EffectivePermissionService.permission_codes_for_user(request.user, entity_id)

    def assert_permission(self, request, entity_id: int, permission_code: str):
        if permission_code not in self.get_permission_codes(request, entity_id):
            raise PermissionDenied(f"Missing permission: {permission_code}")

    def assert_any_permission(self, request, entity_id: int, permission_codes: list[str] | tuple[str, ...]):
        effective_codes = self.get_permission_codes(request, entity_id)
        if any(permission_code in effective_codes for permission_code in permission_codes):
            return
        raise PermissionDenied(f"Missing permission. Need one of: {', '.join(permission_codes)}")

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

    def _scope_with_dates(self, request, *, require_entityfinid: bool = False):
        entity_id, subentity_id, entityfinid_id = self._scope(request, require_entityfinid=require_entityfinid)
        from_date = _parse_optional_date(request.query_params.get("from_date"), "from_date")
        to_date = _parse_optional_date(request.query_params.get("to_date"), "to_date")
        if from_date and to_date and from_date > to_date:
            raise ValidationError({"to_date": "to_date cannot be earlier than from_date."})
        return entity_id, subentity_id, entityfinid_id, from_date, to_date


class ManufacturingSettingsAPIView(_BaseManufacturingAPIView):
    SERIES_KEY = "manufacturing_work_order"
    DOC_KEY = "MANUFACTURING_WORK_ORDER"
    DOC_LABEL = "Manufacturing Work Order"

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
            doc_key=ManufacturingSettingsAPIView.DOC_KEY,
            name=ManufacturingSettingsAPIView.DOC_LABEL,
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
            "series_key": self.SERIES_KEY,
            "label": self.DOC_LABEL,
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

    def _update_numbering_series(self, rows: list[dict], *, entity_id: int, entityfinid_id: int, subentity_id: Optional[int], settings_obj: ManufacturingSettings, user_id: Optional[int]) -> None:
        row = next((item for item in rows if isinstance(item, dict) and item.get("series_key") == self.SERIES_KEY), None)
        if not row:
            return

        doc_code = str(row.get("doc_code") or settings_obj.default_doc_code_work_order or "MWO").strip()
        if not doc_code:
            raise ValidationError({"numbering_series": "doc_code is required for manufacturing_work_order."})

        settings_obj.default_doc_code_work_order = doc_code
        doc_type = self._ensure_doc_type(settings_obj)
        series, _ = ensure_series(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            doc_type_id=doc_type.id,
            doc_code=doc_code,
            prefix=(row.get("prefix") if row.get("prefix") is not None else doc_code),
            start=int(row.get("starting_number") or 1),
            padding=int(row.get("number_padding") or 0),
            reset=(row.get("reset_frequency") or "none"),
            include_year=bool(row.get("include_year", False)),
            include_month=bool(row.get("include_month", False)),
        )
        series.prefix = str(row.get("prefix") or "")
        series.suffix = str(row.get("suffix") or "")
        series.starting_number = int(row.get("starting_number") or 1)
        series.current_number = int(row.get("current_number") or series.starting_number)
        series.number_padding = int(row.get("number_padding") or 0)
        series.separator = str(row.get("separator") or "-")
        series.reset_frequency = str(row.get("reset_frequency") or "none")
        series.include_year = bool(row.get("include_year", False))
        series.include_month = bool(row.get("include_month", False))
        series.custom_format = str(row.get("custom_format") or "")
        series.is_active = bool(row.get("is_active", True))
        if user_id and not series.created_by_id:
            series.created_by_id = user_id
        validate_unique_series_pattern(series=series, doc_label=self.DOC_LABEL)
        series.save()
        settings_obj.save()

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
        if "output_valuation_basis" in settings_updates and settings_updates["output_valuation_basis"] not in {
            ManufacturingWorkOrderService.OUTPUT_VALUATION_ACTUAL_COST,
            ManufacturingWorkOrderService.OUTPUT_VALUATION_STANDARD_COST,
        }:
            raise ValidationError({"output_valuation_basis": "Allowed values: actual_cost, standard_cost."})
        if "capitalized_additional_cost_types" in settings_updates:
            raw_value = settings_updates["capitalized_additional_cost_types"]
            if not isinstance(raw_value, list):
                raise ValidationError({"capitalized_additional_cost_types": "Provide capitalized additional cost types as a list."})
            invalid = [value for value in raw_value if str(value or "").strip().upper() not in DEFAULT_MANUFACTURING_ADDITIONAL_COST_TYPES]
            if invalid:
                raise ValidationError({"capitalized_additional_cost_types": f"Invalid cost types: {', '.join(map(str, invalid))}."})
            settings_updates["capitalized_additional_cost_types"] = [str(value).strip().upper() for value in raw_value]

    def get(self, request):
        entity_id, subentity_id, entityfinid_id = self._scope(request, require_entityfinid=False)
        self.assert_permission(request, entity_id, "manufacturing.settings.view")
        settings_obj = self._get_settings(entity_id=entity_id, subentity_id=subentity_id)
        return Response({
            "settings": self._settings_payload(settings_obj),
            "accounting": _manufacturing_accounting_payload(settings_obj),
            "numbering_series": self._series_payload(entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id, settings_obj=settings_obj) if entityfinid_id else [],
            "numbering_series_schema": NUMBERING_SERIES_SCHEMA,
            "capabilities": {"has_numbering_management": bool(entityfinid_id)},
        })

    @transaction.atomic
    def patch(self, request):
        entity_id = self._parse_int(request.data.get("entity"), "entity", required=True)
        subentity_id = self._parse_int(request.data.get("subentity"), "subentity_id", required=False)
        entityfinid_id = self._parse_int(request.data.get("entityfinid"), "entityfinid", required=False)
        self.enforce_scope(request, entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id)
        self.assert_permission(request, entity_id, "manufacturing.settings.update")
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

        if "numbering_series" in request.data:
            rows = request.data.get("numbering_series") or []
            if not entityfinid_id:
                raise ValidationError({"entityfinid": "entityfinid is required when updating numbering_series."})
            if not isinstance(rows, list):
                raise ValidationError({"numbering_series": "Provide a list of numbering series rows."})
            self._update_numbering_series(
                rows,
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                subentity_id=subentity_id,
                settings_obj=settings_obj,
                user_id=getattr(request.user, "id", None),
            )

        return Response({
            "settings": self._settings_payload(settings_obj),
            "numbering_series": self._series_payload(entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id, settings_obj=settings_obj) if entityfinid_id else [],
            "numbering_series_schema": NUMBERING_SERIES_SCHEMA,
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
        self.assert_any_permission(self.request, entity_id, ("manufacturing.route.view", "manufacturing.bom.view"))
        qs = ManufacturingRoute.objects.filter(entity_id=entity_id).prefetch_related("steps")
        qs = qs.filter(_subentity_scope_q(subentity_id, include_shared_when_scoped=True))
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
        self.assert_any_permission(request, entity_id, ("manufacturing.route.create", "manufacturing.bom.create"))

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
        context_subentity_id = self._parse_int(request.query_params.get("subentity"), "subentity_id", required=False)
        _assert_master_visible_in_context(
            record_subentity_id=route.subentity_id,
            context_subentity_id=context_subentity_id,
            label="Route",
        )
        self.enforce_scope(request, entity_id=route.entity_id, entityfinid_id=None, subentity_id=route.subentity_id)
        self.assert_any_permission(request, route.entity_id, ("manufacturing.route.view", "manufacturing.bom.view"))
        return Response(ManufacturingRouteResponseSerializer(route).data)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        route = self.get_object()
        context_subentity_id = self._parse_int(request.query_params.get("subentity"), "subentity_id", required=False)
        _assert_master_writable_in_context(
            record_subentity_id=route.subentity_id,
            context_subentity_id=context_subentity_id,
            label="Route",
        )
        self.enforce_scope(request, entity_id=route.entity_id, entityfinid_id=None, subentity_id=route.subentity_id)
        self.assert_any_permission(request, route.entity_id, ("manufacturing.route.update", "manufacturing.bom.update"))
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        _assert_field_is_unchanged(field_name="entity", current_value=route.entity_id, payload_value=payload["entity"], label="Entity")
        _assert_field_is_unchanged(field_name="subentity", current_value=route.subentity_id, payload_value=payload.get("subentity"), label="Route scope")
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
        context_subentity_id = self._parse_int(request.query_params.get("subentity"), "subentity_id", required=False)
        _assert_master_writable_in_context(
            record_subentity_id=route.subentity_id,
            context_subentity_id=context_subentity_id,
            label="Route",
        )
        self.enforce_scope(request, entity_id=route.entity_id, entityfinid_id=None, subentity_id=route.subentity_id)
        self.assert_any_permission(request, route.entity_id, ("manufacturing.route.delete", "manufacturing.bom.delete"))
        route.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ManufacturingBOMListCreateAPIView(_BaseManufacturingAPIView, generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        entity_id, subentity_id, _ = self._scope(self.request, require_entityfinid=False)
        self.assert_permission(self.request, entity_id, "manufacturing.bom.view")
        qs = ManufacturingBOM.objects.filter(entity_id=entity_id).select_related("finished_product", "output_uom", "route").prefetch_related("materials")
        qs = qs.filter(_subentity_scope_q(subentity_id, include_shared_when_scoped=True))
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
            route_id=_get_scoped_route_for_bom(entity_id=entity_id, subentity_id=payload.get("subentity"), route_id=payload.get("route")).id if payload.get("route") else None,
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
        context_subentity_id = self._parse_int(request.query_params.get("subentity"), "subentity_id", required=False)
        _assert_master_visible_in_context(
            record_subentity_id=bom.subentity_id,
            context_subentity_id=context_subentity_id,
            label="BOM",
        )
        self.enforce_scope(request, entity_id=bom.entity_id, entityfinid_id=None, subentity_id=bom.subentity_id)
        self.assert_permission(request, bom.entity_id, "manufacturing.bom.view")
        return Response(ManufacturingBOMResponseSerializer(bom).data)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        bom = self.get_object()
        context_subentity_id = self._parse_int(request.query_params.get("subentity"), "subentity_id", required=False)
        _assert_master_writable_in_context(
            record_subentity_id=bom.subentity_id,
            context_subentity_id=context_subentity_id,
            label="BOM",
        )
        self.enforce_scope(request, entity_id=bom.entity_id, entityfinid_id=None, subentity_id=bom.subentity_id)
        self.assert_permission(request, bom.entity_id, "manufacturing.bom.update")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        _assert_field_is_unchanged(field_name="entity", current_value=bom.entity_id, payload_value=payload["entity"], label="Entity")
        _assert_field_is_unchanged(field_name="subentity", current_value=bom.subentity_id, payload_value=payload.get("subentity"), label="BOM scope")
        bom.subentity_id = payload.get("subentity")
        bom.code = payload["code"]
        bom.name = payload["name"]
        bom.description = payload.get("description") or ""
        bom.finished_product_id = payload["finished_product"]
        bom.route_id = payload.get("route")
        if payload.get("route"):
            route = _get_scoped_route_for_bom(entity_id=bom.entity_id, subentity_id=bom.subentity_id, route_id=payload.get("route"))
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
        context_subentity_id = self._parse_int(request.query_params.get("subentity"), "subentity_id", required=False)
        _assert_master_writable_in_context(
            record_subentity_id=bom.subentity_id,
            context_subentity_id=context_subentity_id,
            label="BOM",
        )
        self.enforce_scope(request, entity_id=bom.entity_id, entityfinid_id=None, subentity_id=bom.subentity_id)
        self.assert_permission(request, bom.entity_id, "manufacturing.bom.delete")
        bom.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ManufacturingWorkOrderListCreateAPIView(_BaseManufacturingAPIView, generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        entity_id, subentity_id, entityfinid_id = self._scope(self.request, require_entityfinid=False)
        self.assert_permission(self.request, entity_id, "manufacturing.workorder.view")
        qs = _manufacturing_work_orders_queryset(
            entity_id=entity_id,
            subentity_id=subentity_id,
            entityfinid_id=entityfinid_id,
        ).select_related("bom", "bom__route").prefetch_related(
            "materials",
            "outputs",
            "additional_costs",
            "operations",
            "trace_links__input_product",
            "trace_links__output_product",
        )
        status_filter = str(self.request.query_params.get("status") or "").strip().upper()
        if status_filter:
            valid_statuses = {choice[0] for choice in ManufacturingWorkOrderStatus.choices}
            if status_filter not in valid_statuses:
                raise ValidationError({"status": f"Invalid status. Allowed values: {', '.join(sorted(valid_statuses))}."})
            qs = qs.filter(status=status_filter)

        search_term = str(self.request.query_params.get("search") or "").strip()
        if search_term:
            qs = qs.filter(
                Q(work_order_no__icontains=search_term)
                | Q(reference_no__icontains=search_term)
                | Q(bom__code__icontains=search_term)
                | Q(bom__name__icontains=search_term)
                | Q(status__icontains=search_term)
            )

        from_date = _parse_optional_date(self.request.query_params.get("from_date"), "from_date")
        to_date = _parse_optional_date(self.request.query_params.get("to_date"), "to_date")
        if from_date and to_date and from_date > to_date:
            raise ValidationError({"to_date": "to_date cannot be earlier than from_date."})
        if from_date:
            qs = qs.filter(production_date__gte=from_date)
        if to_date:
            qs = qs.filter(production_date__lte=to_date)
        return qs.order_by("-production_date", "-id")

    def get_serializer_class(self):
        if self.request.method.upper() == "GET":
            return ManufacturingWorkOrderListSerializer
        return ManufacturingWorkOrderWriteSerializer

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = _parse_positive_int(request.query_params.get("page"), "page", default=1)
        page_size = _parse_positive_int(request.query_params.get("page_size"), "page_size", default=25, maximum=100)
        total_count = queryset.count()
        start = (page - 1) * page_size
        end = start + page_size
        serializer = ManufacturingWorkOrderListSerializer(queryset[start:end], many=True)
        return Response({
            "rows": serializer.data,
            "total_count": total_count,
            "page": page,
            "page_size": page_size,
            "has_previous": page > 1,
            "has_next": end < total_count,
        })

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
        payload = serializer.validated_data
        _assert_field_is_unchanged(field_name="entity", current_value=work_order.entity_id, payload_value=payload["entity"], label="Entity")
        _assert_field_is_unchanged(field_name="entityfinid", current_value=work_order.entityfin_id, payload_value=payload.get("entityfinid"), label="Financial year scope")
        _assert_field_is_unchanged(field_name="subentity", current_value=work_order.subentity_id, payload_value=payload.get("subentity"), label="Work order scope")
        result = ManufacturingWorkOrderService.update_work_order(
            work_order_id=work_order.id,
            payload=payload,
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
        self.assert_permission(request, work_order.entity_id, "manufacturing.workorder.operate")
        result = ManufacturingWorkOrderService.start_operation(work_order_id=pk, operation_id=operation_pk, user_id=request.user.id)
        return Response({"work_order": ManufacturingWorkOrderResponseSerializer(result.work_order).data})


class ManufacturingWorkOrderOperationCompleteAPIView(_BaseManufacturingAPIView):
    def post(self, request, pk: int, operation_pk: int):
        work_order = get_object_or_404(ManufacturingWorkOrder, pk=pk)
        self.enforce_scope(request, entity_id=work_order.entity_id, entityfinid_id=work_order.entityfin_id, subentity_id=work_order.subentity_id)
        self.assert_permission(request, work_order.entity_id, "manufacturing.workorder.operate")
        serializer = ManufacturingOperationActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = ManufacturingWorkOrderService.complete_operation(
            work_order_id=pk,
            operation_id=operation_pk,
            payload=serializer.validated_data,
            user_id=request.user.id,
        )
        return Response({"work_order": ManufacturingWorkOrderResponseSerializer(result.work_order).data})


class ManufacturingWorkOrderOperationApproveAPIView(_BaseManufacturingAPIView):
    def post(self, request, pk: int, operation_pk: int):
        work_order = get_object_or_404(ManufacturingWorkOrder, pk=pk)
        self.enforce_scope(request, entity_id=work_order.entity_id, entityfinid_id=work_order.entityfin_id, subentity_id=work_order.subentity_id)
        self.assert_permission(request, work_order.entity_id, "manufacturing.workorder.qc_approve")
        serializer = ManufacturingOperationActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = ManufacturingWorkOrderService.approve_operation(
            work_order_id=pk,
            operation_id=operation_pk,
            payload=serializer.validated_data,
            user_id=request.user.id,
        )
        return Response({"work_order": ManufacturingWorkOrderResponseSerializer(result.work_order).data})


class ManufacturingWorkOrderOperationRejectAPIView(_BaseManufacturingAPIView):
    def post(self, request, pk: int, operation_pk: int):
        work_order = get_object_or_404(ManufacturingWorkOrder, pk=pk)
        self.enforce_scope(request, entity_id=work_order.entity_id, entityfinid_id=work_order.entityfin_id, subentity_id=work_order.subentity_id)
        self.assert_permission(request, work_order.entity_id, "manufacturing.workorder.qc_approve")
        serializer = ManufacturingOperationActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = ManufacturingWorkOrderService.reject_operation(
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
        self.assert_permission(request, work_order.entity_id, "manufacturing.workorder.operate")
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


class ManufacturingSummaryAPIView(_BaseManufacturingAPIView):
    def get(self, request):
        entity_id, subentity_id, entityfinid_id, from_date, to_date = self._scope_with_dates(request, require_entityfinid=False)
        self.assert_permission(request, entity_id, "manufacturing.workorder.view")
        settings_obj, _ = ManufacturingSettings.objects.get_or_create(entity_id=entity_id, subentity_id=subentity_id)
        work_orders = _manufacturing_work_orders_queryset(
            entity_id=entity_id,
            subentity_id=subentity_id,
            entityfinid_id=entityfinid_id,
            from_date=from_date,
            to_date=to_date,
        )

        recent_rows = list(
            work_orders.select_related("bom")
            .order_by("-production_date", "-id")[:8]
            .values(
                "id",
                "work_order_no",
                "production_date",
                "status",
                "reference_no",
                "posting_entry_id",
                "net_production_cost_snapshot",
                "actual_output_qty_snapshot",
                "bom__code",
                "bom__name",
            )
        )

        overview_counts = {
            row["status"]: row["count"]
            for row in work_orders.values("status").annotate(count=Count("id"))
        }
        operations = (
            ManufacturingWorkOrderOperation.objects
            .filter(work_order__in=work_orders)
            .values("status")
            .annotate(count=Count("id"))
        )
        operation_counts = {row["status"]: row["count"] for row in operations}

        line_value_expr = ExpressionWrapper(
            F("actual_qty") * F("unit_cost"),
            output_field=DecimalField(max_digits=22, decimal_places=4),
        )
        top_materials = list(
            ManufacturingWorkOrderMaterial.objects
            .filter(work_order__in=work_orders)
            .values("material_product_id", "material_product__productname", "material_product__sku", "uom__code")
            .annotate(
                work_order_count=Count("work_order", distinct=True),
                total_qty=Sum("actual_qty"),
                total_value=Sum(line_value_expr),
            )
            .order_by("-total_value", "-total_qty", "material_product__productname")[:8]
        )
        top_outputs = list(
            ManufacturingWorkOrderOutput.objects
            .filter(work_order__in=work_orders)
            .values("finished_product_id", "finished_product__productname", "finished_product__sku", "uom__code", "output_type")
            .annotate(
                work_order_count=Count("work_order", distinct=True),
                total_qty=Sum("actual_qty"),
                total_value=Sum(line_value_expr),
            )
            .order_by("-total_value", "-total_qty", "finished_product__productname")[:8]
        )
        total_additional_cost = (
            ManufacturingWorkOrderAdditionalCost.objects
            .filter(work_order__in=work_orders)
            .aggregate(total=Sum("amount"))
            .get("total")
        ) or 0

        setup_codes = list(ManufacturingWorkOrderService._required_posting_codes(settings_obj=settings_obj))
        mapping_rows = EntityStaticAccountMap.objects.filter(
            entity_id=entity_id,
            is_active=True,
            static_account__code__in=setup_codes,
        ).select_related("static_account", "ledger", "account")
        setup_map = {
            row.static_account.code: row
            for row in mapping_rows
            if row.static_account_id
        }
        setup_rows = []
        missing_codes: list[str] = []
        for code in setup_codes:
            mapping = setup_map.get(code)
            if not mapping or not mapping.account_id:
                missing_codes.append(code)
            setup_rows.append(
                {
                    "code": code,
                    "label": ManufacturingWorkOrderService.MANUFACTURING_POSTING_LABELS.get(code, code),
                    "is_required": True,
                    "is_mapped": bool(mapping and mapping.account_id),
                    "account_id": mapping.account_id if mapping else None,
                    "account_name": getattr(mapping.account, "accountname", None) if mapping and mapping.account_id else None,
                    "ledger_id": mapping.ledger_id if mapping else None,
                    "ledger_name": getattr(mapping.ledger, "ledgername", None) if mapping and mapping.ledger_id else None,
                }
            )

        payload = {
            "scope": {
                "entity": entity_id,
                "entityfinid": entityfinid_id,
                "subentity": subentity_id,
                "from_date": from_date,
                "to_date": to_date,
            },
            "accounting": _manufacturing_accounting_payload(settings_obj),
            "overview": {
                "total_work_orders": int(work_orders.count()),
                "draft_count": int(overview_counts.get("DRAFT", 0)),
                "posted_count": int(overview_counts.get("POSTED", 0)),
                "cancelled_count": int(overview_counts.get("CANCELLED", 0)),
                "awaiting_qc_count": int(operation_counts.get("AWAITING_QC", 0)),
                "qc_rejected_count": int(operation_counts.get("QC_REJECTED", 0)),
                "total_output_qty": work_orders.aggregate(total=Sum("actual_output_qty_snapshot")).get("total") or 0,
                "total_net_cost": work_orders.aggregate(total=Sum("net_production_cost_snapshot")).get("total") or 0,
                "total_additional_cost": total_additional_cost,
                "total_material_variance": work_orders.aggregate(total=Sum("material_variance_value_snapshot")).get("total") or 0,
                "total_yield_variance_value": sum((_yield_variance_value_from_row(row) for row in work_orders.values(
                    "standard_material_cost_snapshot",
                    "actual_output_qty_snapshot",
                    "standard_unit_cost_snapshot",
                    "actual_recovery_value_snapshot",
                )), 0),
            },
            "setup": {
                "is_ready": not missing_codes,
                "mapped_count": len(setup_codes) - len(missing_codes),
                "required_count": len(setup_codes),
                "missing_codes": missing_codes,
                "rows": setup_rows,
            },
            "recent_work_orders": [
                {
                    "id": row["id"],
                    "work_order_no": row["work_order_no"],
                    "production_date": row["production_date"],
                    "status": row["status"],
                    "reference_no": row["reference_no"],
                    "posting_entry_id": row["posting_entry_id"],
                    "net_production_cost": row["net_production_cost_snapshot"],
                    "actual_output_qty": row["actual_output_qty_snapshot"],
                    "bom_code": row["bom__code"],
                    "bom_name": row["bom__name"],
                }
                for row in recent_rows
            ],
            "top_materials": [
                {
                    "product_id": row["material_product_id"],
                    "product_name": row["material_product__productname"],
                    "sku": row["material_product__sku"],
                    "uom_name": row["uom__code"],
                    "work_order_count": row["work_order_count"],
                    "total_qty": row["total_qty"] or 0,
                    "total_value": row["total_value"] or 0,
                }
                for row in top_materials
            ],
            "top_outputs": [
                {
                    "product_id": row["finished_product_id"],
                    "product_name": row["finished_product__productname"],
                    "sku": row["finished_product__sku"],
                    "uom_name": row["uom__code"],
                    "output_type": row["output_type"],
                    "work_order_count": row["work_order_count"],
                    "total_qty": row["total_qty"] or 0,
                    "total_value": row["total_value"] or 0,
                }
                for row in top_outputs
            ],
        }
        return Response(payload)


class ManufacturingMaterialConsumptionAPIView(_BaseManufacturingAPIView):
    def get(self, request):
        entity_id, subentity_id, entityfinid_id, from_date, to_date = self._scope_with_dates(request, require_entityfinid=False)
        self.assert_permission(request, entity_id, "manufacturing.workorder.view")
        settings_obj, _ = ManufacturingSettings.objects.get_or_create(entity_id=entity_id, subentity_id=subentity_id)
        work_orders = _manufacturing_work_orders_queryset(
            entity_id=entity_id,
            subentity_id=subentity_id,
            entityfinid_id=entityfinid_id,
            from_date=from_date,
            to_date=to_date,
        )
        line_value_expr = ExpressionWrapper(
            F("actual_qty") * F("unit_cost"),
            output_field=DecimalField(max_digits=22, decimal_places=4),
        )
        rows = list(
            ManufacturingWorkOrderMaterial.objects
            .filter(work_order__in=work_orders)
            .select_related("work_order", "material_product", "uom")
            .annotate(line_value=line_value_expr)
            .order_by("-work_order__production_date", "-work_order_id", "line_no")
            .values(
                "work_order_id",
                "work_order__work_order_no",
                "work_order__production_date",
                "work_order__status",
                "work_order__posting_entry_id",
                "line_no",
                "material_product_id",
                "material_product__productname",
                "material_product__sku",
                "uom__code",
                "required_qty",
                "actual_qty",
                "waste_qty",
                "unit_cost",
                "line_value",
                "batch_number",
                "note",
            )
        )
        return Response({
            "scope": {
                "entity": entity_id,
                "entityfinid": entityfinid_id,
                "subentity": subentity_id,
                "from_date": from_date,
                "to_date": to_date,
            },
            "accounting": _manufacturing_accounting_payload(settings_obj),
            "overview": {
                "line_count": len(rows),
                "work_order_count": work_orders.count(),
                "total_actual_qty": sum((row["actual_qty"] or 0) for row in rows),
                "total_required_qty": sum((row["required_qty"] or 0) for row in rows),
                "total_waste_qty": sum((row["waste_qty"] or 0) for row in rows),
                "total_value": sum((row["line_value"] or 0) for row in rows),
            },
            "rows": rows,
        })


class ManufacturingOutputYieldAPIView(_BaseManufacturingAPIView):
    def get(self, request):
        entity_id, subentity_id, entityfinid_id, from_date, to_date = self._scope_with_dates(request, require_entityfinid=False)
        self.assert_permission(request, entity_id, "manufacturing.workorder.view")
        settings_obj, _ = ManufacturingSettings.objects.get_or_create(entity_id=entity_id, subentity_id=subentity_id)
        work_orders = _manufacturing_work_orders_queryset(
            entity_id=entity_id,
            subentity_id=subentity_id,
            entityfinid_id=entityfinid_id,
            from_date=from_date,
            to_date=to_date,
        ).select_related("bom")
        rows = list(
            work_orders.order_by("-production_date", "-id").values(
                "id",
                "work_order_no",
                "production_date",
                "status",
                "reference_no",
                "posting_entry_id",
                "bom__code",
                "standard_output_qty_snapshot",
                "actual_output_qty_snapshot",
                "yield_variance_qty_snapshot",
                "yield_variance_percent_snapshot",
                "standard_unit_cost_snapshot",
                "actual_unit_cost_snapshot",
                "net_production_cost_snapshot",
                "material_variance_value_snapshot",
                "standard_material_cost_snapshot",
                "actual_recovery_value_snapshot",
            )
        )
        for row in rows:
            row["yield_variance_value_snapshot"] = _yield_variance_value_from_row(row)
        output_lines = list(
            ManufacturingWorkOrderOutput.objects
            .filter(work_order__in=work_orders)
            .select_related("work_order", "finished_product", "uom")
            .order_by("-work_order__production_date", "-work_order_id", "line_no")
            .values(
                "work_order_id",
                "work_order__work_order_no",
                "line_no",
                "finished_product_id",
                "finished_product__productname",
                "finished_product__sku",
                "uom__code",
                "output_type",
                "planned_qty",
                "actual_qty",
                "unit_cost",
                "estimated_recovery_unit_value",
                "batch_number",
            )
        )
        return Response({
            "scope": {
                "entity": entity_id,
                "entityfinid": entityfinid_id,
                "subentity": subentity_id,
                "from_date": from_date,
                "to_date": to_date,
            },
            "accounting": _manufacturing_accounting_payload(settings_obj),
            "overview": {
                "work_order_count": len(rows),
                "total_standard_output_qty": sum((row["standard_output_qty_snapshot"] or 0) for row in rows),
                "total_actual_output_qty": sum((row["actual_output_qty_snapshot"] or 0) for row in rows),
                "total_net_cost": sum((row["net_production_cost_snapshot"] or 0) for row in rows),
                "total_material_variance": sum((row["material_variance_value_snapshot"] or 0) for row in rows),
                "total_yield_variance_value": sum((row["yield_variance_value_snapshot"] or 0) for row in rows),
            },
            "rows": rows,
            "output_lines": output_lines,
        })


class ManufacturingPostingAuditAPIView(_BaseManufacturingAPIView):
    def get(self, request):
        entity_id, subentity_id, entityfinid_id, from_date, to_date = self._scope_with_dates(request, require_entityfinid=False)
        self.assert_permission(request, entity_id, "manufacturing.workorder.view")
        settings_obj, _ = ManufacturingSettings.objects.get_or_create(entity_id=entity_id, subentity_id=subentity_id)
        work_orders = _manufacturing_work_orders_queryset(
            entity_id=entity_id,
            subentity_id=subentity_id,
            entityfinid_id=entityfinid_id,
            from_date=from_date,
            to_date=to_date,
        ).select_related("bom", "posted_by", "last_unposted_by", "cancelled_by")
        rows = list(
            work_orders.order_by("-production_date", "-id").values(
                "id",
                "work_order_no",
                "production_date",
                "status",
                "posting_entry_id",
                "posted_at",
                "posted_by__username",
                "last_unposted_at",
                "last_unposted_by__username",
                "last_unpost_reason",
                "cancelled_at",
                "cancelled_by__username",
                "cancel_reason",
                "reference_no",
                "bom__code",
                "total_additional_cost_snapshot",
                "net_production_cost_snapshot",
            )
        )
        return Response({
            "scope": {
                "entity": entity_id,
                "entityfinid": entityfinid_id,
                "subentity": subentity_id,
                "from_date": from_date,
                "to_date": to_date,
            },
            "accounting": _manufacturing_accounting_payload(settings_obj),
            "overview": {
                "work_order_count": len(rows),
                "posted_count": sum(1 for row in rows if row["status"] == "POSTED"),
                "draft_count": sum(1 for row in rows if row["status"] == "DRAFT"),
                "cancelled_count": sum(1 for row in rows if row["status"] == "CANCELLED"),
                "with_posting_entry_count": sum(1 for row in rows if row["posting_entry_id"]),
            },
            "rows": rows,
        })


class ManufacturingWipCostSummaryAPIView(_BaseManufacturingAPIView):
    def get(self, request):
        entity_id, subentity_id, entityfinid_id, from_date, to_date = self._scope_with_dates(request, require_entityfinid=False)
        self.assert_permission(request, entity_id, "manufacturing.workorder.view")
        settings_obj, _ = ManufacturingSettings.objects.get_or_create(entity_id=entity_id, subentity_id=subentity_id)
        work_orders = _manufacturing_work_orders_queryset(
            entity_id=entity_id,
            subentity_id=subentity_id,
            entityfinid_id=entityfinid_id,
            from_date=from_date,
            to_date=to_date,
        ).select_related("bom")
        rows = list(
            work_orders.order_by("-production_date", "-id").values(
                "id",
                "work_order_no",
                "production_date",
                "status",
                "posting_entry_id",
                "bom__code",
                "standard_material_cost_snapshot",
                "actual_material_cost_snapshot",
                "total_additional_cost_snapshot",
                "capitalized_additional_cost_snapshot",
                "expensed_additional_cost_snapshot",
                "standard_recovery_value_snapshot",
                "actual_recovery_value_snapshot",
                "net_production_cost_snapshot",
                "standard_output_qty_snapshot",
                "actual_output_qty_snapshot",
                "standard_unit_cost_snapshot",
                "actual_unit_cost_snapshot",
                "material_variance_value_snapshot",
                "yield_variance_qty_snapshot",
                "yield_variance_percent_snapshot",
                "actual_recovery_value_snapshot",
            )
        )
        for row in rows:
            row["yield_variance_value_snapshot"] = _yield_variance_value_from_row(row)
        return Response({
            "scope": {
                "entity": entity_id,
                "entityfinid": entityfinid_id,
                "subentity": subentity_id,
                "from_date": from_date,
                "to_date": to_date,
            },
            "accounting": _manufacturing_accounting_payload(settings_obj),
            "overview": {
                "work_order_count": len(rows),
                "draft_wip_value": sum((row["net_production_cost_snapshot"] or 0) for row in rows if row["status"] == "DRAFT"),
                "posted_cost_value": sum((row["net_production_cost_snapshot"] or 0) for row in rows if row["status"] == "POSTED"),
                "total_additional_cost": sum((row["total_additional_cost_snapshot"] or 0) for row in rows),
                "total_capitalized_additional_cost": sum((row["capitalized_additional_cost_snapshot"] or 0) for row in rows),
                "total_expensed_additional_cost": sum((row["expensed_additional_cost_snapshot"] or 0) for row in rows),
                "total_material_variance": sum((row["material_variance_value_snapshot"] or 0) for row in rows),
                "total_yield_variance_qty": sum((row["yield_variance_qty_snapshot"] or 0) for row in rows),
                "total_yield_variance_value": sum((row["yield_variance_value_snapshot"] or 0) for row in rows),
            },
            "rows": rows,
        })


class ManufacturingBOMFormMetaAPIView(_BaseManufacturingAPIView):
    def get(self, request):
        entity_id, subentity_id, _ = self._scope(request, require_entityfinid=False)
        self.assert_permission(request, entity_id, "manufacturing.bom.view")
        products = Product.objects.filter(entity_id=entity_id, isactive=True, is_service=False).order_by("productname", "id")
        scoped_filter = _subentity_scope_q(subentity_id, include_shared_when_scoped=True)
        routes = ManufacturingRoute.objects.filter(entity_id=entity_id, is_active=True).filter(scoped_filter)
        boms = ManufacturingBOM.objects.filter(entity_id=entity_id, is_active=True).filter(scoped_filter).order_by("code", "id")
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
        scoped_master_filter = _subentity_scope_q(subentity_id, include_shared_when_scoped=True)
        boms = ManufacturingBOM.objects.filter(entity_id=entity_id, is_active=True).filter(scoped_master_filter).select_related("finished_product", "route")
        routes = ManufacturingRoute.objects.filter(entity_id=entity_id, is_active=True).filter(scoped_master_filter)
        if subentity_id is None:
            godowns = Godown.objects.filter(entity_id=entity_id, subentity_id__isnull=True, is_active=True).order_by("name", "id")
        else:
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
            "accounting": _manufacturing_accounting_payload(settings_obj),
            "current_doc_numbers": {
                "manufacturing_work_order": settings_obj.default_doc_code_work_order if not entityfinid_id else settings_obj.default_doc_code_work_order
            },
        })
