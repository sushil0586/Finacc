from rest_framework import serializers

from financial.models import accountHead, accounttype
from financial.services import allocate_next_account_head_code

_INT32_MAX = 2147483647


class AccountTypeV2Serializer(serializers.ModelSerializer):
    accounttypename = serializers.CharField(max_length=255)
    accounttypecode = serializers.CharField(max_length=255)
    accounttypeid = serializers.IntegerField(source="id", read_only=True)

    class Meta:
        model = accounttype
        validators = []
        fields = (
            "id",
            "accounttypeid",
            "accounttypename",
            "accounttypecode",
            "balanceType",
            "entity",
            "isactive",
        )

    def validate(self, attrs):
        attrs = super().validate(attrs)
        entity = attrs.get("entity", getattr(self.instance, "entity", None))
        name = attrs.get("accounttypename", getattr(self.instance, "accounttypename", ""))
        code = attrs.get("accounttypecode", getattr(self.instance, "accounttypecode", ""))
        name = (name or "").strip()
        code = (code or "").strip()

        errors = {}
        if not name:
            errors["accounttypename"] = "Account type name is required."
        if not code:
            errors["accounttypecode"] = "Account type code is required."
        if errors:
            raise serializers.ValidationError(errors)

        qs = accounttype.objects.filter(entity=entity)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.filter(accounttypename__iexact=name).exists():
            errors["accounttypename"] = "An account type with this name already exists."
        if qs.filter(accounttypecode__iexact=code).exists():
            errors["accounttypecode"] = "An account type with this code already exists."
        if errors:
            raise serializers.ValidationError(errors)
        attrs["accounttypename"] = name
        attrs["accounttypecode"] = code
        return attrs


class AccountHeadV2Serializer(serializers.ModelSerializer):
    name = serializers.CharField(max_length=200)
    code = serializers.IntegerField(required=False, allow_null=True, max_value=_INT32_MAX)
    description = serializers.CharField(max_length=200, required=False, allow_null=True, allow_blank=True)
    detailsingroup = serializers.IntegerField(required=False, allow_null=True, max_value=_INT32_MAX)
    parent_name = serializers.CharField(source="accountheadsr.name", read_only=True)
    accounttype_name = serializers.CharField(source="accounttype.accounttypename", read_only=True)

    class Meta:
        model = accountHead
        validators = []
        fields = (
            "id",
            "name",
            "code",
            "detailsingroup",
            "balanceType",
            "drcreffect",
            "description",
            "accountheadsr",
            "parent_name",
            "entity",
            "accounttype",
            "accounttype_name",
            "canbedeleted",
            "isactive",
        )

    def validate(self, attrs):
        attrs = super().validate(attrs)
        entity = attrs.get("entity", getattr(self.instance, "entity", None))
        name = attrs.get("name", getattr(self.instance, "name", ""))
        code = attrs.get("code", getattr(self.instance, "code", None))
        name = (name or "").strip()

        errors = {}
        if not name:
            errors["name"] = "Account head name is required."
        if errors:
            raise serializers.ValidationError(errors)

        qs = accountHead.objects.filter(entity=entity)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        normalized_code = None if code in (None, "", 0) else code
        if normalized_code is not None and qs.filter(code=normalized_code).exists():
            errors["code"] = "An account head with this code already exists."
        if qs.filter(name__iexact=name).exists():
            errors["name"] = "An account head with this name already exists."
        if errors:
            raise serializers.ValidationError(errors)
        attrs["name"] = name
        attrs["code"] = normalized_code
        return attrs

    def create(self, validated_data):
        if validated_data.get("code") in (None, "", 0):
            entity = validated_data.get("entity")
            if entity is None:
                raise serializers.ValidationError({"entity": "Entity is required."})
            validated_data["code"] = allocate_next_account_head_code(entity_id=entity.id)
        return super().create(validated_data)
