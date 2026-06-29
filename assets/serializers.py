from __future__ import annotations

from django.db.models import Q
from rest_framework import serializers

from assets.models import AssetCategory, AssetSettings, DepreciationRun, DepreciationRunLine, FixedAsset
from assets.services.settings import AssetSettingsService


def _run_scope_overlap_q(*, subentity_id: int | None):
    if subentity_id is None:
        return Q()
    return Q(subentity_id__isnull=True) | Q(subentity_id=subentity_id)


class AssetScopeValidationMixin:
    @staticmethod
    def _scope_error(field_name: str, message: str) -> serializers.ValidationError:
        return serializers.ValidationError({field_name: message})

    def _resolve_entity(self, attrs):
        instance = getattr(self, "instance", None)
        entity = attrs.get("entity") or getattr(instance, "entity", None)
        if entity is None:
            raise self._scope_error("entity", "Entity is required.")
        return entity

    @staticmethod
    def _validate_related_entity(*, obj, entity_id: int, field_name: str):
        if obj is None:
            return
        obj_entity_id = getattr(obj, "entity_id", None)
        if obj_entity_id is not None and obj_entity_id != entity_id:
            raise serializers.ValidationError({field_name: "Selected record belongs to a different entity."})

    @staticmethod
    def _validate_subentity_scope(*, subentity, entity_id: int):
        if subentity is None:
            return
        if getattr(subentity, "entity_id", None) != entity_id:
            raise serializers.ValidationError({"subentity": "Selected subentity belongs to a different entity."})


class AssetSettingsSerializer(serializers.ModelSerializer):
    default_doc_code_asset = serializers.CharField(max_length=10, required=False)
    default_doc_code_disposal = serializers.CharField(max_length=10, required=False)

    class Meta:
        model = AssetSettings
        exclude = ("created_at", "updated_at", "created_by", "updated_by", "is_active")


