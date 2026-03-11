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
