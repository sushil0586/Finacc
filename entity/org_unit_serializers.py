from rest_framework import serializers

from entity.models import EntityOrgUnit


class EntityOrgUnitSerializer(serializers.ModelSerializer):
    entity_name = serializers.CharField(source="entity.entityname", read_only=True)
    subentity_name = serializers.CharField(source="subentity.subentityname", read_only=True, allow_null=True)
    parent_name = serializers.CharField(source="parent.name", read_only=True, allow_null=True)
    is_shared = serializers.SerializerMethodField()

    class Meta:
        model = EntityOrgUnit
        fields = [
            "id",
            "entity",
            "entity_name",
            "subentity",
            "subentity_name",
            "unit_type",
            "code",
            "name",
            "short_name",
            "description",
            "parent",
            "parent_name",
            "manager_title",
            "status",
            "effective_from",
            "effective_to",
            "sort_order",
            "metadata",
            "is_shared",
        ]

    def get_is_shared(self, obj):
        return obj.subentity_id is None

    def validate(self, attrs):
        instance = getattr(self, "instance", None)
        entity = attrs.get("entity") or getattr(instance, "entity", None)
        subentity = attrs.get("subentity", getattr(instance, "subentity", None))
        parent = attrs.get("parent", getattr(instance, "parent", None))

        if subentity and entity and subentity.entity_id != entity.id:
            raise serializers.ValidationError({"subentity": "Subentity must belong to the selected entity."})

        if parent and entity and parent.entity_id != entity.id:
            raise serializers.ValidationError({"parent": "Parent unit must belong to the selected entity."})

        if parent and subentity and parent.subentity_id not in (None, subentity.id):
            raise serializers.ValidationError({"parent": "Parent unit must be shared or belong to the same subentity."})

        if (
            attrs.get("effective_from") is not None
            and attrs.get("effective_to") is not None
            and attrs["effective_from"] > attrs["effective_to"]
        ):
            raise serializers.ValidationError({"effective_to": "Effective end date must be on or after effective start date."})

        return attrs


class EntityOrgUnitMetaSerializer(serializers.Serializer):
    unit_types = serializers.ListField(child=serializers.DictField())
    resolution_modes = serializers.ListField(child=serializers.DictField())