class AssetCategorySerializer(AssetScopeValidationMixin, serializers.ModelSerializer):
    code = serializers.CharField(max_length=30)
    name = serializers.CharField(max_length=255)

    class Meta:
        model = AssetCategory
        exclude = ("created_at", "updated_at", "created_by", "updated_by", "is_active")

    def validate(self, attrs):
        entity = self._resolve_entity(attrs)
        subentity = attrs.get("subentity") or getattr(getattr(self, "instance", None), "subentity", None)
        self._validate_subentity_scope(subentity=subentity, entity_id=entity.id)
        for field_name in (
            "asset_ledger",
            "accumulated_depreciation_ledger",
            "depreciation_expense_ledger",
            "impairment_expense_ledger",
            "impairment_reserve_ledger",
            "cwip_ledger",
            "gain_on_sale_ledger",
            "loss_on_sale_ledger",
        ):
            self._validate_related_entity(
                obj=attrs.get(field_name) or getattr(getattr(self, "instance", None), field_name, None),
                entity_id=entity.id,
                field_name=field_name,
            )
        try:
            attrs["traceability_controls"] = AssetSettingsService.normalize_category_traceability_controls(
                attrs.get("traceability_controls") if "traceability_controls" in attrs else getattr(getattr(self, "instance", None), "traceability_controls", {})
            )
        except ValueError as exc:
            raise serializers.ValidationError({"traceability_controls": str(exc)})
        try:
            attrs["accounting_controls"] = AssetSettingsService.normalize_category_accounting_controls(
                attrs.get("accounting_controls") if "accounting_controls" in attrs else getattr(getattr(self, "instance", None), "accounting_controls", {})
            )
        except ValueError as exc:
            raise serializers.ValidationError({"accounting_controls": str(exc)})

        settings_obj = AssetSettingsService.get_settings(entity.id, getattr(subentity, "id", None))
        resolved_accounting_controls = AssetSettingsService.resolve_category_accounting_controls(
            type("CategoryStub", (), {"accounting_controls": attrs.get("accounting_controls", {}), "nature": attrs.get("nature") or getattr(getattr(self, "instance", None), "nature", None)})(),
            settings_obj,
        )
        accounting_errors = {}
        if resolved_accounting_controls.get("asset_ledger_rule") == "hard" and not (attrs.get("asset_ledger") or getattr(getattr(self, "instance", None), "asset_ledger", None)):
            accounting_errors["asset_ledger"] = ["Select the asset ledger because policy marks it as required for this category."]
        if resolved_accounting_controls.get("depreciation_ledgers_rule") == "hard":
            if not (attrs.get("accumulated_depreciation_ledger") or getattr(getattr(self, "instance", None), "accumulated_depreciation_ledger", None)):
                accounting_errors["accumulated_depreciation_ledger"] = ["Select the accumulated depreciation ledger because policy marks depreciation ledgers as required."]
            if not (attrs.get("depreciation_expense_ledger") or getattr(getattr(self, "instance", None), "depreciation_expense_ledger", None)):
                accounting_errors["depreciation_expense_ledger"] = ["Select the depreciation expense ledger because policy marks depreciation ledgers as required."]
        if resolved_accounting_controls.get("impairment_ledgers_rule") == "hard":
            if not (attrs.get("impairment_expense_ledger") or getattr(getattr(self, "instance", None), "impairment_expense_ledger", None)):
                accounting_errors["impairment_expense_ledger"] = ["Select the impairment expense ledger because policy marks impairment ledgers as required."]
            if not (attrs.get("impairment_reserve_ledger") or getattr(getattr(self, "instance", None), "impairment_reserve_ledger", None)):
                accounting_errors["impairment_reserve_ledger"] = ["Select the impairment reserve ledger because policy marks impairment ledgers as required."]
        if resolved_accounting_controls.get("disposal_ledgers_rule") == "hard":
            if not (attrs.get("gain_on_sale_ledger") or getattr(getattr(self, "instance", None), "gain_on_sale_ledger", None)):
                accounting_errors["gain_on_sale_ledger"] = ["Select the gain on sale ledger because policy marks disposal ledgers as required."]
            if not (attrs.get("loss_on_sale_ledger") or getattr(getattr(self, "instance", None), "loss_on_sale_ledger", None)):
                accounting_errors["loss_on_sale_ledger"] = ["Select the loss on sale ledger because policy marks disposal ledgers as required."]
        nature_value = attrs.get("nature") or getattr(getattr(self, "instance", None), "nature", None)
        if resolved_accounting_controls.get("cwip_ledger_rule") == "hard" and nature_value == AssetCategory.AssetNature.CAPITAL_WIP:
            if not (attrs.get("cwip_ledger") or getattr(getattr(self, "instance", None), "cwip_ledger", None)):
                accounting_errors["cwip_ledger"] = ["Select the CWIP ledger because policy marks it as required for CWIP categories."]
        if accounting_errors:
            raise serializers.ValidationError(accounting_errors)
        return attrs


class FixedAssetListSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    ledger_name = serializers.CharField(source="ledger.name", read_only=True)
    vendor_name = serializers.CharField(source="vendor_account.accountname", read_only=True)
    is_purchase_intake = serializers.SerializerMethodField()
    source_purchase_line_ids = serializers.SerializerMethodField()
    source_purchase_numbers = serializers.SerializerMethodField()

    class Meta:
        model = FixedAsset
        fields = "__all__"

    def get_is_purchase_intake(self, obj):
        lines = getattr(obj, "source_purchase_lines", None)
        has_source_lines = bool(lines.exists()) if lines is not None else False
        return bool(getattr(obj, "purchase_document_no", None) or has_source_lines)

    def get_source_purchase_line_ids(self, obj):
        lines = getattr(obj, "source_purchase_lines", None)
        if lines is None:
            return []
        return [line.id for line in lines.all()]

    def get_source_purchase_numbers(self, obj):
        lines = getattr(obj, "source_purchase_lines", None)
        if lines is None:
            return [obj.purchase_document_no] if obj.purchase_document_no else []
        numbers = []
        seen = set()
        for line in lines.all():
            header = getattr(line, "header", None)
            number = getattr(header, "purchase_number", None) or getattr(obj, "purchase_document_no", None)
            if not number or number in seen:
                continue
            seen.add(number)
            numbers.append(number)
        if not numbers and obj.purchase_document_no:
            numbers.append(obj.purchase_document_no)
        return numbers


