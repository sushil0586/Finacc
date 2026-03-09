from django.db import transaction
from rest_framework import serializers

from financial.models import Ledger, account
from financial.services import sync_ledger_for_account


class LedgerSerializer(serializers.ModelSerializer):
    account_profile_id = serializers.IntegerField(source="account_profile.id", read_only=True)
    account_profile_name = serializers.CharField(source="account_profile.accountname", read_only=True)
    account_profile_gstno = serializers.CharField(source="account_profile.gstno", read_only=True)
    account_profile_pan = serializers.CharField(source="account_profile.pan", read_only=True)

    class Meta:
        model = Ledger
        fields = (
            "id",
            "entity",
            "ledger_code",
            "name",
            "legal_name",
            "accounthead",
            "creditaccounthead",
            "contra_ledger",
            "accounttype",
            "is_party",
            "is_system",
            "canbedeleted",
            "openingbcr",
            "openingbdr",
            "isactive",
            "account_profile_id",
            "account_profile_name",
            "account_profile_gstno",
            "account_profile_pan",
        )


class LedgerSimpleSerializer(serializers.ModelSerializer):
    accountname = serializers.CharField(source="account_profile.accountname", read_only=True)

    class Meta:
        model = Ledger
        fields = ("id", "ledger_code", "name", "accountname", "accounthead", "is_party")


class LedgerBalanceRowSerializer(serializers.Serializer):
    ledger_id = serializers.IntegerField()
    account_id = serializers.IntegerField(allow_null=True)
    ledger_code = serializers.IntegerField(allow_null=True)
    ledger_name = serializers.CharField()
    accountname = serializers.CharField(allow_null=True)
    accgst = serializers.CharField(allow_null=True)
    accpan = serializers.CharField(allow_null=True)
    cityname = serializers.CharField(allow_null=True)
    accounthead_id = serializers.IntegerField(allow_null=True)
    accounthead_name = serializers.CharField(allow_null=True)
    creditaccounthead_id = serializers.IntegerField(allow_null=True)
    creditaccounthead_name = serializers.CharField(allow_null=True)
    accanbedeleted = serializers.BooleanField()
    balance = serializers.DecimalField(max_digits=18, decimal_places=2)
    debit = serializers.DecimalField(max_digits=18, decimal_places=2)
    credit = serializers.DecimalField(max_digits=18, decimal_places=2)
    drcr = serializers.CharField()
    is_party = serializers.BooleanField()


class BaseAccountListV2RowSerializer(serializers.Serializer):
    accountid = serializers.IntegerField()
    accountname = serializers.CharField()
    balance = serializers.DecimalField(max_digits=18, decimal_places=2)


class SimpleAccountV2Serializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source="account_profile.id", read_only=True)
    accounthead = serializers.IntegerField(source="accounthead_id", read_only=True)
    accountname = serializers.CharField(source="account_profile.accountname", read_only=True)
    accountcode = serializers.IntegerField(source="ledger_code", allow_null=True, read_only=True)
    state = serializers.IntegerField(source="account_profile.state_id", allow_null=True, read_only=True)
    statecode = serializers.CharField(source="account_profile.state.statecode", allow_null=True, read_only=True)
    district = serializers.IntegerField(source="account_profile.district_id", allow_null=True, read_only=True)
    city = serializers.IntegerField(source="account_profile.city_id", allow_null=True, read_only=True)
    pincode = serializers.CharField(source="account_profile.pincode", allow_null=True, read_only=True)
    gstno = serializers.CharField(source="account_profile.gstno", allow_null=True, read_only=True)
    pan = serializers.CharField(source="account_profile.pan", allow_null=True, read_only=True)
    saccode = serializers.CharField(source="account_profile.saccode", allow_null=True, read_only=True)

    class Meta:
        model = Ledger
        fields = (
            "id",
            "accounthead",
            "accountname",
            "accountcode",
            "state",
            "statecode",
            "district",
            "city",
            "pincode",
            "gstno",
            "pan",
            "saccode",
        )


