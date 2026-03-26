from django.db import transaction
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from financial.gstin import validate_financial_gstin
from financial.models import Ledger, account
from financial.profile_access import account_primary_address
from financial.services import (
    allocate_next_ledger_code,
    apply_normalized_profile_payload,
    create_account_with_synced_ledger,
    sync_ledger_for_account,
)


class LedgerSerializer(serializers.ModelSerializer):
    account_profile_id = serializers.IntegerField(source="account_profile.id", read_only=True)
    account_profile_name = serializers.CharField(source="account_profile.accountname", read_only=True)
    account_profile_gstno = serializers.SerializerMethodField()
    account_profile_pan = serializers.SerializerMethodField()
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
        return "auto_managed" if hasattr(obj, "account_profile") else "direct"

    def get_account_profile_gstno(self, obj):
        acc = getattr(obj, "account_profile", None)
        if not acc:
            return None
        compliance = getattr(acc, "compliance_profile", None)
        return getattr(compliance, "gstno", None)

    def get_account_profile_pan(self, obj):
        acc = getattr(obj, "account_profile", None)
        if not acc:
            return None
        compliance = getattr(acc, "compliance_profile", None)
        return getattr(compliance, "pan", None)


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
    state = serializers.SerializerMethodField()
    statecode = serializers.SerializerMethodField()
    district = serializers.SerializerMethodField()
    city = serializers.SerializerMethodField()
    pincode = serializers.SerializerMethodField()
    gstno = serializers.SerializerMethodField()
    pan = serializers.SerializerMethodField()
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

    def get_gstno(self, obj):
        acc = getattr(obj, "account_profile", None)
        if not acc:
            return None
        compliance = getattr(acc, "compliance_profile", None)
        return getattr(compliance, "gstno", None)

    def get_pan(self, obj):
        acc = getattr(obj, "account_profile", None)
        if not acc:
            return None
        compliance = getattr(acc, "compliance_profile", None)
        return getattr(compliance, "pan", None)

    @staticmethod
    def _primary_address(obj):
        acc = getattr(obj, "account_profile", None)
        if not acc:
            return None
        return account_primary_address(acc)

    def get_state(self, obj):
        address = self._primary_address(obj)
        return getattr(address, "state_id", None)

    def get_statecode(self, obj):
        address = self._primary_address(obj)
        state = getattr(address, "state", None)
        return getattr(state, "statecode", None)

    def get_district(self, obj):
        address = self._primary_address(obj)
        return getattr(address, "district_id", None)

    def get_city(self, obj):
        address = self._primary_address(obj)
        return getattr(address, "city_id", None)

    def get_pincode(self, obj):
        address = self._primary_address(obj)
        return getattr(address, "pincode", None)


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
    compliance_profile = serializers.DictField(required=False, write_only=True)
    commercial_profile = serializers.DictField(required=False, write_only=True)
    primary_address = serializers.DictField(required=False, write_only=True)

    class Meta:
        model = account
        validators = []
        fields = (
            "id",
            "entity",
            "accountname",
            "legalname",
            "emailid",
            "contactno",
            "contactno2",
            "contactperson",
            "isactive",
            "bankname",
            "banKAcno",
            "rtgsno",
            "saccode",
            "adhaarno",
            "sharepercentage",
            "composition",
            "tobel10cr",
            "isaddsameasbillinf",
            "website",
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
            "compliance_profile",
            "commercial_profile",
            "primary_address",
        )

    def validate(self, attrs):
        unknown_fields = sorted(set(getattr(self, "initial_data", {}).keys()) - set(self.fields.keys()))
        if unknown_fields:
            raise serializers.ValidationError({field: "This field is not allowed." for field in unknown_fields})
        attrs = super().validate(attrs)
        compliance = dict(attrs.get("compliance_profile", {}) or {})
        if "gstno" in compliance:
            try:
                compliance["gstno"] = validate_financial_gstin(compliance.get("gstno"))
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"compliance_profile": {"gstno": exc.messages[0]}})
            attrs["compliance_profile"] = compliance
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

    def _extract_normalized_profile_payload(self, validated_data):
        compliance = dict(validated_data.pop("compliance_profile", {}) or {})
        commercial = dict(validated_data.pop("commercial_profile", {}) or {})
        primary_address = dict(validated_data.pop("primary_address", {}) or {})

        return compliance, commercial, primary_address

    @transaction.atomic
    def create(self, validated_data):
        accounting = self._resolve_accounting_payload(validated_data)
        compliance_payload, commercial_payload, primary_address_payload = self._extract_normalized_profile_payload(
            validated_data
        )
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

        acc = create_account_with_synced_ledger(
            account_data=validated_data,
            ledger_overrides={
                "ledger_code": ledger_code,
                "name": validated_data.get("accountname"),
                "legal_name": validated_data.get("legalname"),
                "accounthead_id": accounting.get("accounthead"),
                "creditaccounthead_id": accounting.get("creditaccounthead"),
                "contra_ledger_id": accounting.get("contra_ledger"),
                "accounttype_id": accounting.get("accounttype"),
                "openingbcr": accounting.get("openingbcr"),
                "openingbdr": accounting.get("openingbdr"),
                "canbedeleted": accounting.get("canbedeleted", validated_data.get("canbedeleted", True)),
                "is_party": True,
                "isactive": accounting.get("isactive", validated_data.get("isactive", True)),
            },
        )
        apply_normalized_profile_payload(
            acc,
            compliance_data=compliance_payload if compliance_payload else {},
            commercial_data=commercial_payload if commercial_payload else {},
            primary_address_data=primary_address_payload if primary_address_payload else None,
            createdby=validated_data.get("createdby"),
        )
        return acc

    @transaction.atomic
    def update(self, instance, validated_data):
        accounting = self._resolve_accounting_payload(validated_data)
        compliance_payload, commercial_payload, primary_address_payload = self._extract_normalized_profile_payload(
            validated_data
        )
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
        request = self.context.get("request")
        actor = request.user if request and getattr(request, "user", None) and request.user.is_authenticated else instance.createdby
        apply_normalized_profile_payload(
            instance,
            compliance_data=compliance_payload if compliance_payload else {},
            commercial_data=commercial_payload if commercial_payload else {},
            primary_address_data=primary_address_payload if primary_address_payload else None,
            createdby=actor,
        )
        return instance