class FixedAssetWriteSerializer(AssetScopeValidationMixin, serializers.ModelSerializer):
    asset_code = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=50)
    asset_name = serializers.CharField(max_length=255)
    asset_tag = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=100)
    serial_number = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=100)
    manufacturer = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=255)
    model_number = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=100)
    location_name = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=255)
    department_name = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=255)
    custodian_name = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=255)
    purchase_document_no = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=100)
    external_reference = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=100)
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=500)
    MANUALLY_SETTABLE_STATUSES = {
        FixedAsset.AssetStatus.DRAFT,
        FixedAsset.AssetStatus.CAPITAL_WIP,
        FixedAsset.AssetStatus.HELD_FOR_SALE,
    }
    SYSTEM_MANAGED_INPUT_FIELDS = (
        "accumulated_depreciation",
        "impairment_amount",
        "net_book_value",
        "impairment_posting_batch",
        "disposal_proceeds",
        "disposal_gain_loss",
    )

    class Meta:
        model = FixedAsset
        exclude = (
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "is_active",
            "capitalization_posting_batch",
            "disposal_posting_batch",
        )
        read_only_fields = (
            "accumulated_depreciation",
            "impairment_amount",
            "net_book_value",
            "impairment_posting_batch",
            "disposal_proceeds",
            "disposal_gain_loss",
        )
        extra_kwargs = {
            "asset_code": {"required": False, "allow_blank": True},
        }

    def to_internal_value(self, data):
        system_managed_errors = {}
        for field_name in self.SYSTEM_MANAGED_INPUT_FIELDS:
            if field_name in data:
                system_managed_errors[field_name] = ["This field is system managed and cannot be set directly."]
        if system_managed_errors:
            raise serializers.ValidationError(system_managed_errors)
        return super().to_internal_value(data)

    def get_validators(self):
        validators = super().get_validators()
        filtered_validators = []
        for validator in validators:
            fields = tuple(getattr(validator, "fields", ()))
            if fields == ("entity", "asset_code"):
                continue
            filtered_validators.append(validator)
        return filtered_validators

    def validate(self, attrs):
        entity = self._resolve_entity(attrs)
        instance = getattr(self, "instance", None)
        subentity = attrs.get("subentity") or getattr(instance, "subentity", None)
        category = attrs.get("category") or getattr(instance, "category", None)
        ledger = attrs.get("ledger") or getattr(instance, "ledger", None)
        vendor_account = attrs.get("vendor_account") or getattr(instance, "vendor_account", None)
        entityfinid = attrs.get("entityfinid") or getattr(instance, "entityfinid", None)

        self._validate_subentity_scope(subentity=subentity, entity_id=entity.id)
        self._validate_related_entity(obj=category, entity_id=entity.id, field_name="category")
        self._validate_related_entity(obj=ledger, entity_id=entity.id, field_name="ledger")
        self._validate_related_entity(obj=vendor_account, entity_id=entity.id, field_name="vendor_account")
        self._validate_related_entity(obj=entityfinid, entity_id=entity.id, field_name="entityfinid")

        if category is not None and getattr(category, "subentity_id", None) is not None:
            if subentity is None:
                raise serializers.ValidationError({"subentity": "This category is scoped to a subentity and requires the same subentity on the asset."})
            if category.subentity_id != subentity.id:
                raise serializers.ValidationError({"category": "Selected category belongs to a different subentity."})

        status_value = attrs.get("status")
        if status_value and status_value not in self.MANUALLY_SETTABLE_STATUSES:
            raise serializers.ValidationError(
                {"status": "Status can only be set manually to Draft, Capital WIP, or Held for Sale. Use asset lifecycle actions for active or disposed states."}
            )

        settings_obj = AssetSettingsService.get_settings(entity.id, getattr(subentity, "id", None))
        controls = AssetSettingsService.resolve_policy_controls(settings_obj)
        field_values = {
            "location_name": attrs.get("location_name", getattr(instance, "location_name", None)),
            "department_name": attrs.get("department_name", getattr(instance, "department_name", None)),
            "custodian_name": attrs.get("custodian_name", getattr(instance, "custodian_name", None)),
        }
        field_labels = {
            "location_name": "location",
            "department_name": "department",
            "custodian_name": "custodian",
        }
        field_rules = {
            "location_name": controls.get("require_location_rule", "off"),
            "department_name": controls.get("require_department_rule", "off"),
            "custodian_name": controls.get("require_custodian_rule", "off"),
        }
        field_errors = {}
        for field_name, value in field_values.items():
            if field_rules[field_name] == "hard" and not str(value or "").strip():
                field_errors[field_name] = [f"Enter the asset {field_labels[field_name]} before saving because policy marks it as required."]
        if field_errors:
            raise serializers.ValidationError(field_errors)

        return attrs


