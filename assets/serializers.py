from __future__ import annotations

from rest_framework import serializers

from assets.models import AssetCategory, AssetSettings, DepreciationRun, DepreciationRunLine, FixedAsset


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
    class Meta:
        model = AssetSettings
        exclude = ("created_at", "updated_at", "created_by", "updated_by", "is_active")


class AssetCategorySerializer(AssetScopeValidationMixin, serializers.ModelSerializer):
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
        return attrs


class FixedAssetListSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    ledger_name = serializers.CharField(source="ledger.name", read_only=True)
    vendor_name = serializers.CharField(source="vendor_account.accountname", read_only=True)

    class Meta:
        model = FixedAsset
        fields = "__all__"


class FixedAssetWriteSerializer(AssetScopeValidationMixin, serializers.ModelSerializer):
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

        return attrs


class AssetCapitalizeSerializer(serializers.Serializer):
    counter_ledger_id = serializers.IntegerField()
    capitalization_date = serializers.DateField()
    narration = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class AssetImpairSerializer(serializers.Serializer):
    impairment_amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    posting_date = serializers.DateField()
    narration = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class AssetTransferSerializer(serializers.Serializer):
    subentity_id = serializers.IntegerField(required=False, allow_null=True)
    location_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    department_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    custodian_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class AssetDisposalSerializer(serializers.Serializer):
    proceeds_ledger_id = serializers.IntegerField()
    disposal_date = serializers.DateField()
    sale_proceeds = serializers.DecimalField(max_digits=14, decimal_places=2)
    narration = serializers.CharField(required=False, allow_blank=True, allow_null=True)


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

        self._validate_subentity_scope(subentity=subentity, entity_id=entity.id)
        self._validate_related_entity(obj=entityfinid, entity_id=entity.id, field_name="entityfinid")
        return attrs


class DepreciationRunCalculateSerializer(serializers.Serializer):
    category_id = serializers.IntegerField(required=False)