class AccountProfileV2ReadSerializer(serializers.ModelSerializer):
    ledger = LedgerSerializer(read_only=True)
    ledger_mode = serializers.SerializerMethodField()
    partytype = serializers.SerializerMethodField()
    gstno = serializers.SerializerMethodField()
    pan = serializers.SerializerMethodField()
    gstintype = serializers.SerializerMethodField()
    gstregtype = serializers.SerializerMethodField()
    is_sez = serializers.SerializerMethodField()
    tdsno = serializers.SerializerMethodField()
    tdsrate = serializers.SerializerMethodField()
    tdssection = serializers.SerializerMethodField()
    tds_threshold = serializers.SerializerMethodField()
    istcsapplicable = serializers.SerializerMethodField()
    tcscode = serializers.SerializerMethodField()
    creditlimit = serializers.SerializerMethodField()
    creditdays = serializers.SerializerMethodField()
    paymentterms = serializers.SerializerMethodField()
    currency = serializers.SerializerMethodField()
    blockstatus = serializers.SerializerMethodField()
    blockedreason = serializers.SerializerMethodField()
    approved = serializers.SerializerMethodField()
    agent = serializers.SerializerMethodField()
    reminders = serializers.SerializerMethodField()
    country = serializers.SerializerMethodField()
    state = serializers.SerializerMethodField()
    district = serializers.SerializerMethodField()
    city = serializers.SerializerMethodField()
    pincode = serializers.SerializerMethodField()
    address1 = serializers.SerializerMethodField()
    address2 = serializers.SerializerMethodField()
    addressfloorno = serializers.SerializerMethodField()
    addressstreet = serializers.SerializerMethodField()
    cin = serializers.SerializerMethodField()
    msme = serializers.SerializerMethodField()
    gsttdsno = serializers.SerializerMethodField()

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
            "cin",
            "msme",
            "gsttdsno",
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
            "sharepercentage",
            "composition",
            "tobel10cr",
            "isaddsameasbillinf",
            "website",
            "agent",
            "reminders",
            "dateofreg",
            "dateofdreg",
            "ledger_mode",
            "ledger",
        )

    def _get_compliance(self, obj):
        return getattr(obj, "compliance_profile", None)

    def _get_commercial(self, obj):
        return getattr(obj, "commercial_profile", None)

    def _get_primary_address(self, obj):
        prefetched = getattr(obj, "prefetched_primary_addresses", None)
        if prefetched is not None:
            return prefetched[0] if prefetched else None
        return obj.addresses.filter(isprimary=True, isactive=True).first()

    def get_ledger_mode(self, obj):
        return "auto_managed"

    def get_partytype(self, obj):
        return getattr(self._get_commercial(obj), "partytype", None)

    def get_gstno(self, obj):
        return getattr(self._get_compliance(obj), "gstno", None)

    def get_pan(self, obj):
        return getattr(self._get_compliance(obj), "pan", None)

    def get_gstintype(self, obj):
        return getattr(self._get_compliance(obj), "gstintype", None)

    def get_gstregtype(self, obj):
        return getattr(self._get_compliance(obj), "gstregtype", None)

    def get_is_sez(self, obj):
        return getattr(self._get_compliance(obj), "is_sez", None)

    def get_tdsno(self, obj):
        return getattr(self._get_compliance(obj), "tdsno", None)

    def get_tdsrate(self, obj):
        return getattr(self._get_compliance(obj), "tdsrate", None)

    def get_tdssection(self, obj):
        return getattr(self._get_compliance(obj), "tdssection", None)

    def get_tds_threshold(self, obj):
        return getattr(self._get_compliance(obj), "tds_threshold", None)

    def get_istcsapplicable(self, obj):
        return getattr(self._get_compliance(obj), "istcsapplicable", None)

    def get_tcscode(self, obj):
        return getattr(self._get_compliance(obj), "tcscode", None)

    def get_creditlimit(self, obj):
        return getattr(self._get_commercial(obj), "creditlimit", None)

    def get_creditdays(self, obj):
        return getattr(self._get_commercial(obj), "creditdays", None)

    def get_paymentterms(self, obj):
        return getattr(self._get_commercial(obj), "paymentterms", None)

    def get_currency(self, obj):
        return getattr(self._get_commercial(obj), "currency", None)

    def get_blockstatus(self, obj):
        return getattr(self._get_commercial(obj), "blockstatus", None)

    def get_blockedreason(self, obj):
        return getattr(self._get_commercial(obj), "blockedreason", None)

    def get_approved(self, obj):
        return getattr(self._get_commercial(obj), "approved", None)

    def get_agent(self, obj):
        return getattr(self._get_commercial(obj), "agent", None)

    def get_reminders(self, obj):
        return getattr(self._get_commercial(obj), "reminders", None)

    def get_country(self, obj):
        address = self._get_primary_address(obj)
        return getattr(address, "country_id", None)

    def get_state(self, obj):
        address = self._get_primary_address(obj)
        return getattr(address, "state_id", None)

    def get_district(self, obj):
        address = self._get_primary_address(obj)
        return getattr(address, "district_id", None)

    def get_city(self, obj):
        address = self._get_primary_address(obj)
        return getattr(address, "city_id", None)

    def get_pincode(self, obj):
        address = self._get_primary_address(obj)
        return getattr(address, "pincode", None)

    def get_address1(self, obj):
        address = self._get_primary_address(obj)
        return getattr(address, "line1", None)

    def get_address2(self, obj):
        address = self._get_primary_address(obj)
        return getattr(address, "line2", None)

    def get_addressfloorno(self, obj):
        address = self._get_primary_address(obj)
        return getattr(address, "floor_no", None)

    def get_addressstreet(self, obj):
        address = self._get_primary_address(obj)
        return getattr(address, "street", None)

    def get_cin(self, obj):
        return getattr(self._get_compliance(obj), "cin", None)

    def get_msme(self, obj):
        return getattr(self._get_compliance(obj), "msme", None)

    def get_gsttdsno(self, obj):
        return getattr(self._get_compliance(obj), "gsttdsno", None)
