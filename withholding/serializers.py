from __future__ import annotations

from decimal import Decimal
import re

from django.db.models import Sum
from rest_framework import serializers

from withholding.models import (
    EntityPartyTaxProfile,
    EntityTcsThresholdOpening,
    EntityWithholdingSectionPostingMap,
    EntityWithholdingConfig,
    GstTcsComputation,
    GstTcsEcoProfile,
    PartyTaxProfile,
    TcsCollection,
    TcsComputation,
    TcsDeposit,
    TcsDepositAllocation,
    TcsQuarterlyReturn,
    WithholdingSectionPolicyAudit,
    WithholdingSection,
    WithholdingBaseRule,
    WithholdingTaxType,
)
from withholding.services import (
    ZERO2,
    compute_withholding_preview,
    determine_fy_quarter,
    q2,
)
from financial.models import AccountComplianceProfile


APPLICABILITY_ALLOWED_KEYS = {
    "resident_status",
    "resident_country_codes",
    "party_country_codes",
    "threshold_mode",
    "aggregate_threshold",
    "rent_rate_plant_machinery",
    "rent_rate_land_building",
    "rent_plant_machinery_keywords",
}
APPLICABILITY_RESIDENT_STATUSES = {"resident", "non_resident"}
APPLICABILITY_THRESHOLD_MODES = {"single_txn", "cumulative"}


