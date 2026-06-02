from __future__ import annotations

from datetime import date
from typing import Any, Dict

from rest_framework import serializers

from posting.bank_account_mapping_service import BankAccountMappingRow, EligibleBankLedgerRow
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
    eligible_bank_ledgers = serializers.ListField(child=serializers.DictField(), required=False)
    bank_account_mappings = serializers.ListField(child=serializers.DictField(), required=False)


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


class EligibleBankLedgerSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    ledger_code = serializers.IntegerField(allow_null=True)
    name = serializers.CharField()
    account_id = serializers.IntegerField(allow_null=True)
    accountname = serializers.CharField(allow_null=True)

    @classmethod
    def from_row(cls, row: EligibleBankLedgerRow) -> Dict[str, Any]:
        return {
            "id": row.id,
            "ledger_code": row.ledger_code,
            "name": row.name,
            "account_id": row.account_id,
            "accountname": row.accountname,
        }


class BankAccountMappingRowSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    entity_id = serializers.IntegerField()
    bank_name = serializers.CharField()
    account_number_masked = serializers.CharField()
    ifsc_code = serializers.CharField()
    branch = serializers.CharField(allow_null=True)
    is_primary = serializers.BooleanField()
    is_active = serializers.BooleanField()
    ledger_id = serializers.IntegerField(allow_null=True)
    ledger_name = serializers.CharField(allow_null=True)
    account_id = serializers.IntegerField(allow_null=True)
    account_name = serializers.CharField(allow_null=True)
    mapping_source = serializers.CharField()

    @classmethod
    def from_row(cls, row: BankAccountMappingRow) -> Dict[str, Any]:
        return {
            "id": row.id,
            "entity_id": row.entity_id,
            "bank_name": row.bank_name,
            "account_number_masked": row.account_number_masked,
            "ifsc_code": row.ifsc_code,
            "branch": row.branch,
            "is_primary": row.is_primary,
            "is_active": row.is_active,
            "ledger_id": row.ledger_id,
            "ledger_name": row.ledger_name,
            "account_id": row.account_id,
            "account_name": row.account_name,
            "mapping_source": row.mapping_source,
        }


class BankAccountMappingUpsertSerializer(serializers.Serializer):
    ledger_id = serializers.IntegerField(required=False, allow_null=True)
