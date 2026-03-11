from django.db import transaction
from rest_framework import serializers

from financial.models import Ledger, account
from financial.services import allocate_next_ledger_code, sync_ledger_for_account


class LedgerSerializer(serializers.ModelSerializer):
    account_profile_id = serializers.IntegerField(source="account_profile.id", read_only=True)
    account_profile_name = serializers.CharField(source="account_profile.accountname", read_only=True)
    account_profile_gstno = serializers.CharField(source="account_profile.gstno", read_only=True)
    account_profile_pan = serializers.CharField(source="account_profile.pan", read_only=True)
    management_mode = serializers.SerializerMethodField()

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
            "management_mode",
        )

    def get_management_mode(self, obj):
        return "auto_managed" if getattr(obj, "account_profile_id", None) else "direct"


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
    # Transitional compatibility only.
    # New account screens should not directly edit the nested ledger payload.
    # Use the flat account-facing accounting fields exposed by
    # AccountProfileV2WriteSerializer instead.
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
    # New account APIs are account-centric: backend auto-manages the linked
    # ledger. These flat fields define the accounting classification for the
    # generated/synchronized ledger without forcing the UI to act like a ledger
    # editor.
    ledger_code = serializers.IntegerField(required=False, allow_null=True, write_only=True)
    accounthead = serializers.IntegerField(required=False, allow_null=True, write_only=True)
    creditaccounthead = serializers.IntegerField(required=False, allow_null=True, write_only=True)
    contra_ledger = serializers.IntegerField(required=False, allow_null=True, write_only=True)
    accounttype = serializers.IntegerField(required=False, allow_null=True, write_only=True)
    openingbcr = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, allow_null=True, write_only=True)
    openingbdr = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, allow_null=True, write_only=True)
    canbedeleted = serializers.BooleanField(required=False, write_only=True)
    ledger = AccountProfileLedgerInputSerializer(required=False, write_only=True)

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
            "ledger_code",
            "accounthead",
            "creditaccounthead",
            "contra_ledger",
            "accounttype",
            "openingbcr",
            "openingbdr",
            "canbedeleted",
            "ledger",
        )

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance is None and not attrs.get("entity"):
            raise serializers.ValidationError({"entity": "Entity is required."})
        if self.instance is None and not attrs.get("accountname"):
            raise serializers.ValidationError({"accountname": "Account name is required."})
        accounthead_value = attrs.get("accounthead")
        nested_accounthead_value = attrs.get("ledger", {}).get("accounthead")
        if accounthead_value in (0, "0", ""):
            attrs["accounthead"] = None
            accounthead_value = None
        if nested_accounthead_value in (0, "0", ""):
            attrs.setdefault("ledger", {})["accounthead"] = None
            nested_accounthead_value = None
        if self.instance is None and not (accounthead_value or nested_accounthead_value):
            raise serializers.ValidationError({"accounthead": "Account head is required."})
        return attrs

    @staticmethod
    def _normalize_fk_value(value):
        return None if value in (0, "0", "") else value

    def _resolve_accounting_payload(self, validated_data):
        ledger_data = validated_data.pop("ledger", {}) or {}
        accounting = {}
        field_names = (
            "ledger_code",
            "accounthead",
            "creditaccounthead",
            "contra_ledger",
            "accounttype",
            "openingbcr",
            "openingbdr",
            "canbedeleted",
        )
        for field_name in field_names:
            if field_name in validated_data:
                accounting[field_name] = self._normalize_fk_value(validated_data.pop(field_name))
            elif field_name in ledger_data:
                accounting[field_name] = self._normalize_fk_value(ledger_data.get(field_name))
        if "isactive" in ledger_data:
            accounting["isactive"] = ledger_data.get("isactive")
        return accounting

    @transaction.atomic
    def create(self, validated_data):
        accounting = self._resolve_accounting_payload(validated_data)
        request = self.context.get("request")
        if request and getattr(request, "user", None) and request.user.is_authenticated:
            validated_data["createdby"] = request.user

        ledger_code = accounting.get("ledger_code")
        if ledger_code is None and validated_data.get("entity"):
            ledger_code = allocate_next_ledger_code(entity_id=validated_data["entity"].id)

        validated_data["accountcode"] = ledger_code
        validated_data["accounthead_id"] = accounting.get("accounthead")
        validated_data["creditaccounthead_id"] = accounting.get("creditaccounthead")
        validated_data["accounttype_id"] = accounting.get("accounttype")
        validated_data["openingbcr"] = accounting.get("openingbcr")
        validated_data["openingbdr"] = accounting.get("openingbdr")
        validated_data["canbedeleted"] = accounting.get("canbedeleted", True)
        if accounting.get("isactive") is not None:
            validated_data["isactive"] = accounting["isactive"]

        acc = account.objects.create(**validated_data)
        sync_ledger_for_account(
            acc,
            ledger_overrides={
                "ledger_code": ledger_code,
                "name": acc.accountname,
                "legal_name": acc.legalname,
                "accounthead_id": accounting.get("accounthead"),
                "creditaccounthead_id": accounting.get("creditaccounthead"),
                "contra_ledger_id": accounting.get("contra_ledger"),
                "accounttype_id": accounting.get("accounttype"),
                "openingbcr": accounting.get("openingbcr"),
                "openingbdr": accounting.get("openingbdr"),
                "canbedeleted": accounting.get("canbedeleted", acc.canbedeleted),
                "is_party": True,
                "isactive": accounting.get("isactive", acc.isactive),
            },
        )
        return acc

    @transaction.atomic
    def update(self, instance, validated_data):
        accounting = self._resolve_accounting_payload(validated_data)
        for field, value in validated_data.items():
            setattr(instance, field, value)

        if "ledger_code" in accounting and accounting.get("ledger_code") is not None:
            instance.accountcode = accounting.get("ledger_code")
        elif instance.accountcode is None and instance.entity_id:
            instance.accountcode = allocate_next_ledger_code(entity_id=instance.entity_id)
        if "accounthead" in accounting:
            instance.accounthead_id = accounting.get("accounthead")
        if "creditaccounthead" in accounting:
            instance.creditaccounthead_id = accounting.get("creditaccounthead")
        if "accounttype" in accounting:
            instance.accounttype_id = accounting.get("accounttype")
        if "openingbcr" in accounting:
            instance.openingbcr = accounting.get("openingbcr")
        if "openingbdr" in accounting:
            instance.openingbdr = accounting.get("openingbdr")
        if "canbedeleted" in accounting:
            instance.canbedeleted = accounting.get("canbedeleted")

        request = self.context.get("request")
        if request and getattr(request, "user", None) and request.user.is_authenticated:
            instance.createdby = request.user

        instance.save()
        sync_ledger_for_account(
            instance,
            ledger_overrides={
                "ledger_code": instance.accountcode,
                "name": instance.accountname,
                "legal_name": instance.legalname,
                "accounthead_id": instance.accounthead_id,
                "creditaccounthead_id": instance.creditaccounthead_id,
                "contra_ledger_id": accounting.get("contra_ledger") if "contra_ledger" in accounting else None,
                "accounttype_id": instance.accounttype_id,
                "openingbcr": instance.openingbcr,
                "openingbdr": instance.openingbdr,
                "canbedeleted": instance.canbedeleted,
                "is_party": True,
                "isactive": accounting.get("isactive") if accounting.get("isactive") is not None else instance.isactive,
            },
        )
        return instance


class AccountProfileV2ReadSerializer(serializers.ModelSerializer):
    ledger = LedgerSerializer(read_only=True)
    ledger_mode = serializers.SerializerMethodField()

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
            "ledger_mode",
            "ledger",
        )

    def get_ledger_mode(self, obj):
        return "auto_managed"