class AccountListPostV2RowSerializer(serializers.Serializer):
    accountname = serializers.CharField()
    debit = serializers.DecimalField(max_digits=18, decimal_places=2)
    credit = serializers.DecimalField(max_digits=18, decimal_places=2)
    accgst = serializers.CharField(allow_null=True)
    accpan = serializers.CharField(allow_null=True)
    cityname = serializers.CharField(allow_null=True)
    accountid = serializers.IntegerField()
    daccountheadname = serializers.CharField(allow_null=True)
    caccountheadname = serializers.CharField(allow_null=True)
    accanbedeleted = serializers.BooleanField()
    balance = serializers.DecimalField(max_digits=18, decimal_places=2)
    drcr = serializers.CharField()


class AccountProfileLedgerInputSerializer(serializers.Serializer):
    ledger_code = serializers.IntegerField(required=False, allow_null=True)
    name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    legal_name = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    accounthead = serializers.IntegerField(required=False, allow_null=True)
    creditaccounthead = serializers.IntegerField(required=False, allow_null=True)
    contra_ledger = serializers.IntegerField(required=False, allow_null=True)
    accounttype = serializers.IntegerField(required=False, allow_null=True)
    openingbcr = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, allow_null=True)
    openingbdr = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, allow_null=True)
    canbedeleted = serializers.BooleanField(required=False)
    isactive = serializers.BooleanField(required=False)


