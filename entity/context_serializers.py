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

