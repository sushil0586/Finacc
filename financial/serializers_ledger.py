from django.db import transaction
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from financial.gstin import validate_financial_gstin
from financial.models import AccountComplianceProfile, Ledger, account
from financial.party_accounting_defaults import resolve_party_accounting_ids
from financial.profile_access import (
    account_primary_address,
    account_primary_bank_account,
    account_primary_bank_name,
    account_primary_contact_person,
    account_primary_email,
    account_primary_phone,
)
from financial.services import (
    allocate_next_ledger_code,
    apply_normalized_profile_payload,
    create_account_with_synced_ledger,
    get_or_create_financial_settings,
    ledger_should_be_party,
    sync_ledger_for_account,
)
from financial.services_opening_balance import sync_account_opening_posting
from withholding.models import EntityPartyTaxProfile


WITHHOLDING_PROFILE_FIELDS = (
    "subentity",
    "residency_status",
    "tax_identifier",
    "declaration_reference",
    "treaty_article",
    "treaty_rate",
    "treaty_valid_from",
    "treaty_valid_to",
    "surcharge_rate",
    "cess_rate",
    "is_exempt_withholding",
    "is_specified_person_206ab",
    "specified_person_valid_from",
    "specified_person_valid_to",
    "lower_deduction_rate",
    "lower_deduction_valid_from",
    "lower_deduction_valid_to",
    "is_active",
)


def _account_withholding_subentity_id(serializer) -> int | None:
    request = serializer.context.get("request") if isinstance(serializer.context, dict) else None
    if request is None:
        return None
    query_params = getattr(request, "query_params", None)
    if query_params is None:
        query_params = getattr(request, "GET", None)
    if query_params is None:
        return None
    raw = query_params.get("subentity_id")
    if raw in (None, "", "null", "None"):
        return None
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _resolve_account_withholding_profile(*, acc, serializer):
    entity_id = getattr(acc, "entity_id", None)
    if not entity_id:
        return None
    subentity_id = _account_withholding_subentity_id(serializer)
    qs = EntityPartyTaxProfile.objects.filter(
        entity_id=entity_id,
        party_account_id=acc.id,
        is_active=True,
    )
    if subentity_id is not None:
        scoped = qs.filter(subentity_id=subentity_id).order_by("-id").first()
        if scoped is not None:
            return scoped
    return qs.filter(subentity__isnull=True).order_by("-id").first()


def _serialize_account_withholding_profile(*, acc, serializer):
    profile = _resolve_account_withholding_profile(acc=acc, serializer=serializer)
    compliance = getattr(acc, "compliance_profile", None)
    pan = getattr(compliance, "pan", None) if compliance else None
    payload = {
        "id": getattr(profile, "id", None),
        "party_account": acc.id,
        "pan": pan,
        "is_pan_available": bool((pan or "").strip()),
        "subentity": getattr(profile, "subentity_id", None),
        "residency_status": getattr(profile, "residency_status", "unknown") if profile else "unknown",
        "tax_identifier": getattr(profile, "tax_identifier", None) if profile else None,
        "declaration_reference": getattr(profile, "declaration_reference", None) if profile else None,
        "treaty_article": getattr(profile, "treaty_article", None) if profile else None,
        "treaty_rate": getattr(profile, "treaty_rate", None) if profile else None,
        "treaty_valid_from": getattr(profile, "treaty_valid_from", None) if profile else None,
        "treaty_valid_to": getattr(profile, "treaty_valid_to", None) if profile else None,
        "surcharge_rate": getattr(profile, "surcharge_rate", None) if profile else None,
        "cess_rate": getattr(profile, "cess_rate", None) if profile else None,
        "is_exempt_withholding": bool(getattr(profile, "is_exempt_withholding", False)),
        "is_specified_person_206ab": bool(getattr(profile, "is_specified_person_206ab", False)),
        "specified_person_valid_from": getattr(profile, "specified_person_valid_from", None) if profile else None,
        "specified_person_valid_to": getattr(profile, "specified_person_valid_to", None) if profile else None,
        "lower_deduction_rate": getattr(profile, "lower_deduction_rate", None) if profile else None,
        "lower_deduction_valid_from": getattr(profile, "lower_deduction_valid_from", None) if profile else None,
        "lower_deduction_valid_to": getattr(profile, "lower_deduction_valid_to", None) if profile else None,
        "is_active": bool(getattr(profile, "is_active", True)) if profile else True,
    }
    return payload