class AccountProfileV2WriteSerializer(serializers.ModelSerializer):
    ledger = AccountProfileLedgerInputSerializer(required=False)

    class Meta:
        model = account
        fields = (
            "id",
            "entity",
            "accountname",
            "legalname",
            "partytype",
            "gstno",
            "pan",
            "emailid",
            "contactno",
            "contactno2",
            "contactperson",
            "gstintype",
            "gstregtype",
            "is_sez",
            "tdsno",
            "tdsrate",
            "tdssection",
            "tds_threshold",
            "istcsapplicable",
            "tcscode",
            "creditlimit",
            "creditdays",
            "paymentterms",
            "currency",
            "blockstatus",
            "blockedreason",
            "isactive",
            "approved",
            "country",
            "state",
            "district",
            "city",
            "pincode",
            "address1",
            "address2",
            "addressfloorno",
            "addressstreet",
            "bankname",
            "banKAcno",
            "rtgsno",
            "saccode",
            "adhaarno",
            "msme",
            "gsttdsno",
            "sharepercentage",
            "composition",
            "tobel10cr",
            "isaddsameasbillinf",
            "website",
            "reminders",
            "dateofreg",
            "dateofdreg",
            "ledger",
        )

    @transaction.atomic
    def create(self, validated_data):
        ledger_data = validated_data.pop("ledger", {}) or {}
        request = self.context.get("request")
        if request and getattr(request, "user", None) and request.user.is_authenticated:
            validated_data["createdby"] = request.user

        validated_data["accountcode"] = ledger_data.get("ledger_code")
        validated_data["accounthead_id"] = ledger_data.get("accounthead")
        validated_data["creditaccounthead_id"] = ledger_data.get("creditaccounthead")
        validated_data["accounttype_id"] = ledger_data.get("accounttype")
        validated_data["openingbcr"] = ledger_data.get("openingbcr")
        validated_data["openingbdr"] = ledger_data.get("openingbdr")
        validated_data["canbedeleted"] = ledger_data.get("canbedeleted", True)
        if "isactive" in ledger_data:
            validated_data["isactive"] = ledger_data["isactive"]
        if ledger_data.get("legal_name") and not validated_data.get("legalname"):
            validated_data["legalname"] = ledger_data["legal_name"]

        acc = account.objects.create(**validated_data)
        sync_ledger_for_account(
            acc,
            ledger_overrides={
                "ledger_code": ledger_data.get("ledger_code"),
                "name": ledger_data.get("name") or acc.accountname,
                "legal_name": ledger_data.get("legal_name") or acc.legalname,
                "accounthead_id": ledger_data.get("accounthead"),
                "creditaccounthead_id": ledger_data.get("creditaccounthead"),
                "contra_ledger_id": ledger_data.get("contra_ledger"),
                "accounttype_id": ledger_data.get("accounttype"),
                "openingbcr": ledger_data.get("openingbcr"),
                "openingbdr": ledger_data.get("openingbdr"),
                "canbedeleted": ledger_data.get("canbedeleted", acc.canbedeleted),
                "is_party": True,
                "isactive": ledger_data.get("isactive", acc.isactive),
            },
        )
        return acc

    @transaction.atomic
    def update(self, instance, validated_data):
        ledger_data = validated_data.pop("ledger", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)

        if ledger_data:
            if "ledger_code" in ledger_data:
                instance.accountcode = ledger_data.get("ledger_code")
            if "accounthead" in ledger_data:
                instance.accounthead_id = ledger_data.get("accounthead")
            if "creditaccounthead" in ledger_data:
                instance.creditaccounthead_id = ledger_data.get("creditaccounthead")
            if "accounttype" in ledger_data:
                instance.accounttype_id = ledger_data.get("accounttype")
            if "openingbcr" in ledger_data:
                instance.openingbcr = ledger_data.get("openingbcr")
            if "openingbdr" in ledger_data:
                instance.openingbdr = ledger_data.get("openingbdr")
            if "canbedeleted" in ledger_data:
                instance.canbedeleted = ledger_data.get("canbedeleted")
            if "legal_name" in ledger_data and ledger_data.get("legal_name") and not instance.legalname:
                instance.legalname = ledger_data.get("legal_name")

        request = self.context.get("request")
        if request and getattr(request, "user", None) and request.user.is_authenticated:
            instance.createdby = request.user

        instance.save()
        sync_ledger_for_account(
            instance,
            ledger_overrides={
                "ledger_code": ledger_data.get("ledger_code") if ledger_data else None,
                "name": (ledger_data.get("name") if ledger_data else None) or instance.accountname,
                "legal_name": (ledger_data.get("legal_name") if ledger_data else None) or instance.legalname,
                "accounthead_id": ledger_data.get("accounthead") if ledger_data else None,
                "creditaccounthead_id": ledger_data.get("creditaccounthead") if ledger_data else None,
                "contra_ledger_id": ledger_data.get("contra_ledger") if ledger_data else None,
                "accounttype_id": ledger_data.get("accounttype") if ledger_data else None,
                "openingbcr": ledger_data.get("openingbcr") if ledger_data else None,
                "openingbdr": ledger_data.get("openingbdr") if ledger_data else None,
                "canbedeleted": ledger_data.get("canbedeleted") if ledger_data else instance.canbedeleted,
                "is_party": True,
                "isactive": ledger_data.get("isactive") if ledger_data and "isactive" in ledger_data else instance.isactive,
            },
        )
        return instance


class AccountProfileV2ReadSerializer(serializers.ModelSerializer):
    ledger = LedgerSerializer(read_only=True)

    class Meta:
        model = account
        fields = (
            "id",
            "entity",
            "accountname",
            "legalname",
            "partytype",
            "gstno",
            "pan",
            "emailid",
            "contactno",
            "contactno2",
            "contactperson",
            "gstintype",
            "gstregtype",
            "is_sez",
            "tdsno",
            "tdsrate",
            "tdssection",
            "tds_threshold",
            "istcsapplicable",
            "tcscode",
            "creditlimit",
            "creditdays",
            "paymentterms",
            "currency",
            "blockstatus",
            "blockedreason",
            "isactive",
            "approved",
            "country",
            "state",
            "district",
            "city",
            "pincode",
            "address1",
            "address2",
            "addressfloorno",
            "addressstreet",
            "bankname",
            "banKAcno",
            "rtgsno",
            "saccode",
            "adhaarno",
            "msme",
            "gsttdsno",
            "sharepercentage",
            "composition",
            "tobel10cr",
            "isaddsameasbillinf",
            "website",
            "reminders",
            "dateofreg",
            "dateofdreg",
            "ledger",
        )
