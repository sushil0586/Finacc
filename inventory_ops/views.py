from __future__ import annotations

from typing import Any, Optional

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.entitlements import ScopedEntitlementMixin
from entity.models import Godown
from numbering.models import DocumentNumberSeries
from numbering.services import ensure_document_type, ensure_series
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
from .models import InventoryOpsSettings, InventoryTransfer
from .services import InventoryAdjustmentService, InventoryTransferService


def _choice_payload(choices) -> list[dict]:
    return [{"value": value, "label": label} for value, label in choices]


INVENTORY_SETTINGS_SCHEMA = [
    {"name": "default_doc_code_transfer", "label": "Default Transfer Doc Code", "type": "string", "group": "numbering_defaults"},
    {"name": "default_doc_code_adjustment", "label": "Default Adjustment Doc Code", "type": "string", "group": "numbering_defaults"},
    {"name": "default_workflow_action", "label": "Default Workflow", "type": "choice", "group": "workflow", "choices": _choice_payload(InventoryOpsSettings.DefaultWorkflowAction.choices)},
    {"name": "auto_derive_transfer_cost", "label": "Auto Derive Transfer Cost", "type": "boolean", "group": "transfer_controls"},
    {"name": "show_transfer_cost_readonly", "label": "Show Transfer Cost Read Only", "type": "boolean", "group": "transfer_controls"},
    {"name": "allow_manual_transfer_cost_override", "label": "Allow Manual Transfer Cost Override", "type": "boolean", "group": "transfer_controls"},
    {"name": "require_confirm_before_post", "label": "Require Confirm Before Post", "type": "boolean", "group": "workflow"},
    {"name": "allow_unpost_posted", "label": "Allow Unpost Posted", "type": "boolean", "group": "workflow"},
    {"name": "allow_cancel_draft", "label": "Allow Cancel Draft", "type": "boolean", "group": "workflow"},
    {"name": "unpost_target_status", "label": "Unpost Target Status", "type": "choice", "group": "workflow", "choices": _choice_payload([("draft", "Draft"), ("confirmed", "Confirmed")])},
    {"name": "require_reason_on_adjustment", "label": "Require Reason On Adjustment", "type": "boolean", "group": "adjustment_controls"},
    {"name": "positive_adjustment_cost_mode", "label": "Positive Adjustment Cost Mode", "type": "choice", "group": "adjustment_controls", "choices": _choice_payload([("required_if_no_default", "Required if no default"), ("auto_if_available", "Auto if available"), ("always_required", "Always required")])},
    {"name": "block_negative_adjustment_without_stock", "label": "Block Negative Adjustment Without Stock", "type": "boolean", "group": "adjustment_controls"},
    {"name": "require_batch_for_batch_managed_items", "label": "Require Batch For Batch Managed Items", "type": "boolean", "group": "batch_validation"},
    {"name": "require_expiry_when_expiry_tracked", "label": "Require Expiry When Expiry Tracked", "type": "boolean", "group": "batch_validation"},
    {"name": "transfer_shortage_rule", "label": "Transfer Shortage Rule", "type": "choice", "group": "batch_validation", "choices": _choice_payload([("block", "Block"), ("warn", "Warn")])},
    {"name": "adjustment_shortage_rule", "label": "Adjustment Shortage Rule", "type": "choice", "group": "batch_validation", "choices": _choice_payload([("block", "Block"), ("warn", "Warn")])},
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

EDITABLE_SETTINGS_FIELDS = {
    "default_doc_code_transfer",
    "default_doc_code_adjustment",
    "default_workflow_action",
    "auto_derive_transfer_cost",
    "show_transfer_cost_readonly",
    "allow_manual_transfer_cost_override",
    "require_confirm_before_post",
    "allow_unpost_posted",
    "allow_cancel_draft",
    "unpost_target_status",
    "require_reason_on_adjustment",
    "positive_adjustment_cost_mode",
    "block_negative_adjustment_without_stock",
    "require_batch_for_batch_managed_items",
    "require_expiry_when_expiry_tracked",
    "transfer_shortage_rule",
    "adjustment_shortage_rule",
}

INVENTORY_DOC_TYPES = {
    "inventory_transfer": {
        "doc_key": "INVENTORY_TRANSFER",
        "label": "Inventory Transfer",
        "default_code_field": "default_doc_code_transfer",
        "fallback_code": "ITF",
        "prefix": "ITF",
    },
    "inventory_adjustment": {
        "doc_key": "INVENTORY_ADJUSTMENT",
        "label": "Inventory Adjustment",
        "default_code_field": "default_doc_code_adjustment",
        "fallback_code": "IAD",
        "prefix": "IAD",
    },
}


def _raise_inventory_validation(err: Exception) -> None:
    payload = err.args[0] if err.args else str(err)
    if isinstance(payload, dict):
        raise ValidationError(payload)
    raise ValidationError({"detail": str(payload)})


class _BaseInventoryOpsAPIView(ScopedEntitlementMixin, APIView):
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


class InventoryOpsSettingsAPIView(_BaseInventoryOpsAPIView):
    @staticmethod
    def _ensure_doc_type(series_key: str, settings_obj: InventoryOpsSettings):
        cfg = INVENTORY_DOC_TYPES[series_key]
        doc_code = getattr(settings_obj, cfg["default_code_field"]) or cfg["fallback_code"]
        return ensure_document_type(module="inventory_ops", doc_key=cfg["doc_key"], name=cfg["label"], default_code=doc_code)

    def _get_settings(self, *, entity_id: int, subentity_id: Optional[int]) -> InventoryOpsSettings:
        settings_obj, _ = InventoryOpsSettings.objects.get_or_create(entity_id=entity_id, subentity_id=subentity_id)
        return settings_obj

    @staticmethod
    def _settings_payload(settings_obj: InventoryOpsSettings) -> dict[str, Any]:
        payload = {
            "default_doc_code_transfer": settings_obj.default_doc_code_transfer,
            "default_doc_code_adjustment": settings_obj.default_doc_code_adjustment,
            "default_workflow_action": settings_obj.default_workflow_action,
        }
        payload.update(settings_obj.policy_controls or {})
        return payload

    def _series_payload(self, *, entity_id: int, entityfinid_id: int, subentity_id: Optional[int], settings_obj: InventoryOpsSettings) -> list[dict]:
        rows: list[dict] = []
        for series_key, cfg in INVENTORY_DOC_TYPES.items():
            doc_code = getattr(settings_obj, cfg["default_code_field"]) or cfg["fallback_code"]
            doc_type = self._ensure_doc_type(series_key, settings_obj)
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
                    prefix=cfg["prefix"],
                    start=1,
                    padding=4,
                    reset="yearly",
                    include_year=False,
                    include_month=False,
                )
            rows.append({
                "series_key": series_key,
                "label": cfg["label"],
                "doc_key": cfg["doc_key"],
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
            })
        return rows

    def _update_numbering_series(self, rows: list[dict], *, entity_id: int, entityfinid_id: int, subentity_id: Optional[int], settings_obj: InventoryOpsSettings) -> None:
        row_map = {row["series_key"]: row for row in rows if isinstance(row, dict) and row.get("series_key") in INVENTORY_DOC_TYPES}
        for series_key, cfg in INVENTORY_DOC_TYPES.items():
            if series_key not in row_map:
                continue
            row = row_map[series_key]
            doc_code = str(row.get("doc_code") or getattr(settings_obj, cfg["default_code_field"]) or "").strip()
            if not doc_code:
                raise ValidationError({"numbering_series": f"doc_code is required for {series_key}."})
            doc_type = self._ensure_doc_type(series_key, settings_obj)
            series, _ = ensure_series(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                subentity_id=subentity_id,
                doc_type_id=doc_type.id,
                doc_code=doc_code,
                prefix=str(row.get("prefix") or cfg["prefix"]).strip() or cfg["prefix"],
                start=int(row.get("starting_number") or 1),
                padding=int(row.get("number_padding") or 4),
                reset=str(row.get("reset_frequency") or "yearly"),
                include_year=bool(row.get("include_year", False)),
                include_month=bool(row.get("include_month", False)),
            )
            series.suffix = str(row.get("suffix") or "")
            series.current_number = int(row.get("current_number") or series.current_number or series.starting_number or 1)
            series.separator = str(row.get("separator") if row.get("separator") is not None else series.separator or "-")
            series.custom_format = str(row.get("custom_format") or "")
            series.is_active = bool(row.get("is_active", True))
            series.save(update_fields=[
                "suffix",
                "current_number",
                "separator",
                "custom_format",
                "is_active",
                "updated_at",
            ])

    @staticmethod
    def _validate_settings_updates(settings_updates: dict[str, Any]) -> None:
        workflow_values = {v for v, _ in InventoryOpsSettings.DefaultWorkflowAction.choices}
        if "default_doc_code_transfer" in settings_updates:
            code = str(settings_updates["default_doc_code_transfer"] or "").strip()
            if not code:
                raise ValidationError({"default_doc_code_transfer": "This field cannot be blank."})
            if len(code) > 10:
                raise ValidationError({"default_doc_code_transfer": "Ensure this value has at most 10 characters."})
        if "default_doc_code_adjustment" in settings_updates:
            code = str(settings_updates["default_doc_code_adjustment"] or "").strip()
            if not code:
                raise ValidationError({"default_doc_code_adjustment": "This field cannot be blank."})
            if len(code) > 10:
                raise ValidationError({"default_doc_code_adjustment": "Ensure this value has at most 10 characters."})
        if "default_workflow_action" in settings_updates and settings_updates["default_workflow_action"] not in workflow_values:
            raise ValidationError({"default_workflow_action": f"Invalid value. Allowed: {', '.join(sorted(workflow_values))}."})
        if "unpost_target_status" in settings_updates and settings_updates["unpost_target_status"] not in {"draft", "confirmed"}:
            raise ValidationError({"unpost_target_status": "Allowed values: draft, confirmed."})
        if "positive_adjustment_cost_mode" in settings_updates and settings_updates["positive_adjustment_cost_mode"] not in {"required_if_no_default", "auto_if_available", "always_required"}:
            raise ValidationError({"positive_adjustment_cost_mode": "Invalid positive adjustment cost mode."})
        for field_name in ("transfer_shortage_rule", "adjustment_shortage_rule"):
            if field_name in settings_updates and settings_updates[field_name] not in {"block", "warn"}:
                raise ValidationError({field_name: "Allowed values: block, warn."})

    def get(self, request):
        entity_id, subentity_id, entityfinid_id = self._scope(request, require_entityfinid=False)
        self.assert_permission(request, entity_id, "inventory.transfer.view")
        settings_obj = self._get_settings(entity_id=entity_id, subentity_id=subentity_id)
        return Response({
            "settings": self._settings_payload(settings_obj),
            "numbering_series": self._series_payload(entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id, settings_obj=settings_obj) if entityfinid_id else [],
            "capabilities": {
                "has_numbering_management": bool(entityfinid_id),
            },
        })

    @transaction.atomic
    def patch(self, request):
        entity_id = self._parse_int(request.data.get("entity"), "entity", required=True)
        subentity_id = self._parse_int(request.data.get("subentity"), "subentity_id", required=False)
        entityfinid_id = self._parse_int(request.data.get("entityfinid"), "entityfinid", required=False)
        self.enforce_scope(request, entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id)
        self.assert_permission(request, entity_id, "inventory.transfer.view")
        settings_obj = self._get_settings(entity_id=entity_id, subentity_id=subentity_id)

        settings_payload = request.data.get("settings")
        if settings_payload is not None:
            if not isinstance(settings_payload, dict):
                raise ValidationError({"settings": "Provide settings as an object."})
            settings_updates = {key: settings_payload[key] for key in EDITABLE_SETTINGS_FIELDS if key in settings_payload}
            self._validate_settings_updates(settings_updates)
            policy_controls = dict(settings_obj.policy_controls or {})
            direct_updates = {}
            for key, value in settings_updates.items():
                if key in {"default_doc_code_transfer", "default_doc_code_adjustment", "default_workflow_action"}:
                    direct_updates[key] = value
                else:
                    policy_controls[key] = value
            for key, value in direct_updates.items():
                setattr(settings_obj, key, value)
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
            )

        return Response({
            "settings": self._settings_payload(settings_obj),
            "numbering_series": self._series_payload(entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id, settings_obj=settings_obj) if entityfinid_id else [],
            "capabilities": {
                "has_numbering_management": bool(entityfinid_id),
            },
        })


