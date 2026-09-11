from __future__ import annotations

from rest_framework import serializers

from entity.models import EntityOwnershipV2
from financial.models import account

from .models import (
    CapitalDistributionRun,
    CapitalDistributionTaxWorking,
    DistributionPolicyStakeholder,
    FormationType,
    TaxPolicyVersion,
)


class EntityScopeSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    entityfinid = serializers.IntegerField(required=False, allow_null=True)
    subentity = serializers.IntegerField(required=False, allow_null=True)


class FormationResolveSerializer(EntityScopeSerializer):
    effective_from = serializers.DateField(required=False, allow_null=True)


class WaveOneMigrationSerializer(EntityScopeSerializer):
    entityfinid = serializers.IntegerField()


class WaveOneActivationSerializer(WaveOneMigrationSerializer):
    enabled = serializers.BooleanField()


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


class TaxPolicyWriteSerializer(EntityScopeSerializer):
    formation_profile = serializers.IntegerField()
    tax_type = serializers.ChoiceField(choices=TaxPolicyVersion.TaxType.choices, default="income_tax")
    policy_code = serializers.RegexField(regex=r"^[A-Za-z0-9][A-Za-z0-9 _-]{1,79}$", max_length=80)
    jurisdiction_country = serializers.RegexField(regex=r"^[A-Za-z]{2}$", default="IN")
    jurisdiction_state = serializers.RegexField(
        regex=r"^[A-Za-z0-9-]{0,10}$",
        required=False,
        allow_blank=True,
        default="",
    )
    effective_from = serializers.DateField()
    effective_to = serializers.DateField(required=False, allow_null=True)
    statutory_reference = serializers.CharField(max_length=255)
    source_url = serializers.URLField(max_length=500, required=False, allow_blank=True, default="")
    source_published_on = serializers.DateField(required=False, allow_null=True)
    configuration = serializers.JSONField()
    schema_version = serializers.IntegerField(required=False, min_value=1, default=1)
    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        if attrs.get("effective_to") and attrs["effective_from"] > attrs["effective_to"]:
            raise serializers.ValidationError({
                "effective_to": "Effective end date must be on or after effective start date."
            })
        return attrs


class TaxPolicyPatchSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    expected_updated_at = serializers.DateTimeField()
    entityfinid = serializers.IntegerField(required=False, allow_null=True)
    tax_type = serializers.ChoiceField(choices=TaxPolicyVersion.TaxType.choices, required=False)
    effective_from = serializers.DateField(required=False)
    effective_to = serializers.DateField(required=False, allow_null=True)
    statutory_reference = serializers.CharField(max_length=255, required=False)
    source_url = serializers.URLField(max_length=500, required=False, allow_blank=True)
    source_published_on = serializers.DateField(required=False, allow_null=True)
    configuration = serializers.JSONField(required=False)
    schema_version = serializers.IntegerField(required=False, min_value=1)
    notes = serializers.CharField(required=False, allow_blank=True)


class TaxWorkingCalculateSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    run = serializers.IntegerField()
    tax_policy = serializers.IntegerField()
    idempotency_key = serializers.CharField(max_length=80)


class TaxWorkingLineOverrideSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    expected_updated_at = serializers.DateTimeField()
    allowable_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    reason = serializers.CharField(max_length=500)
    evidence_references = serializers.ListField(child=serializers.JSONField(), allow_empty=False)


class TaxWorkingActionSerializer(serializers.Serializer):
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


def serialize_tax_policy(policy: TaxPolicyVersion) -> dict:
    return {
        "id": policy.id,
        "entity": policy.entity_id,
        "entityfinid": policy.entityfin_id,
        "formation_profile": policy.formation_profile_id,
        "formation_type": policy.formation_type,
        "formation_label": FormationType(policy.formation_type).label,
        "tax_type": policy.tax_type,
        "policy_code": policy.policy_code,
        "version_number": policy.version_number,
        "status": policy.status,
        "jurisdiction_country": policy.jurisdiction_country,
        "jurisdiction_state": policy.jurisdiction_state,
        "effective_from": policy.effective_from.isoformat(),
        "effective_to": policy.effective_to.isoformat() if policy.effective_to else None,
        "statutory_reference": policy.statutory_reference,
        "source_url": policy.source_url,
        "source_published_on": policy.source_published_on.isoformat() if policy.source_published_on else None,
        "configuration": policy.configuration,
        "schema_version": policy.schema_version,
        "notes": policy.notes,
        "submitted_at": policy.submitted_at.isoformat() if policy.submitted_at else None,
        "submitted_by": policy.submitted_by_id,
        "approved_at": policy.approved_at.isoformat() if policy.approved_at else None,
        "approved_by": policy.approved_by_id,
        "created_at": policy.created_at.isoformat() if policy.created_at else None,
        "updated_at": policy.updated_at.isoformat() if policy.updated_at else None,
    }


def serialize_tax_working(working: CapitalDistributionTaxWorking) -> dict:
    return {
        "id": working.id,
        "entity": working.entity_id,
        "entityfinid": working.entityfin_id,
        "subentity": working.subentity_id,
        "run": working.run_id,
        "tax_policy": working.tax_policy_id,
        "tax_policy_code": working.policy_snapshot.get("policy_code"),
        "tax_policy_version": working.policy_snapshot.get("version_number"),
        "period_from": working.period_from.isoformat(),
        "period_to": working.period_to.isoformat(),
        "status": working.status,
        "idempotency_key": working.idempotency_key,
        "calculation_hash": working.calculation_hash,
        "source_snapshot": working.source_snapshot,
        "policy_snapshot": working.policy_snapshot,
        "book_amount": str(working.book_amount),
        "allowable_amount": str(working.allowable_amount),
        "disallowed_amount": str(working.disallowed_amount),
        "calculated_at": working.calculated_at.isoformat() if working.calculated_at else None,
        "calculated_by": working.calculated_by_id,
        "submitted_at": working.submitted_at.isoformat() if working.submitted_at else None,
        "submitted_by": working.submitted_by_id,
        "approved_at": working.approved_at.isoformat() if working.approved_at else None,
        "approved_by": working.approved_by_id,
        "reversed_at": working.reversed_at.isoformat() if working.reversed_at else None,
        "reversed_by": working.reversed_by_id,
        "lifecycle_reason": working.lifecycle_reason,
        "created_at": working.created_at.isoformat() if working.created_at else None,
        "updated_at": working.updated_at.isoformat() if working.updated_at else None,
        "lines": [
            {
                "id": line.id,
                "source_line": line.source_line_id,
                "component_type": line.component_type,
                "stakeholder_name": line.stakeholder_name,
                "book_amount": str(line.book_amount),
                "treatment": line.treatment,
                "calculated_allowable_amount": str(line.calculated_allowable_amount),
                "calculated_disallowed_amount": str(line.calculated_disallowed_amount),
                "override_allowable_amount": (
                    str(line.override_allowable_amount) if line.override_allowable_amount is not None else None
                ),
                "allowable_amount": str(line.allowable_amount),
                "disallowed_amount": str(line.disallowed_amount),
                "rule_snapshot": line.rule_snapshot,
                "source_snapshot": line.source_snapshot,
                "override_reason": line.override_reason,
                "evidence_references": line.evidence_references,
                "overridden_at": line.overridden_at.isoformat() if line.overridden_at else None,
                "overridden_by": line.overridden_by_id,
            }
            for line in working.lines.all()
        ],
    }
