from rest_framework import serializers


class EntityContextRoleSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    code = serializers.CharField(allow_blank=True)
    source = serializers.CharField()
    is_primary = serializers.BooleanField(default=False)


class EntityContextSerializer(serializers.Serializer):
    entityid = serializers.IntegerField()
    entityname = serializers.CharField()
    gstno = serializers.CharField(allow_null=True, allow_blank=True)
    email = serializers.EmailField()
    role = serializers.CharField(allow_blank=True)
    roleid = serializers.IntegerField(allow_null=True)
    roles = EntityContextRoleSerializer(many=True)
    default_entityfinid = serializers.IntegerField(allow_null=True, required=False)
    default_subentity = serializers.IntegerField(allow_null=True, required=False)
    default_subentity_id = serializers.IntegerField(allow_null=True, required=False)
    financial_years = serializers.ListField(child=serializers.DictField(), required=False)
    subentities = serializers.ListField(child=serializers.DictField(), required=False)


class EntityFinancialYearOptionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    desc = serializers.CharField(allow_null=True, allow_blank=True)
    year_code = serializers.CharField(allow_null=True, allow_blank=True)
    assessment_year_label = serializers.CharField(allow_null=True, allow_blank=True)
    finstartyear = serializers.DateTimeField(allow_null=True)
    finendyear = serializers.DateTimeField(allow_null=True)
    isactive = serializers.BooleanField()


class SubEntityOptionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    subentityname = serializers.CharField()
    subentity_code = serializers.CharField(allow_null=True, allow_blank=True)
    is_head_office = serializers.BooleanField()
    branch_type = serializers.CharField()


class UserContextSelectionSerializer(serializers.Serializer):
    entity_id = serializers.IntegerField()
    entityfinid = serializers.IntegerField(allow_null=True)
    subentity = serializers.IntegerField(allow_null=True)