class LedgerSerializer(serializers.ModelSerializer):
    account_profile_id = serializers.IntegerField(source="account_profile.id", read_only=True)
    account_profile_name = serializers.CharField(source="account_profile.accountname", read_only=True)
    account_profile_gstno = serializers.SerializerMethodField()
    account_profile_pan = serializers.SerializerMethodField()
    management_mode = serializers.SerializerMethodField()
    direct_edit_blocked = serializers.SerializerMethodField()

    class Meta:
        model = Ledger
        validators = []
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
            "direct_edit_blocked",
        )

    def validate(self, attrs):
        attrs = super().validate(attrs)
        entity = attrs.get("entity", getattr(self.instance, "entity", None))
        name = str(attrs.get("name", getattr(self.instance, "name", "")) or "").strip()
        legal_name = str(attrs.get("legal_name", getattr(self.instance, "legal_name", "")) or "").strip() or None
        ledger_code = attrs.get("ledger_code", getattr(self.instance, "ledger_code", None))

        errors = {}
        if not entity:
            errors["entity"] = "Entity is required."
        if not name:
            errors["name"] = "Ledger name is required."

        if entity and ledger_code not in (None, ""):
            duplicate_qs = Ledger.objects.filter(entity=entity, ledger_code=ledger_code)
            if self.instance is not None:
                duplicate_qs = duplicate_qs.exclude(pk=self.instance.pk)
            if duplicate_qs.exists():
                errors["ledger_code"] = "A ledger with this code already exists."

        if errors:
            raise serializers.ValidationError(errors)

        attrs["name"] = name
        attrs["legal_name"] = legal_name
        return attrs

    def get_management_mode(self, obj):
        return "auto_managed" if self.get_direct_edit_blocked(obj) else "direct"

    def get_direct_edit_blocked(self, obj):
        if hasattr(obj, "account_profile"):
            return True
        return ledger_should_be_party(
            entity=obj.entity,
            is_party=obj.is_party,
            is_system=obj.is_system,
            accounttype_obj=getattr(obj, "accounttype", None),
            accounthead_obj=getattr(obj, "accounthead", None),
            creditaccounthead_obj=getattr(obj, "creditaccounthead", None),
        )

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
    emailid = serializers.EmailField(required=False, allow_null=True, allow_blank=True, write_only=True)
    contactno = serializers.CharField(required=False, allow_null=True, allow_blank=True, write_only=True)
    contactperson = serializers.CharField(required=False, allow_null=True, allow_blank=True, write_only=True)
    bankname = serializers.CharField(required=False, allow_null=True, allow_blank=True, write_only=True)
    banKAcno = serializers.CharField(required=False, allow_null=True, allow_blank=True, write_only=True)
    ledger = AccountProfileLedgerInputSerializer(required=False, write_only=True)
    compliance_profile = serializers.DictField(required=False, write_only=True)
    commercial_profile = serializers.DictField(required=False, write_only=True)
    withholding_profile = serializers.DictField(required=False, write_only=True)
    primary_address = serializers.DictField(required=False, write_only=True)
    primary_contact = serializers.DictField(required=False, write_only=True)
    primary_bank = serializers.DictField(required=False, write_only=True)

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
            "contactperson",
            "isactive",
            "bankname",
            "banKAcno",
            "website",
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
            "withholding_profile",
            "primary_address",
            "primary_contact",
            "primary_bank",
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
        if "udyam_no" in compliance:
            compliance["udyam_no"] = (str(compliance.get("udyam_no") or "").strip().upper() or None)
        if "msme_status" in compliance:
            valid_statuses = {choice[0] for choice in AccountComplianceProfile.MsmeStatus.choices}
            msme_status = str(compliance.get("msme_status") or "").strip().lower() or None
            if msme_status and msme_status not in valid_statuses:
                raise serializers.ValidationError(
                    {"compliance_profile": {"msme_status": "Select a valid MSME status."}}
                )
            compliance["msme_status"] = msme_status
        if "msme_credit_days" in compliance:
            raw_days = compliance.get("msme_credit_days")
            if raw_days in ("", None):
                compliance["msme_credit_days"] = None
            else:
                try:
                    msme_credit_days = int(raw_days)
                except (TypeError, ValueError):
                    raise serializers.ValidationError(
                        {"compliance_profile": {"msme_credit_days": "Enter a valid number of MSME credit days."}}
                    )
                if msme_credit_days < 0 or msme_credit_days > 45:
                    raise serializers.ValidationError(
                        {"compliance_profile": {"msme_credit_days": "MSME credit days must be between 0 and 45."}}
                    )
                compliance["msme_credit_days"] = msme_credit_days
        attrs["compliance_profile"] = compliance
        if self.instance is None and not attrs.get("entity"):
            raise serializers.ValidationError({"entity": "Entity is required."})
        if self.instance is None and not attrs.get("accountname"):
            raise serializers.ValidationError({"accountname": "Account name is required."})
        entity = attrs.get("entity") or getattr(self.instance, "entity", None)
        accountname = str(attrs.get("accountname", getattr(self.instance, "accountname", "")) or "").strip()
        legalname = str(attrs.get("legalname", getattr(self.instance, "legalname", "")) or "").strip() or None
        attrs["accountname"] = accountname or None
        attrs["legalname"] = legalname

        if not accountname:
            raise serializers.ValidationError({"accountname": "Account name is required."})

        errors = {}
        duplicate_accounts = account.objects.filter(entity=entity)
        if self.instance is not None:
            duplicate_accounts = duplicate_accounts.exclude(pk=self.instance.pk)
        existing_accountname = str(getattr(self.instance, "accountname", "") or "").strip()
        accountname_changed = self.instance is None or accountname.lower() != existing_accountname.lower()
        if accountname_changed and duplicate_accounts.filter(accountname__iexact=accountname).exists():
            errors["accountname"] = "An account with this name already exists."

        settings, _ = get_or_create_financial_settings(entity) if entity else (None, False)
        compliance_gst = str(compliance.get("gstno") or "").strip().upper() or None
        compliance_pan = str(compliance.get("pan") or "").strip().upper() or None
        existing_compliance = getattr(self.instance, "compliance_profile", None) if self.instance is not None else None
        existing_gst = str(getattr(existing_compliance, "gstno", "") or "").strip().upper() or None
        existing_pan = str(getattr(existing_compliance, "pan", "") or "").strip().upper() or None
        if compliance_gst:
            gst_qs = account.objects.filter(entity=entity, compliance_profile__gstno__iexact=compliance_gst)
            if self.instance is not None:
                gst_qs = gst_qs.exclude(pk=self.instance.pk)
            gst_changed = self.instance is None or compliance_gst != existing_gst
            if gst_changed and gst_qs.exists() and (settings is None or settings.enforce_gst_uniqueness):
                errors["compliance_profile"] = {"gstno": "An account with this GSTIN already exists."}
            compliance["gstno"] = compliance_gst
        if compliance_pan:
            pan_qs = account.objects.filter(entity=entity, compliance_profile__pan__iexact=compliance_pan)
            if self.instance is not None:
                pan_qs = pan_qs.exclude(pk=self.instance.pk)
            pan_changed = self.instance is None or compliance_pan != existing_pan
            if pan_changed and pan_qs.exists() and settings is not None and settings.enforce_pan_uniqueness:
                existing = errors.get("compliance_profile", {})
                existing["pan"] = "An account with this PAN already exists."
                errors["compliance_profile"] = existing
            compliance["pan"] = compliance_pan

        commercial = dict(attrs.get("commercial_profile", {}) or {})
        defaults = resolve_party_accounting_ids(entity=entity, partytype=commercial.get("partytype"))
        accounttype_value = attrs.get("accounttype")
        nested_accounttype_value = attrs.get("ledger", {}).get("accounttype")
        accounthead_value = attrs.get("accounthead")
        nested_accounthead_value = attrs.get("ledger", {}).get("accounthead")
        creditaccounthead_value = attrs.get("creditaccounthead")
        nested_creditaccounthead_value = attrs.get("ledger", {}).get("creditaccounthead")
        if accounttype_value in (0, "0", ""):
            attrs["accounttype"] = None
            accounttype_value = None
        if nested_accounttype_value in (0, "0", ""):
            attrs.setdefault("ledger", {})["accounttype"] = None
            nested_accounttype_value = None
        if accounthead_value in (0, "0", ""):
            attrs["accounthead"] = None
            accounthead_value = None
        if nested_accounthead_value in (0, "0", ""):
            attrs.setdefault("ledger", {})["accounthead"] = None
            nested_accounthead_value = None
        if creditaccounthead_value in (0, "0", ""):
            attrs["creditaccounthead"] = None
            creditaccounthead_value = None
        if nested_creditaccounthead_value in (0, "0", ""):
            attrs.setdefault("ledger", {})["creditaccounthead"] = None
            nested_creditaccounthead_value = None
        if not (accounttype_value or nested_accounttype_value) and defaults.get("accounttype_id"):
            attrs["accounttype"] = defaults["accounttype_id"]
        if not (accounthead_value or nested_accounthead_value) and defaults.get("accounthead_id"):
            attrs["accounthead"] = defaults["accounthead_id"]
            accounthead_value = defaults["accounthead_id"]
        if not (creditaccounthead_value or nested_creditaccounthead_value) and defaults.get("creditaccounthead_id"):
            attrs["creditaccounthead"] = defaults["creditaccounthead_id"]
        if self.instance is None and not (accounthead_value or nested_accounthead_value):
            raise serializers.ValidationError({"accounthead": "Account head is required."})
        proposed_ledger_code = attrs.get("ledger_code")
        if proposed_ledger_code in (None, ""):
            proposed_ledger_code = attrs.get("ledger", {}).get("ledger_code")
        if entity and proposed_ledger_code not in (None, ""):
            duplicate_ledgers = Ledger.objects.filter(entity=entity, ledger_code=proposed_ledger_code)
            current_ledger_id = getattr(self.instance, "ledger_id", None)
            if current_ledger_id:
                duplicate_ledgers = duplicate_ledgers.exclude(pk=current_ledger_id)
            if duplicate_ledgers.exists():
                errors["ledger_code"] = "An account with this ledger code already exists."

        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    @staticmethod
    def _normalize_fk_value(value):
        if isinstance(value, bool):
            return value
        return None if value in (0, "0", "") else value

    @staticmethod
    def _apply_party_accounting_defaults(*, entity, accounting, commercial_payload):
        partytype = (commercial_payload or {}).get("partytype")
        defaults = resolve_party_accounting_ids(entity=entity, partytype=partytype)
        if not any(defaults.values()):
            return accounting

        if not accounting.get("accounttype") and defaults.get("accounttype_id"):
            accounting["accounttype"] = defaults["accounttype_id"]
        if not accounting.get("accounthead") and defaults.get("accounthead_id"):
            accounting["accounthead"] = defaults["accounthead_id"]
        if not accounting.get("creditaccounthead") and defaults.get("creditaccounthead_id"):
            accounting["creditaccounthead"] = defaults["creditaccounthead_id"]
        return accounting

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
        withholding = dict(validated_data.pop("withholding_profile", {}) or {})
        primary_address = dict(validated_data.pop("primary_address", {}) or {})
        primary_contact = dict(validated_data.pop("primary_contact", {}) or {})
        primary_bank = dict(validated_data.pop("primary_bank", {}) or {})

        top_level_contact = {
            "emailid": validated_data.get("emailid"),
            "contactno": validated_data.get("contactno"),
            "contactperson": validated_data.get("contactperson"),
        }
        if any(value not in (None, "") for value in top_level_contact.values()):
            for key, value in top_level_contact.items():
                if value not in (None, "") and key not in primary_contact:
                    primary_contact[key] = value

        top_level_bank = {
            "bankname": validated_data.get("bankname"),
            "banKAcno": validated_data.get("banKAcno"),
        }
        if any(value not in (None, "") for value in top_level_bank.values()):
            for key, value in top_level_bank.items():
                if value not in (None, "") and key not in primary_bank:
                    primary_bank[key] = value

        return withholding, compliance, commercial, primary_address, primary_contact, primary_bank

    @staticmethod
    def _raise_opening_balance_validation(exc):
        messages = []
        if isinstance(exc, DjangoValidationError):
            if hasattr(exc, "message_dict"):
                for value in exc.message_dict.values():
                    if isinstance(value, (list, tuple)):
                        messages.extend(str(item) for item in value)
                    else:
                        messages.append(str(value))
            elif getattr(exc, "messages", None):
                messages.extend(str(item) for item in exc.messages)
            else:
                messages.append(str(exc))
        else:
            messages.append(str(exc))
        cleaned = [message for message in messages if message]
        raise serializers.ValidationError(
            {"opening_balance": cleaned or ["Unable to synchronize opening balance posting."]}
        )

    @transaction.atomic
    def create(self, validated_data):
        accounting = self._resolve_accounting_payload(validated_data)
        withholding_payload, compliance_payload, commercial_payload, primary_address_payload, primary_contact_payload, primary_bank_payload = self._extract_normalized_profile_payload(
            validated_data
        )
        request = self.context.get("request")
        if request and getattr(request, "user", None) and request.user.is_authenticated:
            validated_data["createdby"] = request.user

        validated_data["canbedeleted"] = accounting.get("canbedeleted", True)
        if accounting.get("isactive") is not None:
            validated_data["isactive"] = accounting["isactive"]
        accounting = self._apply_party_accounting_defaults(
            entity=validated_data.get("entity"),
            accounting=accounting,
            commercial_payload=commercial_payload,
        )
        ledger_code = accounting.get("ledger_code")
        if ledger_code is None and validated_data.get("entity"):
            ledger_code = allocate_next_ledger_code(
                entity_id=validated_data["entity"].id,
                partytype=(commercial_payload or {}).get("partytype"),
                account_type_id=accounting.get("accounttype"),
                debit_head_id=accounting.get("accounthead"),
                credit_head_id=accounting.get("creditaccounthead"),
                allocated_by=validated_data.get("createdby"),
            )

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
            primary_contact_data=primary_contact_payload if primary_contact_payload else None,
            primary_bank_data=primary_bank_payload if primary_bank_payload else None,
            createdby=validated_data.get("createdby"),
        )
        self._sync_withholding_profile(acc=acc, withholding_payload=withholding_payload)
        try:
            sync_account_opening_posting(
                acc,
                old_opening_dr=None,
                old_opening_cr=None,
                actor=validated_data.get("createdby"),
            )
        except (DjangoValidationError, ValueError) as exc:
            self._raise_opening_balance_validation(exc)
        return acc

    @transaction.atomic
    def update(self, instance, validated_data):
        old_opening_dr = getattr(getattr(instance, "ledger", None), "openingbdr", None)
        old_opening_cr = getattr(getattr(instance, "ledger", None), "openingbcr", None)
        accounting = self._resolve_accounting_payload(validated_data)
        withholding_payload, compliance_payload, commercial_payload, primary_address_payload, primary_contact_payload, primary_bank_payload = self._extract_normalized_profile_payload(
            validated_data
        )
        accounting = self._apply_party_accounting_defaults(
            entity=getattr(instance, "entity", None),
            accounting=accounting,
            commercial_payload=commercial_payload,
        )
        for field, value in validated_data.items():
            setattr(instance, field, value)

        if "canbedeleted" in accounting:
            instance.canbedeleted = accounting.get("canbedeleted")

        request = self.context.get("request")
        if request and getattr(request, "user", None) and request.user.is_authenticated:
            instance.createdby = request.user

        instance.save()
        ledger_code = accounting.get("ledger_code")
        if ledger_code is None and getattr(instance, "ledger_id", None):
            ledger_code = instance.ledger.ledger_code
        elif ledger_code is None and instance.entity_id:
            ledger_code = allocate_next_ledger_code(
                entity_id=instance.entity_id,
                partytype=(commercial_payload or {}).get("partytype")
                or getattr(getattr(instance, "commercial_profile", None), "partytype", None),
                account_type_id=accounting.get("accounttype"),
                debit_head_id=accounting.get("accounthead"),
                credit_head_id=accounting.get("creditaccounthead"),
                allocated_by=instance.createdby,
            )
        sync_ledger_for_account(
            instance,
            ledger_overrides={
                "ledger_code": ledger_code,
                "name": instance.accountname,
                "legal_name": instance.legalname,
                "accounthead_id": accounting.get("accounthead"),
                "creditaccounthead_id": accounting.get("creditaccounthead"),
                "contra_ledger_id": accounting.get("contra_ledger") if "contra_ledger" in accounting else None,
                "accounttype_id": accounting.get("accounttype"),
                "openingbcr": accounting.get("openingbcr"),
                "openingbdr": accounting.get("openingbdr"),
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
            primary_contact_data=primary_contact_payload if primary_contact_payload else None,
            primary_bank_data=primary_bank_payload if primary_bank_payload else None,
            createdby=actor,
        )
        self._sync_withholding_profile(acc=instance, withholding_payload=withholding_payload)
        try:
            sync_account_opening_posting(
                instance,
                old_opening_dr=old_opening_dr,
                old_opening_cr=old_opening_cr,
                actor=actor,
            )
        except (DjangoValidationError, ValueError) as exc:
            self._raise_opening_balance_validation(exc)
        return instance

    def _sync_withholding_profile(self, *, acc, withholding_payload):
        if not withholding_payload:
            return
        payload = dict(withholding_payload)
        payload.pop("id", None)
        payload.pop("party_account", None)
        payload.pop("pan", None)
        payload.pop("is_pan_available", None)
        if "subentity" in payload:
            payload["subentity_id"] = self._normalize_fk_value(payload.pop("subentity"))

        defaults = {}
        for field_name in WITHHOLDING_PROFILE_FIELDS:
            source_key = "subentity_id" if field_name == "subentity" else field_name
            if source_key in payload:
                defaults[source_key] = payload[source_key]
        if not defaults:
            return

        EntityPartyTaxProfile.objects.update_or_create(
            entity_id=acc.entity_id,
            party_account=acc,
            subentity_id=defaults.pop("subentity_id", None),
            defaults=defaults,
        )


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
    msme_status = serializers.SerializerMethodField()
    udyam_no = serializers.SerializerMethodField()
    has_written_payment_terms = serializers.SerializerMethodField()
    msme_credit_days = serializers.SerializerMethodField()
    emailid = serializers.SerializerMethodField()
    contactno = serializers.SerializerMethodField()
    contactperson = serializers.SerializerMethodField()
    bankname = serializers.SerializerMethodField()
    banKAcno = serializers.SerializerMethodField()
    withholding_profile = serializers.SerializerMethodField()

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
            "contactperson",
            "cin",
            "msme",
            "msme_status",
            "udyam_no",
            "has_written_payment_terms",
            "msme_credit_days",
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
            "website",
            "withholding_profile",
            "agent",
            "reminders",
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

    def get_emailid(self, obj):
        return account_primary_email(obj)

    def get_contactno(self, obj):
        return account_primary_phone(obj)

    def get_contactperson(self, obj):
        return account_primary_contact_person(obj)

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

    def get_bankname(self, obj):
        return account_primary_bank_name(obj)

    def get_banKAcno(self, obj):
        return account_primary_bank_account(obj)

    def get_cin(self, obj):
        return getattr(self._get_compliance(obj), "cin", None)

    def get_msme(self, obj):
        return getattr(self._get_compliance(obj), "msme", None)

    def get_gsttdsno(self, obj):
        return getattr(self._get_compliance(obj), "gsttdsno", None)

    def get_msme_status(self, obj):
        return getattr(self._get_compliance(obj), "msme_status", None)

    def get_udyam_no(self, obj):
        return getattr(self._get_compliance(obj), "udyam_no", None)

    def get_has_written_payment_terms(self, obj):
        return getattr(self._get_compliance(obj), "has_written_payment_terms", None)

    def get_msme_credit_days(self, obj):
        return getattr(self._get_compliance(obj), "msme_credit_days", None)

    def get_withholding_profile(self, obj):
        return _serialize_account_withholding_profile(acc=obj, serializer=self)
