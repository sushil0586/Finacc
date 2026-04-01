from rest_framework import serializers

from financial.models import accountHead, accounttype


class AccountTypeV2Serializer(serializers.ModelSerializer):
    accounttypeid = serializers.IntegerField(source="id", read_only=True)

    class Meta:
        model = accounttype
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
            errors["accounttypename"] = "Duplicate account type name for this entity."
        if qs.filter(accounttypecode__iexact=code).exists():
            errors["accounttypecode"] = "Duplicate account type code for this entity."
        if errors:
            raise serializers.ValidationError(errors)
        attrs["accounttypename"] = name
        attrs["accounttypecode"] = code
        return attrs


class AccountHeadV2Serializer(serializers.ModelSerializer):
    parent_name = serializers.CharField(source="accountheadsr.name", read_only=True)
    accounttype_name = serializers.CharField(source="accounttype.accounttypename", read_only=True)

    class Meta:
        model = accountHead
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
        if code in (None, ""):
            errors["code"] = "Account head code is required."
        if errors:
            raise serializers.ValidationError(errors)

        qs = accountHead.objects.filter(entity=entity)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.filter(code=code).exists():
            errors["code"] = "Duplicate account head code for this entity."
        if qs.filter(name__iexact=name).exists():
            errors["name"] = "Duplicate account head name for this entity."
        if errors:
            raise serializers.ValidationError(errors)
        attrs["name"] = name
        return attrs
