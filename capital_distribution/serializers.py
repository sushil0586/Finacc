from __future__ import annotations

from rest_framework import serializers

from entity.models import EntityOwnershipV2
from financial.models import account

from .models import CapitalDistributionRun, DistributionPolicyStakeholder, FormationType


class EntityScopeSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    entityfinid = serializers.IntegerField(required=False, allow_null=True)
    subentity = serializers.IntegerField(required=False, allow_null=True)


class FormationResolveSerializer(EntityScopeSerializer):
    effective_from = serializers.DateField(required=False, allow_null=True)


class PolicyStakeholderWriteSerializer(serializers.Serializer):
    ownership = serializers.PrimaryKeyRelatedField(queryset=EntityOwnershipV2.objects.all())
    target_type = serializers.ChoiceField(choices=DistributionPolicyStakeholder.TargetType.choices)
    target_name = serializers.CharField(max_length=150)
    profit_percentage = serializers.DecimalField(max_digits=7, decimal_places=4, required=False, allow_null=True)
    loss_percentage = serializers.DecimalField(max_digits=7, decimal_places=4, required=False, allow_null=True)
    destination_account_preference = serializers.ChoiceField(
        choices=EntityOwnershipV2.AccountPreference.choices,
        required=False,
        default=EntityOwnershipV2.AccountPreference.CURRENT,
    )
    configuration = serializers.JSONField(required=False, default=dict)
    sort_order = serializers.IntegerField(required=False, min_value=0)


class DistributionPolicyWriteSerializer(EntityScopeSerializer):
    formation_profile = serializers.IntegerField()
    effective_from = serializers.DateField()
    effective_to = serializers.DateField(required=False, allow_null=True)
    governing_document_reference = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    configuration = serializers.JSONField(required=False, default=dict)
    schema_version = serializers.IntegerField(required=False, min_value=1, default=1)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    stakeholders = PolicyStakeholderWriteSerializer(many=True)

    def validate(self, attrs):
        if attrs.get("effective_to") and attrs["effective_from"] > attrs["effective_to"]:
            raise serializers.ValidationError({"effective_to": "Effective end date must be on or after effective start date."})
        return attrs


class DistributionPolicyPatchSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    expected_updated_at = serializers.DateTimeField()
    entityfinid = serializers.IntegerField(required=False, allow_null=True)
    subentity = serializers.IntegerField(required=False, allow_null=True)
    effective_from = serializers.DateField(required=False)
    effective_to = serializers.DateField(required=False, allow_null=True)
    governing_document_reference = serializers.CharField(max_length=255, required=False, allow_blank=True)
    configuration = serializers.JSONField(required=False)
    schema_version = serializers.IntegerField(required=False, min_value=1)
    notes = serializers.CharField(required=False, allow_blank=True)
    stakeholders = PolicyStakeholderWriteSerializer(many=True, required=False)


class PolicyActionSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    expected_updated_at = serializers.DateTimeField()
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)


class DistributionPolicySeedSerializer(EntityScopeSerializer):
    formation_profile = serializers.IntegerField()
    effective_from = serializers.DateField()
    effective_to = serializers.DateField(required=False, allow_null=True)
    governing_document_reference = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        default="",
    )
    configuration = serializers.JSONField(required=False, default=dict)
    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        if attrs.get("effective_to") and attrs["effective_from"] > attrs["effective_to"]:
            raise serializers.ValidationError({
                "effective_to": "Effective end date must be on or after effective start date."
            })
        return attrs


class DistributionBalanceInputSerializer(serializers.Serializer):
    ownership = serializers.IntegerField()
    capital_balance = serializers.DecimalField(max_digits=18, decimal_places=2, required=False, default="0.00")
    drawing_balance = serializers.DecimalField(max_digits=18, decimal_places=2, required=False, default="0.00")
    movements = serializers.ListField(child=serializers.DictField(), required=False, default=list)
    source_references = serializers.ListField(child=serializers.CharField(), required=False, default=list)