def _json_safe_value(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: _json_safe_value(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_value(item) for item in value]
    return value


class RejectWorkflowManagedFieldsMixin:
    workflow_managed_write_errors: dict[str, str] = {}

    def validate(self, attrs):
        errors = {}
        initial_data = getattr(self, "initial_data", None)
        if isinstance(initial_data, dict):
            for field_name, message in self.workflow_managed_write_errors.items():
                if field_name in initial_data:
                    errors[field_name] = message
        if errors:
            raise serializers.ValidationError(errors)
        return super().validate(attrs)


def _normalize_text_list(value):
    if value in (None, ""):
        return []
    if isinstance(value, str):
        raw_items = [value]
    elif isinstance(value, (list, tuple)):
        raw_items = list(value)
    else:
        raise serializers.ValidationError("must be a string or list of strings.")

    out = []
    for item in raw_items:
        if not isinstance(item, str):
            raise serializers.ValidationError("must contain only strings.")
        token = item.strip()
        if token:
            out.append(token)
    return out


def _normalize_country_code_list(value, field_name: str):
    tokens = _normalize_text_list(value)
    out = []
    for token in tokens:
        upper = token.upper()
        if not re.fullmatch(r"[A-Z]{2}", upper):
            raise serializers.ValidationError({field_name: "must contain ISO alpha-2 country codes (e.g. IN, AE)."})
        out.append(upper)
    return out


def _normalize_decimal_string(value, field_name: str):
    try:
        amount = q2(Decimal(str(value or ZERO2)))
    except Exception as exc:
        raise serializers.ValidationError({field_name: "Enter a valid amount."}) from exc
    if amount < ZERO2:
        raise serializers.ValidationError({field_name: "Amount cannot be negative."})
    return str(amount)


def _is_valid_fy_label(value: str) -> bool:
    raw = (value or "").strip()
    m_short = re.match(r"^(\d{4})-(\d{2})$", raw)
    if m_short:
        start = int(m_short.group(1))
        end_2 = int(m_short.group(2))
        end_full = (start // 100) * 100 + end_2
        if end_full < start:
            end_full += 100
        return end_full == (start + 1)
    m_full = re.match(r"^(\d{4})-(\d{4})$", raw)
    if m_full:
        start = int(m_full.group(1))
        end_full = int(m_full.group(2))
        return end_full == (start + 1)
    return False


class WithholdingSectionSerializer(serializers.ModelSerializer):
    TRACKED_POLICY_FIELDS = (
        "rate_default",
        "threshold_default",
        "higher_rate_no_pan",
        "higher_rate_206ab",
        "applicability_json",
        "effective_from",
        "effective_to",
        "is_active",
        "base_rule",
        "requires_pan",
    )

    @staticmethod
    def _policy_snapshot(instance: WithholdingSection) -> dict:
        return {
            "tax_type": int(instance.tax_type) if instance.tax_type is not None else None,
            "section_code": instance.section_code,
            "description": instance.description,
            "base_rule": int(instance.base_rule) if instance.base_rule is not None else None,
            "rate_default": str(instance.rate_default) if instance.rate_default is not None else None,
            "threshold_default": str(instance.threshold_default) if instance.threshold_default is not None else None,
            "requires_pan": bool(instance.requires_pan),
            "higher_rate_no_pan": str(instance.higher_rate_no_pan) if instance.higher_rate_no_pan is not None else None,
            "higher_rate_206ab": str(instance.higher_rate_206ab) if instance.higher_rate_206ab is not None else None,
            "applicability_json": instance.applicability_json if isinstance(instance.applicability_json, dict) else None,
            "effective_from": instance.effective_from.isoformat() if instance.effective_from else None,
            "effective_to": instance.effective_to.isoformat() if instance.effective_to else None,
            "is_active": bool(instance.is_active),
        }

    def _log_policy_audit(self, *, action: str, section: WithholdingSection, before: dict | None, after: dict | None):
        request = self.context.get("request") if isinstance(self.context, dict) else None
        changed_by = getattr(request, "user", None) if request else None
        if changed_by is not None and not getattr(changed_by, "is_authenticated", False):
            changed_by = None

        changed_fields = []
        if before is None and after:
            changed_fields = sorted(after.keys())
        elif before and after:
            changed_fields = sorted([key for key in after.keys() if before.get(key) != after.get(key)])

        if action == WithholdingSectionPolicyAudit.Action.UPDATED and not changed_fields:
            return

        WithholdingSectionPolicyAudit.objects.create(
            section=section,
            action=action,
            changed_by=changed_by,
            changed_fields_json=changed_fields,
            before_snapshot_json=before,
            after_snapshot_json=after,
            source="api",
        )

    def create(self, validated_data):
        section = super().create(validated_data)
        self._log_policy_audit(
            action=WithholdingSectionPolicyAudit.Action.CREATED,
            section=section,
            before=None,
            after=self._policy_snapshot(section),
        )
        return section

    def update(self, instance, validated_data):
        before = self._policy_snapshot(instance)
        section = super().update(instance, validated_data)
        after = self._policy_snapshot(section)
        self._log_policy_audit(
            action=WithholdingSectionPolicyAudit.Action.UPDATED,
            section=section,
            before=before,
            after=after,
        )
        return section

    def validate_applicability_json(self, value):
        if value in (None, ""):
            return None
        if not isinstance(value, dict):
            raise serializers.ValidationError("must be a JSON object.")

        unknown_keys = sorted(set(value.keys()) - APPLICABILITY_ALLOWED_KEYS)
        if unknown_keys:
            raise serializers.ValidationError(
                f"Unsupported keys: {', '.join(unknown_keys)}. "
                f"Allowed keys: {', '.join(sorted(APPLICABILITY_ALLOWED_KEYS))}."
            )

        normalized = {}

        if "resident_status" in value:
            statuses = [s.lower() for s in _normalize_text_list(value.get("resident_status"))]
            invalid = [s for s in statuses if s not in APPLICABILITY_RESIDENT_STATUSES]
            if invalid:
                raise serializers.ValidationError(
                    {
                        "resident_status": (
                            "supports only: resident, non_resident."
                        )
                    }
                )
            if statuses:
                normalized["resident_status"] = list(dict.fromkeys(statuses))

        if "resident_country_codes" in value:
            resident_codes = _normalize_country_code_list(
                value.get("resident_country_codes"),
                "resident_country_codes",
            )
            if resident_codes:
                normalized["resident_country_codes"] = list(dict.fromkeys(resident_codes))

        if "party_country_codes" in value:
            party_codes = _normalize_country_code_list(
                value.get("party_country_codes"),
                "party_country_codes",
            )
            if party_codes:
                normalized["party_country_codes"] = list(dict.fromkeys(party_codes))

        if "threshold_mode" in value:
            mode = str(value.get("threshold_mode") or "").strip().lower()
            if mode:
                if mode not in APPLICABILITY_THRESHOLD_MODES:
                    raise serializers.ValidationError(
                        {
                            "threshold_mode": (
                                "supports only: single_txn, cumulative."
                            )
                        }
                    )
                normalized["threshold_mode"] = mode

        if "aggregate_threshold" in value:
            normalized["aggregate_threshold"] = _normalize_decimal_string(
                value.get("aggregate_threshold"),
                "aggregate_threshold",
            )

        if "rent_rate_plant_machinery" in value:
            normalized["rent_rate_plant_machinery"] = _normalize_decimal_string(
                value.get("rent_rate_plant_machinery"),
                "rent_rate_plant_machinery",
            )

        if "rent_rate_land_building" in value:
            normalized["rent_rate_land_building"] = _normalize_decimal_string(
                value.get("rent_rate_land_building"),
                "rent_rate_land_building",
            )

        if "rent_plant_machinery_keywords" in value:
            keywords = [token.lower() for token in _normalize_text_list(value.get("rent_plant_machinery_keywords"))]
            if keywords:
                normalized["rent_plant_machinery_keywords"] = list(dict.fromkeys(keywords))

        return normalized

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance is not None:
            immutable_fields = ("tax_type", "section_code", "base_rule", "effective_from")
            errors = {}
            for field in immutable_fields:
                if field in attrs and attrs[field] != getattr(self.instance, field):
                    errors[field] = (
                        f"{field} cannot be changed on an existing section. "
                        "Create a new effective row instead."
                    )
            if errors:
                raise serializers.ValidationError(errors)
        return attrs

    class Meta:
        model = WithholdingSection
        fields = [
            "id",
            "tax_type",
            "law_type",
            "sub_type",
            "section_code",
            "description",
            "base_rule",
            "rate_default",
            "threshold_default",
            "requires_pan",
            "higher_rate_no_pan",
            "higher_rate_206ab",
            "applicability_json",
            "effective_from",
            "effective_to",
            "is_active",
        ]


class PartyTaxProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = PartyTaxProfile
        fields = [
            "id",
            "party_account",
            "pan",
            "is_pan_available",
            "is_exempt_withholding",
            "is_specified_person_206ab",
            "specified_person_valid_from",
            "specified_person_valid_to",
            "lower_deduction_rate",
            "lower_deduction_valid_from",
            "lower_deduction_valid_to",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]


class EntityPartyTaxProfileSerializer(serializers.ModelSerializer):
    pan = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    is_pan_available = serializers.BooleanField(required=False)

    class Meta:
        model = EntityPartyTaxProfile
        fields = [
            "id",
            "entity",
            "subentity",
            "party_account",
            "pan",
            "is_pan_available",
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
            "updated_at",
        ]
        read_only_fields = ["updated_at"]

    _UNSET = object()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        compliance_profile = getattr(getattr(instance, "party_account", None), "compliance_profile", None)
        pan_value = str(getattr(compliance_profile, "pan", None) or "").strip().upper() or None
        if not pan_value:
            compliance_profile = (
                AccountComplianceProfile.objects.filter(account_id=instance.party_account_id)
                .only("pan")
                .first()
            )
            pan_value = str(getattr(compliance_profile, "pan", None) or "").strip().upper() or None
        if pan_value:
            data["pan"] = pan_value
            data["is_pan_available"] = True
            return data

        party_profile = getattr(getattr(instance, "party_account", None), "tax_profile", None)
        party_pan = str(getattr(party_profile, "pan", None) or "").strip().upper() or None
        if party_profile is None or (not party_pan and not bool(getattr(party_profile, "is_pan_available", False))):
            party_profile = (
                PartyTaxProfile.objects.filter(party_account_id=instance.party_account_id)
                .only("pan", "is_pan_available")
                .first()
            )
            party_pan = str(getattr(party_profile, "pan", None) or "").strip().upper() or None
        data["pan"] = party_pan
        data["is_pan_available"] = bool(getattr(party_profile, "is_pan_available", False)) if party_profile else False
        return data

    def _sync_party_tax_profile(self, *, instance: EntityPartyTaxProfile, pan=_UNSET, is_pan_available=_UNSET):
        if pan is self._UNSET and is_pan_available is self._UNSET:
            return

        defaults = {}
        normalized_pan = self._UNSET
        if pan is not self._UNSET:
            pan_value = str(pan or "").strip().upper()
            normalized_pan = pan_value or None
            defaults["pan"] = normalized_pan

        if is_pan_available is not self._UNSET:
            defaults["is_pan_available"] = bool(is_pan_available)
        elif normalized_pan is not self._UNSET:
            defaults["is_pan_available"] = bool(normalized_pan)

        if defaults:
            normalized_pan = defaults.get("pan")
            if normalized_pan is not None:
                AccountComplianceProfile.objects.update_or_create(
                    account_id=instance.party_account_id,
                    defaults={
                        "entity_id": instance.entity_id,
                        "pan": normalized_pan,
                    },
                )
            PartyTaxProfile.objects.update_or_create(
                party_account_id=instance.party_account_id,
                defaults=defaults,
            )

    def create(self, validated_data):
        pan = validated_data.pop("pan", self._UNSET)
        is_pan_available = validated_data.pop("is_pan_available", self._UNSET)
        instance = super().create(validated_data)
        self._sync_party_tax_profile(instance=instance, pan=pan, is_pan_available=is_pan_available)
        return instance

    def update(self, instance, validated_data):
        pan = validated_data.pop("pan", self._UNSET)
        is_pan_available = validated_data.pop("is_pan_available", self._UNSET)
        instance = super().update(instance, validated_data)
        self._sync_party_tax_profile(instance=instance, pan=pan, is_pan_available=is_pan_available)
        return instance


class EntityWithholdingConfigSerializer(serializers.ModelSerializer):
    def validate(self, attrs):
        attrs = super().validate(attrs)
        instance = getattr(self, "instance", None)

        effective_from = attrs.get("effective_from")
        if effective_from is None and instance is not None:
            effective_from = instance.effective_from

        default_tds_section = attrs.get("default_tds_section", getattr(instance, "default_tds_section", None))
        default_tcs_section = attrs.get("default_tcs_section", getattr(instance, "default_tcs_section", None))

        errors = {}

        if default_tds_section is not None:
            if int(default_tds_section.tax_type) != int(WithholdingTaxType.TDS):
                errors["default_tds_section"] = "Section tax_type must be TDS."
            elif int(default_tds_section.base_rule) not in (
                int(WithholdingBaseRule.INVOICE_VALUE_EXCL_GST),
                int(WithholdingBaseRule.INVOICE_VALUE_INCL_GST),
            ):
                errors["default_tds_section"] = (
                    "Default TDS section must be invoice-basis. "
                    "Use runtime section selection for payment-basis flows."
                )
            elif effective_from:
                if default_tds_section.effective_from and default_tds_section.effective_from > effective_from:
                    errors["default_tds_section"] = "Section is not yet effective for selected configuration date."
                if default_tds_section.effective_to and default_tds_section.effective_to < effective_from:
                    errors["default_tds_section"] = "Section is expired for selected configuration date."

        if default_tcs_section is not None:
            if int(default_tcs_section.tax_type) != int(WithholdingTaxType.TCS):
                errors["default_tcs_section"] = "Section tax_type must be TCS."
            elif int(default_tcs_section.base_rule) not in (
                int(WithholdingBaseRule.INVOICE_VALUE_EXCL_GST),
                int(WithholdingBaseRule.INVOICE_VALUE_INCL_GST),
            ):
                errors["default_tcs_section"] = (
                    "Default TCS section must be invoice-basis. "
                    "Use runtime section selection for receipt-basis flows."
                )
            elif effective_from:
                if default_tcs_section.effective_from and default_tcs_section.effective_from > effective_from:
                    errors["default_tcs_section"] = "Section is not yet effective for selected configuration date."
                if default_tcs_section.effective_to and default_tcs_section.effective_to < effective_from:
                    errors["default_tcs_section"] = "Section is expired for selected configuration date."

        if errors:
            raise serializers.ValidationError(errors)

        prev_turnover = attrs.get(
            "tds_194q_prev_fy_turnover",
            getattr(instance, "tds_194q_prev_fy_turnover", ZERO2) if instance else ZERO2,
        )
        turnover_limit = attrs.get(
            "tds_194q_turnover_limit",
            getattr(instance, "tds_194q_turnover_limit", ZERO2) if instance else ZERO2,
        )
        if q2(prev_turnover or ZERO2) < ZERO2:
            errors["tds_194q_prev_fy_turnover"] = "Previous FY turnover cannot be negative."
        if q2(turnover_limit or ZERO2) < ZERO2:
            errors["tds_194q_turnover_limit"] = "Turnover limit cannot be negative."

        prev_turnover = attrs.get(
            "tcs_206c1h_prev_fy_turnover",
            getattr(instance, "tcs_206c1h_prev_fy_turnover", ZERO2) if instance else ZERO2,
        )
        turnover_limit = attrs.get(
            "tcs_206c1h_turnover_limit",
            getattr(instance, "tcs_206c1h_turnover_limit", ZERO2) if instance else ZERO2,
        )
        if q2(prev_turnover or ZERO2) < ZERO2:
            errors["tcs_206c1h_prev_fy_turnover"] = "Previous FY turnover cannot be negative."
        if q2(turnover_limit or ZERO2) < ZERO2:
            errors["tcs_206c1h_turnover_limit"] = "Turnover limit cannot be negative."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    class Meta:
        model = EntityWithholdingConfig
        fields = [
            "id",
            "entity",
            "entityfin",
            "subentity",
            "enable_tds",
            "enable_tcs",
            "default_tds_section",
            "default_tcs_section",
            "apply_194q",
            "tds_194q_prev_fy_turnover",
            "tds_194q_turnover_limit",
            "tds_194q_force_eligible",
            "apply_tcs_206c1h",
            "tcs_206c1h_prev_fy_turnover",
            "tcs_206c1h_turnover_limit",
            "tcs_206c1h_force_eligible",
            "effective_from",
            "rounding_places",
        ]


class EntityTcsThresholdOpeningSerializer(serializers.ModelSerializer):
    def validate(self, attrs):
        attrs = super().validate(attrs)
        instance = getattr(self, "instance", None)
        entity = attrs.get("entity", getattr(instance, "entity", None))
        subentity = attrs.get("subentity", getattr(instance, "subentity", None))
        section = attrs.get("section", getattr(instance, "section", None))
        opening_base_amount = attrs.get("opening_base_amount", getattr(instance, "opening_base_amount", ZERO2))

        errors = {}
        if subentity is not None and entity is not None and int(subentity.entity_id) != int(entity.id):
            errors["subentity"] = "Subentity must belong to selected entity."
        if section is not None and int(section.tax_type) != int(WithholdingTaxType.TCS):
            errors["section"] = "Only TCS sections are allowed."
        if opening_base_amount is not None and q2(opening_base_amount) < ZERO2:
            errors["opening_base_amount"] = "opening_base_amount cannot be negative."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    class Meta:
        model = EntityTcsThresholdOpening
        fields = [
            "id",
            "entity",
            "entityfin",
            "subentity",
            "party_account",
            "section",
            "opening_base_amount",
            "effective_from",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class EntityWithholdingSectionPostingMapSerializer(serializers.ModelSerializer):
    def validate(self, attrs):
        attrs = super().validate(attrs)
        instance = getattr(self, "instance", None)

        entity_obj = attrs.get("entity", getattr(instance, "entity", None))
        subentity_obj = attrs.get("subentity", getattr(instance, "subentity", None))
        payable_account = attrs.get("payable_account", getattr(instance, "payable_account", None))
        payable_ledger = attrs.get("payable_ledger", getattr(instance, "payable_ledger", None))

        errors = {}

        if subentity_obj is not None and entity_obj is not None and subentity_obj.entity_id != entity_obj.id:
            errors["subentity"] = "Subentity must belong to selected entity."

        if payable_account is not None and entity_obj is not None and payable_account.entity_id != entity_obj.id:
            errors["payable_account"] = "Payable account must belong to selected entity."

        if payable_ledger is not None and entity_obj is not None:
            ledger_entity_id = getattr(payable_ledger, "entity_id", None)
            if ledger_entity_id not in (None, entity_obj.id):
                errors["payable_ledger"] = "Payable ledger must belong to selected entity."

        if payable_ledger is not None and payable_account is not None:
            account_ledger_id = getattr(payable_account, "ledger_id", None)
            if account_ledger_id and int(payable_ledger.id) != int(account_ledger_id):
                errors["payable_ledger"] = "Payable ledger must match payable account ledger."

        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    class Meta:
        model = EntityWithholdingSectionPostingMap
        fields = [
            "id",
            "entity",
            "subentity",
            "section",
            "payable_account",
            "payable_ledger",
            "effective_from",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class WithholdingSectionPolicyAuditSerializer(serializers.ModelSerializer):
    section_code = serializers.CharField(source="section.section_code", read_only=True)
    section_tax_type = serializers.IntegerField(source="section.tax_type", read_only=True)
    changed_by_email = serializers.EmailField(source="changed_by.email", read_only=True)

    class Meta:
        model = WithholdingSectionPolicyAudit
        fields = [
            "id",
            "section",
            "section_code",
            "section_tax_type",
            "action",
            "changed_by",
            "changed_by_email",
            "changed_fields_json",
            "before_snapshot_json",
            "after_snapshot_json",
            "source",
            "created_at",
        ]


class TcsComputeRequestSerializer(serializers.Serializer):
    entity_id = serializers.IntegerField()
    entityfin_id = serializers.IntegerField()
    subentity_id = serializers.IntegerField(required=False, allow_null=True)
    party_account_id = serializers.IntegerField(required=False, allow_null=True)
    tax_type = serializers.ChoiceField(choices=WithholdingTaxType.choices, default=WithholdingTaxType.TCS)
    section_id = serializers.IntegerField(required=False, allow_null=True)
    document_type = serializers.CharField(required=False, allow_blank=True, default="invoice")
    document_id = serializers.IntegerField(required=False, allow_null=True)
    document_no = serializers.CharField(required=False, allow_blank=True, default="")
    module_name = serializers.CharField(required=False, allow_blank=True, default="sales")
    doc_date = serializers.DateField()
    taxable_total = serializers.DecimalField(max_digits=18, decimal_places=2, required=False, default=Decimal("0.00"))
    gross_total = serializers.DecimalField(max_digits=18, decimal_places=2, required=False, default=Decimal("0.00"))
    trigger_basis = serializers.CharField(required=False, allow_blank=True, default="INVOICE")
    override_reason = serializers.CharField(required=False, allow_blank=True, default="")


class TcsComputeConfirmSerializer(TcsComputeRequestSerializer):
    status = serializers.ChoiceField(choices=TcsComputation.Status.choices, required=False, default=TcsComputation.Status.CONFIRMED)


class TcsComputationSerializer(serializers.ModelSerializer):
    section_code = serializers.CharField(source="section.section_code", read_only=True)

    class Meta:
        model = TcsComputation
        fields = [
            "id",
            "module_name",
            "document_type",
            "document_id",
            "document_no",
            "doc_date",
            "entity",
            "entityfin",
            "subentity",
            "party_account",
            "section",
            "section_code",
            "rule_snapshot_json",
            "applicability_status",
            "trigger_basis",
            "taxable_base",
            "excluded_base",
            "tcs_base_amount",
            "rate",
            "tcs_amount",
            "no_pan_applied",
            "lower_rate_applied",
            "override_reason",
            "overridden_by",
            "overridden_at",
            "fiscal_year",
            "quarter",
            "status",
            "computation_json",
            "created_at",
            "updated_at",
        ]


class TcsCollectionSerializer(RejectWorkflowManagedFieldsMixin, serializers.ModelSerializer):
    workflow_managed_write_errors = {
        "status": "status is managed by the TCS workflow and cannot be set directly.",
    }

    def validate(self, attrs):
        data = super().validate(attrs)
        instance = getattr(self, "instance", None)
        computation = data.get("computation") or getattr(instance, "computation", None)
        collection_date = data.get("collection_date") or getattr(instance, "collection_date", None)
        amount_received = data.get("amount_received")
        if amount_received is None and instance is not None:
            amount_received = instance.amount_received
        tcs_collected_amount = data.get("tcs_collected_amount")
        if tcs_collected_amount is None and instance is not None:
            tcs_collected_amount = instance.tcs_collected_amount

        if computation is None:
            return data

        if computation.status == TcsComputation.Status.REVERSED:
            raise serializers.ValidationError({"computation": "Cannot collect TCS for a reversed computation."})
        if q2(computation.tcs_amount or Decimal("0.00")) <= Decimal("0.00"):
            raise serializers.ValidationError({"computation": "Collection is allowed only when computed TCS amount is greater than 0."})
        if collection_date and computation.doc_date and collection_date < computation.doc_date:
            raise serializers.ValidationError({"collection_date": "Collection date cannot be before computation document date."})

        amount_received = q2(amount_received or Decimal("0.00"))
        tcs_collected_amount = q2(tcs_collected_amount or Decimal("0.00"))
        if tcs_collected_amount <= Decimal("0.00"):
            raise serializers.ValidationError({"tcs_collected_amount": "Collected amount must be greater than 0."})
        if amount_received < tcs_collected_amount:
            raise serializers.ValidationError({"tcs_collected_amount": "TCS collected amount cannot exceed amount received."})

        existing_total = (
            TcsCollection.objects.filter(computation=computation)
            .exclude(pk=getattr(instance, "pk", None))
            .exclude(status=TcsCollection.Status.CANCELLED)
            .aggregate(v=Sum("tcs_collected_amount"))
            .get("v")
            or Decimal("0.00")
        )
        if q2(existing_total + tcs_collected_amount) > q2(computation.tcs_amount):
            raise serializers.ValidationError({"tcs_collected_amount": "Total collections cannot exceed computed TCS amount."})
        return data

    class Meta:
        model = TcsCollection
        fields = [
            "id",
            "computation",
            "collection_date",
            "receipt_voucher_id",
            "amount_received",
            "tcs_collected_amount",
            "collection_reference",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["status", "created_at", "updated_at"]


class TcsDepositSerializer(RejectWorkflowManagedFieldsMixin, serializers.ModelSerializer):
    workflow_managed_write_errors = {
        "deposited_by": "deposited_by is managed by the TCS workflow and cannot be set directly.",
        "status": "status is managed by the TCS workflow and cannot be set directly.",
    }

    def validate(self, attrs):
        data = super().validate(attrs)
        instance = getattr(self, "instance", None)

        entity = data.get("entity") or getattr(instance, "entity", None)
        financial_year = (data.get("financial_year") or getattr(instance, "financial_year", "") or "").strip()
        month = data.get("month")
        if month is None and instance is not None:
            month = instance.month
        challan_no = (data.get("challan_no") or getattr(instance, "challan_no", "") or "").strip()
        total_deposit_amount = data.get("total_deposit_amount")
        if total_deposit_amount is None and instance is not None:
            total_deposit_amount = instance.total_deposit_amount

        if month is not None and (int(month) < 1 or int(month) > 12):
            raise serializers.ValidationError({"month": "Month must be between 1 and 12."})
        if financial_year and not _is_valid_fy_label(financial_year):
            raise serializers.ValidationError({"financial_year": "Financial year must be like 2025-26 (single-year span)."})

        if q2(total_deposit_amount or Decimal("0.00")) <= Decimal("0.00"):
            raise serializers.ValidationError({"total_deposit_amount": "Deposit amount must be greater than 0."})

        if entity is not None and financial_year and challan_no:
            clash_qs = TcsDeposit.objects.filter(
                entity=entity,
                financial_year=financial_year,
                challan_no__iexact=challan_no,
            )
            if instance is not None:
                clash_qs = clash_qs.exclude(pk=instance.pk)
            if clash_qs.exists():
                raise serializers.ValidationError(
                    {"challan_no": "Challan number already exists for this entity and financial year."}
                )
        return data

    class Meta:
        model = TcsDeposit
        fields = [
            "id",
            "entity",
            "financial_year",
            "month",
            "challan_no",
            "challan_date",
            "bsr_code",
            "cin",
            "bank_name",
            "total_deposit_amount",
            "deposited_by",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["deposited_by", "status", "created_at", "updated_at"]


class TcsDepositAllocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = TcsDepositAllocation
        fields = ["id", "deposit", "collection", "allocated_amount", "created_at"]
        read_only_fields = ["created_at"]


class TcsQuarterlyReturnSerializer(serializers.ModelSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        instance = getattr(self, "instance", None)
        is_filed_metadata_update = False
        if instance is not None and instance.status == TcsQuarterlyReturn.Status.FILED:
            allowed_fields = {"ack_no", "file_path", "notes", "filed_on", "original_return"}
            changed_fields = set(data.keys())
            if changed_fields.issubset(allowed_fields):
                is_filed_metadata_update = True
            else:
                raise serializers.ValidationError(
                    {"status": "Filed returns cannot be edited except for evidence metadata or correction linkage."}
                )
        fy = (data.get("fy") or getattr(instance, "fy", "") or "").strip()
        quarter = (data.get("quarter") or getattr(instance, "quarter", "") or "").strip().upper()
        form_name = (data.get("form_name") or getattr(instance, "form_name", "") or "").strip().upper()
        return_type = data.get("return_type") or getattr(instance, "return_type", TcsQuarterlyReturn.ReturnType.ORIGINAL)
        entity = data.get("entity") or getattr(instance, "entity", None)
        status_value = (data.get("status") or getattr(instance, "status", TcsQuarterlyReturn.Status.DRAFT) or "").strip().upper()
        ack_no = str(data.get("ack_no") if "ack_no" in data else getattr(instance, "ack_no", "") or "").strip()
        filed_on = data.get("filed_on") if "filed_on" in data else getattr(instance, "filed_on", None)
        file_path = str(data.get("file_path") if "file_path" in data else getattr(instance, "file_path", "") or "").strip()
        snapshot = data.get("json_snapshot") if "json_snapshot" in data else getattr(instance, "json_snapshot", None)

        if quarter and quarter not in {"Q1", "Q2", "Q3", "Q4"}:
            raise serializers.ValidationError({"quarter": "Quarter must be one of Q1, Q2, Q3, Q4."})
        if fy and not _is_valid_fy_label(fy):
            raise serializers.ValidationError({"fy": "FY must be like 2025-26 (single-year span)."})
        if form_name and form_name != "27EQ":
            raise serializers.ValidationError({"form_name": "Only form 27EQ is supported in this endpoint."})
        if status_value not in {
            TcsQuarterlyReturn.Status.DRAFT,
            TcsQuarterlyReturn.Status.VALIDATED,
            TcsQuarterlyReturn.Status.FILED,
        }:
            raise serializers.ValidationError({"status": "Status must be one of DRAFT, VALIDATED, FILED."})
        if status_value == TcsQuarterlyReturn.Status.FILED and not ack_no and not is_filed_metadata_update:
            raise serializers.ValidationError({"ack_no": "Acknowledgement No is required when status is FILED."})
        if status_value == TcsQuarterlyReturn.Status.FILED and filed_on is None and not is_filed_metadata_update:
            raise serializers.ValidationError({"filed_on": "Filed On date is required when status is FILED."})
        if status_value in {TcsQuarterlyReturn.Status.VALIDATED, TcsQuarterlyReturn.Status.FILED} and not snapshot and not is_filed_metadata_update:
            raise serializers.ValidationError({"json_snapshot": "Snapshot is required before validation or filing."})
        if return_type == TcsQuarterlyReturn.ReturnType.ORIGINAL and entity and fy and quarter:
            clash_qs = TcsQuarterlyReturn.objects.filter(
                entity=entity,
                fy=fy,
                quarter=quarter,
                form_name="27EQ",
                return_type=TcsQuarterlyReturn.ReturnType.ORIGINAL,
            )
            if instance is not None:
                clash_qs = clash_qs.exclude(pk=instance.pk)
            if clash_qs.exists():
                raise serializers.ValidationError(
                    {"return_type": "Original 27EQ return already exists for this entity/FY/quarter. Use Correction return."}
                )
        if return_type == TcsQuarterlyReturn.ReturnType.CORRECTION and entity and fy and quarter:
            original_return = data.get("original_return") if "original_return" in data else getattr(instance, "original_return", None)
            if original_return is None:
                raise serializers.ValidationError({"original_return": "Correction return requires an original return reference."})
            if getattr(original_return, "return_type", None) != TcsQuarterlyReturn.ReturnType.ORIGINAL:
                raise serializers.ValidationError({"original_return": "Correction return must reference an original 27EQ return."})
            if getattr(original_return, "entity_id", None) != getattr(entity, "id", entity):
                raise serializers.ValidationError({"original_return": "Original return must belong to the same entity."})
            if str(getattr(original_return, "fy", "") or "").strip() != fy:
                raise serializers.ValidationError({"original_return": "Original return must belong to the same financial year."})
            if str(getattr(original_return, "quarter", "") or "").strip().upper() != quarter:
                raise serializers.ValidationError({"original_return": "Original return must belong to the same quarter."})
            if getattr(original_return, "status", None) != TcsQuarterlyReturn.Status.FILED:
                raise serializers.ValidationError({"original_return": "Correction return requires a filed original return."})
            active_correction_qs = TcsQuarterlyReturn.objects.filter(
                entity_id=getattr(entity, "id", entity),
                fy=fy,
                quarter=quarter,
                form_name="27EQ",
                return_type=TcsQuarterlyReturn.ReturnType.CORRECTION,
                original_return_id=getattr(original_return, "id", original_return),
                status__in=[
                    TcsQuarterlyReturn.Status.DRAFT,
                    TcsQuarterlyReturn.Status.VALIDATED,
                ],
            )
            if instance is not None:
                active_correction_qs = active_correction_qs.exclude(pk=getattr(instance, "pk", None))
            if active_correction_qs.exists():
                raise serializers.ValidationError(
                    {"return_type": "An active correction 27EQ return already exists for this original return. Finish or file that correction first."}
                )
        if "json_snapshot" in data:
            data["json_snapshot"] = _json_safe_value(data.get("json_snapshot"))
        return data

    def create(self, validated_data):
        if "json_snapshot" in validated_data:
            validated_data["json_snapshot"] = _json_safe_value(validated_data.get("json_snapshot"))
        validated_data["form_name"] = str(validated_data.get("form_name") or "27EQ").strip().upper() or "27EQ"
        return TcsQuarterlyReturn.objects.create(**validated_data)

    def update(self, instance, validated_data):
        if "json_snapshot" in validated_data:
            validated_data["json_snapshot"] = _json_safe_value(validated_data.get("json_snapshot"))
        validated_data["form_name"] = str(validated_data.get("form_name") or instance.form_name or "27EQ").strip().upper() or "27EQ"
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance

    class Meta:
        model = TcsQuarterlyReturn
        fields = [
            "id",
            "entity",
            "fy",
            "quarter",
            "form_name",
            "return_type",
            "status",
            "ack_no",
            "filed_on",
            "json_snapshot",
            "file_path",
            "notes",
            "original_return",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "created_at",
            "updated_at",
        ]


class GstTcsEcoProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = GstTcsEcoProfile
        fields = [
            "id",
            "entity",
            "gstin",
            "is_eco",
            "section_code",
            "default_rate",
            "effective_from",
            "effective_to",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class GstTcsComputationSerializer(serializers.ModelSerializer):
    class Meta:
        model = GstTcsComputation
        fields = [
            "id",
            "entity",
            "eco_profile",
            "supplier_account",
            "doc_date",
            "document_type",
            "document_id",
            "document_no",
            "taxable_value",
            "gst_tcs_rate",
            "gst_tcs_amount",
            "fy",
            "month",
            "status",
            "snapshot_json",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class GstTcsComputeRequestSerializer(serializers.Serializer):
    entity_id = serializers.IntegerField()
    eco_profile_id = serializers.IntegerField()
    supplier_account_id = serializers.IntegerField()
    doc_date = serializers.DateField()
    document_type = serializers.CharField(required=False, allow_blank=True, default="invoice")
    document_id = serializers.IntegerField(required=False, allow_null=True)
    document_no = serializers.CharField(required=False, allow_blank=True, default="")
    taxable_value = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=ZERO2)
    gst_tcs_rate = serializers.DecimalField(max_digits=7, decimal_places=4, required=False, allow_null=True)
    status = serializers.ChoiceField(choices=GstTcsComputation.Status.choices, required=False, default=GstTcsComputation.Status.DRAFT)

    def validate(self, attrs):
        doc_date = attrs["doc_date"]
        fy, month, _ = determine_fy_quarter(doc_date)
        attrs["fy"] = fy
        attrs["month"] = month
        return attrs


def build_preview_payload(*, req: dict, user=None) -> dict:
    preview = compute_withholding_preview(**req)
    response = {
        "enabled": preview.enabled,
        "reason": preview.reason,
        "reason_code": preview.reason_code,
        "section_id": preview.section.id if preview.section else None,
        "section_code": preview.section.section_code if preview.section else None,
        "rate": q2(preview.rate),
        "base_amount": q2(preview.base_amount),
        "amount": q2(preview.amount),
        "section_law_type": getattr(preview.section, "law_type", None),
        "section_sub_type": getattr(preview.section, "sub_type", None),
    }
    if preview.reason_code == "DISABLED_206C_1H_BY_CONFIG":
        response["policy_warning"] = "206C(1H) is disabled by withholding configuration."
    if user:
        response["computed_by"] = user.id
    return response