class InventoryOpsSettingsMetaAPIView(InventoryOpsSettingsAPIView):
    def get(self, request):
        entity_id, subentity_id, entityfinid_id = self._scope(request, require_entityfinid=False)
        self.assert_permission(request, entity_id, "inventory.transfer.view")
        settings_obj = self._get_settings(entity_id=entity_id, subentity_id=subentity_id)
        return Response({
            "settings": self._settings_payload(settings_obj),
            "schema": INVENTORY_SETTINGS_SCHEMA,
            "numbering_series": self._series_payload(entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id, settings_obj=settings_obj) if entityfinid_id else [],
            "numbering_series_schema": NUMBERING_SERIES_SCHEMA,
            "capabilities": {
                "has_numbering_management": bool(entityfinid_id),
            },
        })


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
        try:
            result = InventoryTransferService.create_transfer(payload=payload, user_id=request.user.id)
        except (ValueError, ValidationError) as exc:
            _raise_inventory_validation(exc)
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
    def get_object(self, pk: int):
        from .models import InventoryTransfer

        transfer = get_object_or_404(
            InventoryTransfer.objects.select_related("source_location", "destination_location").prefetch_related("lines__product", "lines__uom"),
            pk=pk,
        )
        return transfer

    def get(self, request, pk: int):
        transfer = self.get_object(pk)
        self.enforce_scope(request, entity_id=transfer.entity_id, entityfinid_id=transfer.entityfin_id, subentity_id=transfer.subentity_id)
        self.assert_permission(request, transfer.entity_id, "inventory.transfer.view")
        return Response(InventoryTransferResponseSerializer(transfer).data)

    def patch(self, request, pk: int):
        transfer = self.get_object(pk)
        self.enforce_scope(request, entity_id=transfer.entity_id, entityfinid_id=transfer.entityfin_id, subentity_id=transfer.subentity_id)
        self.assert_permission(request, transfer.entity_id, "inventory.transfer.update")
        serializer = InventoryTransferCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        try:
            result = InventoryTransferService.update_transfer(transfer_id=pk, payload=payload, user_id=request.user.id)
        except (ValueError, ValidationError) as exc:
            _raise_inventory_validation(exc)
        return Response(
            {
                "message": "Transfer updated successfully.",
                "transfer": InventoryTransferResponseSerializer(result.transfer).data,
                "entry_id": result.entry_id,
            }
        )