class CapitalDistributionCalculateSerializer(EntityScopeSerializer):
    entityfinid = serializers.IntegerField()
    period_from = serializers.DateField()
    period_to = serializers.DateField()
    cadence = serializers.ChoiceField(choices=CapitalDistributionRun.Cadence.choices, default="custom")
    profit_source = serializers.ChoiceField(choices=CapitalDistributionRun.ProfitSource.choices)
    source_profit = serializers.DecimalField(max_digits=18, decimal_places=2, required=False, allow_null=True)
    book_adjustments = serializers.DecimalField(max_digits=18, decimal_places=2, required=False, default="0.00")
    balances = DistributionBalanceInputSerializer(many=True, required=False, default=list)
    idempotency_key = serializers.CharField(max_length=80)

    def validate(self, attrs):
        if attrs["period_from"] > attrs["period_to"]:
            raise serializers.ValidationError({"period_to": "Period end must be on or after period start."})
        if attrs["profit_source"] != CapitalDistributionRun.ProfitSource.POSTED_BOOKS and attrs.get("source_profit") is None:
            raise serializers.ValidationError({"source_profit": "Source profit is required for this calculation mode."})
        ownership_ids = [row["ownership"] for row in attrs.get("balances", [])]
        if len(ownership_ids) != len(set(ownership_ids)):
            raise serializers.ValidationError({"balances": "Each ownership row can have only one balance input."})
        return attrs


class CapitalDistributionAccountMappingSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    ownership = serializers.PrimaryKeyRelatedField(queryset=EntityOwnershipV2.objects.all())
    capital_account = serializers.PrimaryKeyRelatedField(queryset=account.objects.all(), required=False, allow_null=True)
    current_account = serializers.PrimaryKeyRelatedField(queryset=account.objects.all(), required=False, allow_null=True)
    drawings_account = serializers.PrimaryKeyRelatedField(queryset=account.objects.all(), required=False, allow_null=True)
    effective_from = serializers.DateField(required=False, allow_null=True)
    effective_to = serializers.DateField(required=False, allow_null=True)

    def validate(self, attrs):
        if not attrs.get("capital_account") and not attrs.get("current_account"):
            raise serializers.ValidationError({"current_account": "Map at least one capital or current account."})
        if attrs.get("effective_from") and attrs.get("effective_to") and attrs["effective_from"] > attrs["effective_to"]:
            raise serializers.ValidationError({"effective_to": "Effective end date must be on or after effective start date."})
        return attrs


class CapitalDistributionRunActionSerializer(PolicyActionSerializer):
    pass


class AppropriationStatementQuerySerializer(EntityScopeSerializer):
    entityfinid = serializers.IntegerField()
    period_from = serializers.DateField()
    period_to = serializers.DateField()

    def validate(self, attrs):
        if attrs["period_from"] > attrs["period_to"]:
            raise serializers.ValidationError({"period_to": "Period end must be on or after period start."})
        return attrs


def serialize_policy(policy) -> dict:
    stakeholder_rows = policy.stakeholders.filter(isactive=True).select_related("ownership").order_by("sort_order", "id")
    return {
        "id": policy.id,
        "entity": policy.entity_id,
        "entityfinid": policy.entityfin_id,
        "subentity": policy.subentity_id,
        "formation_profile": policy.formation_profile_id,
        "formation_type": policy.formation_type,
        "formation_label": FormationType(policy.formation_type).label,
        "version_number": policy.version_number,
        "status": policy.status,
        "effective_from": policy.effective_from.isoformat(),
        "effective_to": policy.effective_to.isoformat() if policy.effective_to else None,
        "governing_document_reference": policy.governing_document_reference,
        "configuration": policy.configuration,
        "schema_version": policy.schema_version,
        "notes": policy.notes,
        "submitted_at": policy.submitted_at.isoformat() if policy.submitted_at else None,
        "submitted_by": policy.submitted_by_id,
        "approved_at": policy.approved_at.isoformat() if policy.approved_at else None,
        "approved_by": policy.approved_by_id,
        "created_at": policy.created_at.isoformat() if policy.created_at else None,
        "updated_at": policy.updated_at.isoformat() if policy.updated_at else None,
        "stakeholders": [
            {
                "id": row.id,
                "ownership": row.ownership_id,
                "target_type": row.target_type,
                "target_name": row.target_name,
                "profit_percentage": str(row.profit_percentage) if row.profit_percentage is not None else None,
                "loss_percentage": str(row.loss_percentage) if row.loss_percentage is not None else None,
                "destination_account_preference": row.destination_account_preference,
                "configuration": row.configuration,
                "sort_order": row.sort_order,
            }
            for row in stakeholder_rows
        ],
    }
