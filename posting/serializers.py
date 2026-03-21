from __future__ import annotations

from datetime import date
from typing import Any, Dict

from rest_framework import serializers

from posting.static_account_service import ResolvedRow, StaticAccountStatus


class StaticAccountRowSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    group = serializers.CharField()
    is_required = serializers.BooleanField()
    description = serializers.CharField(allow_null=True, allow_blank=True, required=False)
    account_id = serializers.IntegerField(allow_null=True)
    ledger_id = serializers.IntegerField(allow_null=True)
    scope = serializers.CharField(allow_null=True)
    effective_from = serializers.DateField(allow_null=True)
    status = serializers.CharField()
    inherited = serializers.BooleanField()

    @classmethod
    def from_row(cls, row: ResolvedRow) -> Dict[str, Any]:
        return {
            "code": row.code,
            "name": row.name,
            "group": row.group,
            "is_required": row.is_required,
            "description": row.description,
            "account_id": row.account_id,
            "ledger_id": row.ledger_id,
            "scope": row.scope,
            "effective_from": row.effective_from,
            "status": row.status,
            "inherited": row.inherited,
        }


class StaticAccountSummarySerializer(serializers.Serializer):
    configured = serializers.IntegerField()
    configured_inherited = serializers.IntegerField()
    missing_required = serializers.IntegerField()
    missing_optional = serializers.IntegerField()


class StaticAccountSettingsResponseSerializer(serializers.Serializer):
    summary = StaticAccountSummarySerializer()
    groups = serializers.DictField(child=StaticAccountRowSerializer(many=True))


class StaticAccountUpsertSerializer(serializers.Serializer):
    account_id = serializers.IntegerField(required=False, allow_null=True)
    ledger_id = serializers.IntegerField(required=False, allow_null=True)
    effective_from = serializers.DateField(required=False, allow_null=True)

    def validate(self, attrs):
        if not attrs.get("account_id") and not attrs.get("ledger_id"):
            raise serializers.ValidationError("Either account_id or ledger_id is required.")
        return attrs


class StaticAccountBulkItemSerializer(serializers.Serializer):
    static_account_code = serializers.CharField()
    account_id = serializers.IntegerField(required=False, allow_null=True)
    ledger_id = serializers.IntegerField(required=False, allow_null=True)

    def validate(self, attrs):
        if not attrs.get("account_id") and not attrs.get("ledger_id"):
            raise serializers.ValidationError("Either account_id or ledger_id is required.")
        return attrs


class StaticAccountBulkUpsertSerializer(serializers.Serializer):
    sub_entity_id = serializers.IntegerField(required=False, allow_null=True)
    effective_from = serializers.DateField(required=False, allow_null=True)
    items = StaticAccountBulkItemSerializer(many=True)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("items cannot be empty.")
        return value


class StaticAccountValidationResponseSerializer(serializers.Serializer):
    missing_required = serializers.ListField(child=serializers.CharField())
    missing_optional = serializers.ListField(child=serializers.CharField())
    issues = serializers.ListField(child=serializers.CharField())