class InventoryTransferPostAPIView(_BaseInventoryOpsAPIView):
    def post(self, request, pk: int):
        transfer = get_object_or_404(InventoryTransfer, pk=pk)
        self.enforce_scope(request, entity_id=transfer.entity_id, entityfinid_id=transfer.entityfin_id, subentity_id=transfer.subentity_id)
        self.assert_permission(request, transfer.entity_id, "inventory.transfer.post")
        try:
            result = InventoryTransferService.post_transfer(transfer_id=pk, user_id=request.user.id)
        except (ValueError, ValidationError) as exc:
            _raise_inventory_validation(exc)
        return Response(
            {
                "message": "Transfer posted successfully.",
                "transfer": InventoryTransferResponseSerializer(result.transfer).data,
                "entry_id": result.entry_id,
            }
        )


class InventoryTransferUnpostAPIView(_BaseInventoryOpsAPIView):
    def post(self, request, pk: int):
        transfer = get_object_or_404(InventoryTransfer, pk=pk)
        self.enforce_scope(request, entity_id=transfer.entity_id, entityfinid_id=transfer.entityfin_id, subentity_id=transfer.subentity_id)
        self.assert_permission(request, transfer.entity_id, "inventory.transfer.unpost")
        reason = str(request.data.get("reason") or "").strip() or None
        try:
            result = InventoryTransferService.unpost_transfer(transfer_id=pk, user_id=request.user.id, reason=reason)
        except (ValueError, ValidationError) as exc:
            _raise_inventory_validation(exc)
        return Response(
            {
                "message": "Transfer unposted successfully.",
                "transfer": InventoryTransferResponseSerializer(result.transfer).data,
                "entry_id": result.entry_id,
            }
        )


class InventoryTransferCancelAPIView(_BaseInventoryOpsAPIView):
    def post(self, request, pk: int):
        transfer = get_object_or_404(InventoryTransfer, pk=pk)
        self.enforce_scope(request, entity_id=transfer.entity_id, entityfinid_id=transfer.entityfin_id, subentity_id=transfer.subentity_id)
        self.assert_permission(request, transfer.entity_id, "inventory.transfer.cancel")
        reason = str(request.data.get("reason") or "").strip() or None
        try:
            result = InventoryTransferService.cancel_transfer(transfer_id=pk, user_id=request.user.id, reason=reason)
        except (ValueError, ValidationError) as exc:
            _raise_inventory_validation(exc)
        return Response(
            {
                "message": "Transfer cancelled successfully.",
                "transfer": InventoryTransferResponseSerializer(result.transfer).data,
                "entry_id": result.entry_id,
            }
        )


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
