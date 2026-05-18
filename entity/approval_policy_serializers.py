from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from entity.models import EntityApprovalPolicy


class EntityApprovalPolicySerializer(serializers.ModelSerializer):
    entity_name = serializers.CharField(source="entity.entityname", read_only=True)
    subentity_name = serializers.CharField(source="subentity.subentityname", read_only=True, allow_null=True)
    org_unit_name = serializers.CharField(source="org_unit.name", read_only=True, allow_null=True)
    org_unit_type = serializers.CharField(source="org_unit.unit_type", read_only=True, allow_null=True)
    policy_key_label = serializers.CharField(source="get_policy_key_display", read_only=True)
    approval_mode_label = serializers.CharField(source="get_approval_mode_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = EntityApprovalPolicy
        fields = [
            "id",
            "entity",
            "entity_name",
            "subentity",
            "subentity_name",
            "org_unit",
            "org_unit_name",
            "org_unit_type",
            "policy_key",
            "policy_key_label",
            "code",
            "name",
            "approval_mode",
            "approval_mode_label",
            "manager_levels",
            "min_approvers",
            "approver_roles",
            "approver_permissions",
            "fallback_manager_required",
            "status",
            "status_label",
            "effective_from",
            "effective_to",
            "metadata",
        ]

    def create(self, validated_data):
        try:
            return super().create(validated_data)
        except DjangoValidationError as err:
            raise serializers.ValidationError(err.message_dict if hasattr(err, "message_dict") else {"detail": err.messages})

    def update(self, instance, validated_data):
        try:
            return super().update(instance, validated_data)
        except DjangoValidationError as err:
            raise serializers.ValidationError(err.message_dict if hasattr(err, "message_dict") else {"detail": err.messages})


class EntityApprovalPolicyMetaSerializer(serializers.Serializer):
    policy_keys = serializers.ListField(child=serializers.DictField())
    approval_modes = serializers.ListField(child=serializers.DictField())
    statuses = serializers.ListField(child=serializers.DictField())
    resolution_modes = serializers.ListField(child=serializers.DictField())
