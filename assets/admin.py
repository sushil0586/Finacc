from django.contrib import admin

from .models import AssetCategory, AssetSettings, DepreciationRun, DepreciationRunLine, FixedAsset


@admin.register(AssetSettings)
class AssetSettingsAdmin(admin.ModelAdmin):
    list_display = ("entity", "subentity", "default_depreciation_method", "auto_post_depreciation", "is_active")
    list_filter = ("default_depreciation_method", "auto_post_depreciation", "is_active")
    search_fields = ("entity__entityname", "subentity__subentityname")


@admin.register(AssetCategory)
class AssetCategoryAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "entity", "subentity", "nature", "depreciation_method", "useful_life_months", "is_active")
    list_filter = ("nature", "depreciation_method", "entity", "is_active")
    search_fields = ("code", "name")


@admin.register(FixedAsset)
class FixedAssetAdmin(admin.ModelAdmin):
    list_display = ("asset_code", "asset_name", "entity", "category", "status", "capitalization_date", "gross_block", "net_book_value", "is_active")
    list_filter = ("entity", "status", "category", "depreciation_method", "is_active")
    search_fields = ("asset_code", "asset_name", "asset_tag", "serial_number", "purchase_document_no")


class DepreciationRunLineInline(admin.TabularInline):
    model = DepreciationRunLine
    extra = 0


@admin.register(DepreciationRun)
class DepreciationRunAdmin(admin.ModelAdmin):
    list_display = ("run_code", "entity", "entityfinid", "subentity", "period_from", "period_to", "posting_date", "status", "total_amount")
    list_filter = ("entity", "status", "depreciation_method")
    search_fields = ("run_code", "note")
    inlines = [DepreciationRunLineInline]
