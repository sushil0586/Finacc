from datetime import date
from typing import Optional

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied, ValidationError

from core.entitlements import ScopedEntitlementMixin
from posting.bank_account_mapping_service import EntityBankAccountMappingService
from posting.serializers import (
    BankAccountMappingRowSerializer,
    BankAccountMappingUpsertSerializer,
    EligibleBankLedgerSerializer,
    StaticAccountRowSerializer,
    StaticAccountUpsertSerializer,
    StaticAccountBulkUpsertSerializer,
    StaticAccountValidationResponseSerializer,
)
from posting.static_account_service import StaticAccountMappingService
from rbac.services import EffectivePermissionService
from subscriptions.services import SubscriptionLimitCodes, SubscriptionService


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


class _BaseStaticAccountSettingsAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [IsAuthenticated]
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_FINANCIAL
    subscription_access_mode = SubscriptionService.ACCESS_MODE_SETUP

    def _enforce_access(self, request, *, entity_id: int, permission_code: str):
        self.enforce_scope(request, entity_id=entity_id)
        permission_codes = EffectivePermissionService.permission_codes_for_user(request.user, entity_id)
        if permission_code not in permission_codes:
            raise PermissionDenied(f"Missing permission: {permission_code}")


class StaticAccountSettingsView(_BaseStaticAccountSettingsAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, entity_id: int):
        self._enforce_access(request, entity_id=entity_id, permission_code="posting.static_account_settings.view")
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
            "eligible_bank_ledgers": [
                EligibleBankLedgerSerializer.from_row(row)
                for row in EntityBankAccountMappingService.eligible_ledgers(entity_id=entity_id)
            ],
            "bank_account_mappings": [
                BankAccountMappingRowSerializer.from_row(row)
                for row in EntityBankAccountMappingService.list_rows(entity_id=entity_id)
            ],
        }
        return Response(data)


class StaticAccountSettingDetailView(_BaseStaticAccountSettingsAPIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, entity_id: int, static_account_code: str):
        self._enforce_access(request, entity_id=entity_id, permission_code="posting.static_account_settings.update")
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
        self._enforce_access(request, entity_id=entity_id, permission_code="posting.static_account_settings.delete")
        sub_entity_id = _parse_int(request.query_params.get("sub_entity_id"), "sub_entity_id")

        row = StaticAccountMappingService.deactivate(
            entity_id=entity_id,
            static_account_code=static_account_code,
            sub_entity_id=sub_entity_id,
        )
        return Response(StaticAccountRowSerializer.from_row(row), status=status.HTTP_200_OK)


class StaticAccountSettingsBulkUpsertView(_BaseStaticAccountSettingsAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, entity_id: int):
        self._enforce_access(request, entity_id=entity_id, permission_code="posting.static_account_settings.bulk_upsert")
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


class StaticAccountSettingsValidateView(_BaseStaticAccountSettingsAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, entity_id: int):
        self._enforce_access(request, entity_id=entity_id, permission_code="posting.static_account_settings.validate")
        sub_entity_id = _parse_int(request.query_params.get("sub_entity_id"), "sub_entity_id")
        effective_on = _parse_date(request.query_params.get("effective_on"))

        result = StaticAccountMappingService.validate_required(
            entity_id=entity_id, sub_entity_id=sub_entity_id, effective_on=effective_on
        )
        serializer = StaticAccountValidationResponseSerializer(data=result)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data)


class BankAccountMappingDetailView(_BaseStaticAccountSettingsAPIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, entity_id: int, bank_account_id: int):
        self._enforce_access(request, entity_id=entity_id, permission_code="posting.static_account_settings.update")
        serializer = BankAccountMappingUpsertSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        row = EntityBankAccountMappingService.update_mapping(
            entity_id=entity_id,
            bank_account_id=bank_account_id,
            ledger_id=serializer.validated_data.get("ledger_id"),
        )
        return Response(BankAccountMappingRowSerializer.from_row(row), status=status.HTTP_200_OK)
