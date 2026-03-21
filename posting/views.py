from datetime import date
from typing import Optional

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import ValidationError

from posting.serializers import (
    StaticAccountRowSerializer,
    StaticAccountSettingsResponseSerializer,
    StaticAccountUpsertSerializer,
    StaticAccountBulkUpsertSerializer,
    StaticAccountValidationResponseSerializer,
)
from posting.static_account_service import StaticAccountMappingService


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValidationError("Invalid date format; expected YYYY-MM-DD.")


def _parse_int(value: Optional[str], label: str) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        raise ValidationError(f"Invalid {label}; expected integer.")


class StaticAccountSettingsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, entity_id: int):
        sub_entity_id = _parse_int(request.query_params.get("sub_entity_id"), "sub_entity_id")
        effective_on = _parse_date(request.query_params.get("effective_on"))

        resolved = StaticAccountMappingService.resolve(
            entity_id=entity_id, sub_entity_id=sub_entity_id, effective_on=effective_on
        )
        # serialize rows to primitives
        groups = {
            group: [StaticAccountRowSerializer.from_row(row) for row in rows]
            for group, rows in resolved["groups"].items()
        }
        data = {
            "summary": resolved["summary"],
            "groups": groups,
        }
        serializer = StaticAccountSettingsResponseSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data)


class StaticAccountSettingDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, entity_id: int, static_account_code: str):
        sub_entity_id = _parse_int(request.query_params.get("sub_entity_id"), "sub_entity_id")

        serializer = StaticAccountUpsertSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        row = StaticAccountMappingService.upsert_one(
            entity_id=entity_id,
            static_account_code=static_account_code,
            account_id=payload.get("account_id"),
            ledger_id=payload.get("ledger_id"),
            sub_entity_id=sub_entity_id,
            effective_from=payload.get("effective_from"),
            actor=request.user,
        )
        return Response(StaticAccountRowSerializer.from_row(row), status=status.HTTP_200_OK)

    def delete(self, request, entity_id: int, static_account_code: str):
        sub_entity_id = _parse_int(request.query_params.get("sub_entity_id"), "sub_entity_id")

        row = StaticAccountMappingService.deactivate(
            entity_id=entity_id,
            static_account_code=static_account_code,
            sub_entity_id=sub_entity_id,
        )
        return Response(StaticAccountRowSerializer.from_row(row), status=status.HTTP_200_OK)


class StaticAccountSettingsBulkUpsertView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, entity_id: int):
        sub_entity_id = _parse_int(
            request.data.get("sub_entity_id") or request.query_params.get("sub_entity_id"),
            "sub_entity_id",
        )

        serializer = StaticAccountBulkUpsertSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        result = StaticAccountMappingService.bulk_upsert(
            entity_id=entity_id,
            sub_entity_id=sub_entity_id,
            effective_from=payload.get("effective_from"),
            items=payload["items"],
            actor=request.user,
        )
        response = {
            "updated": [StaticAccountRowSerializer.from_row(r) for r in result["updated"]],
            "summary": result["summary"],
        }
        return Response(response, status=status.HTTP_200_OK)


class StaticAccountSettingsValidateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, entity_id: int):
        sub_entity_id = _parse_int(request.query_params.get("sub_entity_id"), "sub_entity_id")
        effective_on = _parse_date(request.query_params.get("effective_on"))

        result = StaticAccountMappingService.validate_required(
            entity_id=entity_id, sub_entity_id=sub_entity_id, effective_on=effective_on
        )
        serializer = StaticAccountValidationResponseSerializer(data=result)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data)
