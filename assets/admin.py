from django.contrib import admin

from .models import AssetBulkJob, AssetCategory, AssetSettings, DepreciationRun, DepreciationRunLine, FixedAsset


class AssetScopedAdminMixin:
    list_per_page = 50
    readonly_fields = ("created_at", "updated_at", "created_by", "updated_by")


@admin.register(AssetSettings)
class AssetSettingsAdmin(AssetScopedAdminMixin, admin.ModelAdmin):
    list_display = (
        "entity",
        "subentity",
        "default_doc_code_asset",
        "default_depreciation_method",
        "depreciation_posting_day",
        "auto_number_assets",
        "auto_post_depreciation",
        "is_active",
    )
    list_filter = (
        ("entity", admin.RelatedOnlyFieldListFilter),
        ("subentity", admin.RelatedOnlyFieldListFilter),
        "default_depreciation_method",
        "default_workflow_action",
        "auto_number_assets",
        "auto_post_depreciation",
        "require_asset_tag",
        "is_active",
    )
    search_fields = ("entity__entityname", "subentity__subentityname", "default_doc_code_asset", "default_doc_code_disposal")
    list_select_related = ("entity", "subentity", "created_by", "updated_by")
    fieldsets = (
        ("Scope", {"fields": ("entity", "subentity", "is_active")}),
        (
            "Defaults",
            {
                "fields": (
                    "default_doc_code_asset",
                    "default_doc_code_disposal",
                    "default_workflow_action",
                    "default_depreciation_method",
                    "default_useful_life_months",
                    "default_residual_value_percent",
                    "depreciation_posting_day",
                    "capitalization_threshold",
                )
            },
        ),
        (
            "Controls",
            {
                "fields": (
                    "allow_multiple_asset_books",
                    "auto_post_depreciation",
                    "auto_number_assets",
                    "require_asset_tag",
                    "enable_component_accounting",
                    "enable_impairment_tracking",
                    "policy_controls",
                )
            },
        ),
        ("Audit", {"classes": ("collapse",), "fields": ("created_at", "updated_at", "created_by", "updated_by")}),
    )


@admin.register(AssetCategory)
class AssetCategoryAdmin(AssetScopedAdminMixin, admin.ModelAdmin):
    ordering = ("entity_id", "subentity_id", "name", "id")
    list_display = (
        "code",
        "name",
        "entity",
        "subentity",
        "nature",
        "depreciation_method",
        "useful_life_months",
        "capitalization_threshold",
        "is_active",
    )
    list_filter = (
        ("entity", admin.RelatedOnlyFieldListFilter),
        ("subentity", admin.RelatedOnlyFieldListFilter),
        "nature",
        "depreciation_method",
        "is_active",
    )
    search_fields = ("code", "name", "entity__entityname", "subentity__subentityname")
    list_select_related = ("entity", "subentity", "created_by", "updated_by")
    autocomplete_fields = (
        "entity",
        "subentity",
        "asset_ledger",
        "accumulated_depreciation_ledger",
        "depreciation_expense_ledger",
        "impairment_expense_ledger",
        "impairment_reserve_ledger",
        "cwip_ledger",
        "gain_on_sale_ledger",
        "loss_on_sale_ledger",
    )
    fieldsets = (
        ("Scope", {"fields": ("entity", "subentity", "is_active")}),
        (
            "Category",
            {
                "fields": (
                    "code",
                    "name",
                    "nature",
                    "depreciation_method",
                    "useful_life_months",
                    "residual_value_percent",
                    "capitalization_threshold",
                )
            },
        ),
        (
            "Posting Ledgers",
            {
                "fields": (
                    "asset_ledger",
                    "accumulated_depreciation_ledger",
                    "depreciation_expense_ledger",
                    "impairment_expense_ledger",
                    "impairment_reserve_ledger",
                    "cwip_ledger",
                    "gain_on_sale_ledger",
                    "loss_on_sale_ledger",
                )
            },
        ),
        ("Audit", {"classes": ("collapse",), "fields": ("created_at", "updated_at", "created_by", "updated_by")}),
    )


@admin.register(AssetBulkJob)
class AssetBulkJobAdmin(AssetScopedAdminMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "scope_type",
        "job_type",
        "status",
        "file_format",
        "entity",
        "subentity",
        "input_filename",
        "is_active",
    )
    list_filter = (
        ("entity", admin.RelatedOnlyFieldListFilter),
        ("subentity", admin.RelatedOnlyFieldListFilter),
        "scope_type",
        "job_type",
        "status",
        "file_format",
        "is_active",
    )
    search_fields = ("input_filename", "validation_token")
    list_select_related = ("entity", "subentity", "created_by", "updated_by")
    readonly_fields = AssetScopedAdminMixin.readonly_fields + ("summary", "errors", "payload", "validation_token", "input_filename")


