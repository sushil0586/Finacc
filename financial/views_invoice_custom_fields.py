from __future__ import annotations

import re

from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404

from financial.invoice_custom_fields_service import InvoiceCustomFieldService
from financial.models import (
    InvoiceCustomFieldDefinition,
    InvoiceCustomFieldDefault,
)


class InvoiceCustomFieldDefinitionSerializer(serializers.ModelSerializer):
    key = serializers.CharField(max_length=64)

    class Meta:
        model = InvoiceCustomFieldDefinition
        fields = [
            "id",
            "entity",
            "subentity",
            "module",
            "key",
            "label",
            "field_type",
            "is_required",
            "order_no",
            "help_text",
            "options_json",
            "applies_to_account",
            "isactive",
        ]

    def validate_key(self, value: str) -> str:
        normalized = (value or "").strip().lower()
        if not normalized:
            raise serializers.ValidationError("key is required.")
        if not re.fullmatch(r"[a-z][a-z0-9_]*", normalized):
            raise serializers.ValidationError("key must be snake_case (letters, numbers, underscore).")
        return normalized

    def validate(self, attrs):
        instance = getattr(self, "instance", None)
        entity = attrs.get("entity") or getattr(instance, "entity", None)
        subentity = attrs.get("subentity") if "subentity" in attrs else getattr(instance, "subentity", None)
        module = attrs.get("module") or getattr(instance, "module", None)
        key = attrs.get("key") or getattr(instance, "key", None)
        applies_to_account = (
            attrs.get("applies_to_account")
            if "applies_to_account" in attrs
            else getattr(instance, "applies_to_account", None)
        )
        field_type = attrs.get("field_type") or getattr(instance, "field_type", None)
        options_json = attrs.get("options_json") if "options_json" in attrs else getattr(instance, "options_json", [])

        if field_type in (
            InvoiceCustomFieldDefinition.FieldType.SELECT,
            InvoiceCustomFieldDefinition.FieldType.MULTISELECT,
        ):
            if not isinstance(options_json, list) or not options_json:
                raise serializers.ValidationError(
                    {"options_json": "options_json must be a non-empty array for select/multiselect fields."}
                )
            normalized_opts = []
            for opt in options_json:
                sval = str(opt).strip()
                if not sval:
                    raise serializers.ValidationError({"options_json": "options_json cannot contain empty values."})
                normalized_opts.append(sval)
            attrs["options_json"] = normalized_opts
        elif "options_json" in attrs and attrs["options_json"] in (None, ""):
            attrs["options_json"] = []

        if entity and module and key:
            dupe_qs = InvoiceCustomFieldDefinition.objects.filter(
                entity=entity,
                subentity=subentity,
                module=module,
                key=key,
                applies_to_account=applies_to_account,
                isactive=True,
            )
            if instance:
                dupe_qs = dupe_qs.exclude(pk=instance.pk)
            if dupe_qs.exists():
                raise serializers.ValidationError(
                    {"key": "An active definition with this key already exists for the same scope/account."}
                )

        return attrs


class InvoiceCustomFieldDefaultSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceCustomFieldDefault
        fields = [
            "id",
            "definition",
            "party_account",
            "default_value",
            "isactive",
        ]

    def validate(self, attrs):
        instance = getattr(self, "instance", None)
        definition = attrs.get("definition") or getattr(instance, "definition", None)
        party_account = attrs.get("party_account") or getattr(instance, "party_account", None)
        default_value = attrs.get("default_value") if "default_value" in attrs else getattr(instance, "default_value", None)

        if definition is None or party_account is None:
            return attrs

        if definition.entity_id != party_account.entity_id:
            raise serializers.ValidationError("definition.entity and party_account.entity must match.")

        if definition.applies_to_account_id and definition.applies_to_account_id != party_account.id:
            raise serializers.ValidationError("definition applies to a different party account.")

        try:
            InvoiceCustomFieldService._validate_one_value(definition, default_value)
        except ValueError as ex:
            raise serializers.ValidationError({"default_value": str(ex)})

        return attrs


class InvoiceCustomFieldDefinitionListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        entity_id = request.query_params.get("entity")
        module = request.query_params.get("module")
        subentity_id = request.query_params.get("subentity")
        party_account_id = request.query_params.get("party")
        manage_mode = str(request.query_params.get("manage", "")).strip().lower() in ("1", "true", "yes")
        include_inactive = str(request.query_params.get("include_inactive", "")).strip().lower() in ("1", "true", "yes")

        if not entity_id or not module:
            return Response({"detail": "entity and module query params are required."}, status=400)

        if manage_mode:
            qs = InvoiceCustomFieldDefinition.objects.filter(
                entity_id=int(entity_id),
                module=str(module),
            )
            if not include_inactive:
                qs = qs.filter(isactive=True)
            if subentity_id not in (None, "", "0"):
                qs = qs.filter(subentity_id=int(subentity_id))
            if party_account_id not in (None, "", "0"):
                qs = qs.filter(applies_to_account_id=int(party_account_id))
            serialized = InvoiceCustomFieldDefinitionSerializer(
                qs.order_by("order_no", "id"), many=True
            ).data
            return Response({"definitions": serialized}, status=200)

        defs = InvoiceCustomFieldService.get_effective_definitions(
            entity_id=int(entity_id),
            module=str(module),
            subentity_id=int(subentity_id) if subentity_id not in (None, "", "0") else None,
            party_account_id=int(party_account_id) if party_account_id not in (None, "", "0") else None,
        )
        serialized = InvoiceCustomFieldDefinitionSerializer(defs, many=True).data
        return Response({"definitions": serialized}, status=200)

    def post(self, request):
        ser = InvoiceCustomFieldDefinitionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        obj = ser.save()
        return Response(InvoiceCustomFieldDefinitionSerializer(obj).data, status=status.HTTP_201_CREATED)


class InvoiceCustomFieldDefinitionDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk: int):
        obj = get_object_or_404(InvoiceCustomFieldDefinition, pk=pk)
        ser = InvoiceCustomFieldDefinitionSerializer(obj, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data, status=200)


class InvoiceCustomFieldDefaultListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        entity_id = request.query_params.get("entity")
        module = request.query_params.get("module")
        party_account_id = request.query_params.get("party")
        subentity_id = request.query_params.get("subentity")

        if not entity_id or not module or not party_account_id:
            return Response({"detail": "entity, module and party query params are required."}, status=400)

        defaults = InvoiceCustomFieldService.get_defaults_map(
            entity_id=int(entity_id),
            module=str(module),
            party_account_id=int(party_account_id),
            subentity_id=int(subentity_id) if subentity_id not in (None, "", "0") else None,
        )
        return Response({"defaults": defaults}, status=200)

    def post(self, request):
        ser = InvoiceCustomFieldDefaultSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        payload = ser.validated_data
        obj, _ = InvoiceCustomFieldDefault.objects.update_or_create(
            definition=payload["definition"],
            party_account=payload["party_account"],
            defaults={
                "default_value": payload.get("default_value"),
                "isactive": payload.get("isactive", True),
            },
        )
        return Response(InvoiceCustomFieldDefaultSerializer(obj).data, status=status.HTTP_201_CREATED)