class AssetCapitalizeSerializer(serializers.Serializer):
    counter_ledger_id = serializers.IntegerField()
    capitalization_date = serializers.DateField()
    narration = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=500)
    location_name = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=255)
    department_name = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=255)
    custodian_name = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=255)
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=500)


class AssetImpairSerializer(serializers.Serializer):
    impairment_amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    posting_date = serializers.DateField()
    narration = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=500)


class AssetTransferSerializer(serializers.Serializer):
    subentity_id = serializers.IntegerField(required=False, allow_null=True)
    location_name = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=255)
    department_name = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=255)
    custodian_name = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=255)
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=500)


class AssetDisposalSerializer(serializers.Serializer):
    proceeds_ledger_id = serializers.IntegerField()
    disposal_date = serializers.DateField()
    sale_proceeds = serializers.DecimalField(max_digits=14, decimal_places=2)
    narration = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=500)


class AssetReverseLifecycleSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500)


class DepreciationRunLineSerializer(serializers.ModelSerializer):
    asset_code = serializers.CharField(source="asset.asset_code", read_only=True)
    asset_name = serializers.CharField(source="asset.asset_name", read_only=True)
    category_name = serializers.CharField(source="asset.category.name", read_only=True)

    class Meta:
        model = DepreciationRunLine
        fields = "__all__"


class DepreciationRunSerializer(serializers.ModelSerializer):
    lines = DepreciationRunLineSerializer(many=True, read_only=True)

    class Meta:
        model = DepreciationRun
        exclude = ("created_at", "updated_at", "created_by", "updated_by", "is_active")


class DepreciationRunCreateSerializer(AssetScopeValidationMixin, serializers.ModelSerializer):
    class Meta:
        model = DepreciationRun
        exclude = (
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "is_active",
            "total_assets",
            "total_amount",
            "posting_batch",
            "calculated_at",
            "posted_at",
            "posted_by",
        )

    def validate(self, attrs):
        entity = self._resolve_entity(attrs)
        instance = getattr(self, "instance", None)
        subentity = attrs.get("subentity") or getattr(instance, "subentity", None)
        entityfinid = attrs.get("entityfinid") or getattr(instance, "entityfinid", None)
        period_from = attrs.get("period_from") or getattr(instance, "period_from", None)
        period_to = attrs.get("period_to") or getattr(instance, "period_to", None)
        posting_date = attrs.get("posting_date") or getattr(instance, "posting_date", None)

        self._validate_subentity_scope(subentity=subentity, entity_id=entity.id)
        self._validate_related_entity(obj=entityfinid, entity_id=entity.id, field_name="entityfinid")

        if period_from and period_to and period_from > period_to:
            raise serializers.ValidationError({"period_to": "Period to must be on or after period from."})
        if posting_date and period_from and posting_date < period_from:
            raise serializers.ValidationError({"posting_date": "Posting date cannot be earlier than period from."})

        if entityfinid and period_from and period_to:
            overlap_qs = DepreciationRun.objects.filter(
                entity_id=entity.id,
                entityfinid_id=entityfinid.id,
                status__in=[
                    DepreciationRun.RunStatus.DRAFT,
                    DepreciationRun.RunStatus.CALCULATED,
                    DepreciationRun.RunStatus.POSTED,
                ],
                period_from__lte=period_to,
                period_to__gte=period_from,
            ).filter(_run_scope_overlap_q(subentity_id=getattr(subentity, "id", None)))
            if instance is not None and instance.pk:
                overlap_qs = overlap_qs.exclude(pk=instance.pk)
            if overlap_qs.exists():
                raise serializers.ValidationError(
                    {
                        "non_field_errors": [
                            "An overlapping depreciation run already exists in this scope. Cancel or move the existing run before creating another one."
                        ]
                    }
                )
        return attrs


class DepreciationRunCalculateSerializer(serializers.Serializer):
    category_id = serializers.IntegerField(required=False)
