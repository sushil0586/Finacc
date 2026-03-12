from __future__ import annotations

from rest_framework import serializers

from assets.models import AssetCategory, AssetSettings, DepreciationRun, DepreciationRunLine, FixedAsset


class AssetSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetSettings
        exclude = ("created_at", "updated_at", "created_by", "updated_by", "is_active")


class AssetCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetCategory
        exclude = ("created_at", "updated_at", "created_by", "updated_by", "is_active")


class FixedAssetListSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    ledger_name = serializers.CharField(source="ledger.name", read_only=True)
    vendor_name = serializers.CharField(source="vendor_account.accountname", read_only=True)

    class Meta:
        model = FixedAsset
        fields = "__all__"


class FixedAssetWriteSerializer(serializers.ModelSerializer):
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


class DepreciationRunCreateSerializer(serializers.ModelSerializer):
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


class DepreciationRunCalculateSerializer(serializers.Serializer):
    category_id = serializers.IntegerField(required=False)