@admin.register(FixedAsset)
class FixedAssetAdmin(AssetScopedAdminMixin, admin.ModelAdmin):
    list_display = (
        "asset_code",
        "asset_name",
        "entity",
        "subentity",
        "category",
        "status",
        "acquisition_date",
        "capitalization_date",
        "gross_block",
        "accumulated_depreciation",
        "net_book_value",
        "is_active",
    )
    list_filter = (
        ("entity", admin.RelatedOnlyFieldListFilter),
        ("subentity", admin.RelatedOnlyFieldListFilter),
        ("category", admin.RelatedOnlyFieldListFilter),
        "status",
        "depreciation_method",
        "is_active",
    )
    search_fields = (
        "asset_code",
        "asset_name",
        "asset_tag",
        "serial_number",
        "manufacturer",
        "model_number",
        "purchase_document_no",
        "external_reference",
    )
    list_select_related = (
        "entity",
        "entityfinid",
        "subentity",
        "category",
        "ledger",
        "vendor_account",
        "capitalization_posting_batch",
        "impairment_posting_batch",
        "disposal_posting_batch",
        "created_by",
        "updated_by",
    )
    autocomplete_fields = (
        "entity",
        "subentity",
        "category",
        "ledger",
        "vendor_account",
    )
    raw_id_fields = (
        "entityfinid",
        "capitalization_posting_batch",
        "impairment_posting_batch",
        "disposal_posting_batch",
    )
    readonly_fields = AssetScopedAdminMixin.readonly_fields + (
        "capitalization_posting_batch",
        "impairment_posting_batch",
        "disposal_posting_batch",
        "disposal_proceeds",
        "disposal_gain_loss",
    )
    fieldsets = (
        ("Scope", {"fields": ("entity", "entityfinid", "subentity", "is_active")}),
        (
            "Asset Identity",
            {
                "fields": (
                    "category",
                    "ledger",
                    "asset_code",
                    "asset_name",
                    "asset_tag",
                    "serial_number",
                    "manufacturer",
                    "model_number",
                    "status",
                )
            },
        ),
        (
            "Dates",
            {
                "fields": (
                    "acquisition_date",
                    "capitalization_date",
                    "put_to_use_date",
                    "depreciation_start_date",
                    "disposal_date",
                )
            },
        ),
        (
            "Valuation",
            {
                "fields": (
                    "quantity",
                    "gross_block",
                    "residual_value",
                    "useful_life_months",
                    "depreciation_method",
                    "depreciation_rate",
                    "accumulated_depreciation",
                    "impairment_amount",
                    "net_book_value",
                )
            },
        ),
        (
            "Operations",
            {
                "fields": (
                    "location_name",
                    "department_name",
                    "custodian_name",
                    "vendor_account",
                    "purchase_document_no",
                    "external_reference",
                    "notes",
                )
            },
        ),
        (
            "Posting Lifecycle",
            {
                "fields": (
                    "capitalization_posting_batch",
                    "impairment_posting_batch",
                    "disposal_posting_batch",
                    "disposal_proceeds",
                    "disposal_gain_loss",
                )
            },
        ),
        ("Audit", {"classes": ("collapse",), "fields": ("created_at", "updated_at", "created_by", "updated_by")}),
    )


class DepreciationRunLineInline(admin.TabularInline):
    model = DepreciationRunLine
    extra = 0
    fields = (
        "asset",
        "period_from",
        "period_to",
        "opening_gross_block",
        "opening_accumulated_depreciation",
        "depreciation_amount",
        "closing_accumulated_depreciation",
        "closing_net_book_value",
        "is_manual_override",
        "calculation_meta",
        "created_at",
    )
    readonly_fields = fields
    autocomplete_fields = ("asset",)
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DepreciationRun)
class DepreciationRunAdmin(AssetScopedAdminMixin, admin.ModelAdmin):
    list_display = (
        "run_code",
        "entity",
        "entityfinid",
        "subentity",
        "period_from",
        "period_to",
        "posting_date",
        "status",
        "total_assets",
        "total_amount",
    )
    list_filter = (
        ("entity", admin.RelatedOnlyFieldListFilter),
        ("entityfinid", admin.RelatedOnlyFieldListFilter),
        ("subentity", admin.RelatedOnlyFieldListFilter),
        "status",
        "depreciation_method",
    )
    search_fields = ("run_code", "note")
    list_select_related = ("entity", "entityfinid", "subentity", "posting_batch", "posted_by", "created_by", "updated_by")
    autocomplete_fields = ("entity", "subentity")
    raw_id_fields = ("entityfinid", "posting_batch", "posted_by")
    readonly_fields = AssetScopedAdminMixin.readonly_fields + ("calculated_at", "posted_at", "posted_by")
    fieldsets = (
        ("Scope", {"fields": ("entity", "entityfinid", "subentity", "is_active")}),
        (
            "Run",
            {
                "fields": (
                    "run_code",
                    "period_from",
                    "period_to",
                    "posting_date",
                    "status",
                    "depreciation_method",
                    "note",
                )
            },
        ),
        ("Totals", {"fields": ("total_assets", "total_amount")}),
        ("Posting", {"fields": ("posting_batch", "calculated_at", "posted_at", "posted_by")}),
        ("Audit", {"classes": ("collapse",), "fields": ("created_at", "updated_at", "created_by", "updated_by")}),
    )
    inlines = [DepreciationRunLineInline]


@admin.register(DepreciationRunLine)
class DepreciationRunLineAdmin(admin.ModelAdmin):
    list_display = (
        "run",
        "asset",
        "period_from",
        "period_to",
        "depreciation_amount",
        "closing_accumulated_depreciation",
        "closing_net_book_value",
        "is_manual_override",
    )
    list_filter = (
        ("run__entity", admin.RelatedOnlyFieldListFilter),
        ("run__entityfinid", admin.RelatedOnlyFieldListFilter),
        "is_manual_override",
    )
    search_fields = ("run__run_code", "asset__asset_code", "asset__asset_name")
    list_select_related = ("run", "asset", "asset__category")
    autocomplete_fields = ("run", "asset")
    readonly_fields = [field.name for field in DepreciationRunLine._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
