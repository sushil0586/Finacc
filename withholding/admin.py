from django.contrib import admin
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
)

@admin.register(WithholdingSection)
class WithholdingSectionAdmin(admin.ModelAdmin):
    list_display = (
        "tax_type",
        "section_code",
        "rate_default",
        "higher_rate_no_pan",
        "higher_rate_206ab",
        "effective_from",
        "effective_to",
        "is_active",
    )
    list_filter = ("tax_type", "is_active")
    search_fields = ("section_code", "description")


@admin.register(WithholdingSectionPolicyAudit)
class WithholdingSectionPolicyAuditAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "section", "changed_by", "source")
    list_filter = ("action", "source", "section__tax_type")
    search_fields = ("section__section_code", "changed_by__email")
    readonly_fields = (
        "section",
        "action",
        "changed_by",
        "changed_fields_json",
        "before_snapshot_json",
        "after_snapshot_json",
        "source",
        "created_at",
    )

@admin.register(PartyTaxProfile)
class PartyTaxProfileAdmin(admin.ModelAdmin):
    list_display = (
        "party_account",
        "pan",
        "is_pan_available",
        "is_exempt_withholding",
        "is_specified_person_206ab",
        "lower_deduction_rate",
    )
    search_fields = ("party_account__accountname", "pan")


@admin.register(EntityPartyTaxProfile)
class EntityPartyTaxProfileAdmin(admin.ModelAdmin):
    list_display = (
        "entity",
        "subentity",
        "party_account",
        "residency_status",
        "tax_identifier",
        "treaty_rate",
        "is_exempt_withholding",
        "is_specified_person_206ab",
        "lower_deduction_rate",
        "is_active",
    )
    list_filter = ("entity", "subentity", "residency_status", "is_active", "is_exempt_withholding", "is_specified_person_206ab")
    search_fields = ("party_account__accountname",)
    autocomplete_fields = ("entity", "subentity", "party_account")

@admin.register(EntityWithholdingConfig)
class EntityWithholdingConfigAdmin(admin.ModelAdmin):
    list_display = (
        "entity",
        "entityfin",
        "subentity",
        "enable_tds",
        "enable_tcs",
        "apply_tcs_206c1h",
        "tcs_206c1h_prev_fy_turnover",
        "tcs_206c1h_turnover_limit",
        "tcs_206c1h_force_eligible",
        "effective_from",
    )
    list_filter = ("enable_tds", "enable_tcs")


@admin.register(EntityTcsThresholdOpening)
class EntityTcsThresholdOpeningAdmin(admin.ModelAdmin):
    list_display = (
        "entity",
        "entityfin",
        "subentity",
        "party_account",
        "section",
        "opening_base_amount",
        "effective_from",
        "is_active",
    )
    list_filter = ("entity", "entityfin", "subentity", "section", "is_active")
    search_fields = ("party_account__accountname", "section__section_code")
    autocomplete_fields = ("entity", "entityfin", "subentity", "party_account", "section")


@admin.register(EntityWithholdingSectionPostingMap)
class EntityWithholdingSectionPostingMapAdmin(admin.ModelAdmin):
    list_display = (
        "entity",
        "subentity",
        "section",
        "payable_account",
        "payable_ledger",
        "effective_from",
        "is_active",
    )
    list_filter = ("entity", "subentity", "section__tax_type", "is_active")
    search_fields = ("section__section_code", "section__description", "payable_account__accountname")
    autocomplete_fields = ("entity", "subentity", "section", "payable_account", "payable_ledger")


@admin.register(TcsComputation)
class TcsComputationAdmin(admin.ModelAdmin):
    list_display = ("module_name", "document_type", "document_id", "doc_date", "section", "rate", "tcs_amount", "status")
    list_filter = ("module_name", "document_type", "status", "fiscal_year", "quarter")
    search_fields = ("document_no",)


@admin.register(TcsCollection)
class TcsCollectionAdmin(admin.ModelAdmin):
    list_display = ("computation", "collection_date", "tcs_collected_amount", "status")
    list_filter = ("status",)


@admin.register(TcsDeposit)
class TcsDepositAdmin(admin.ModelAdmin):
    list_display = ("entity", "financial_year", "month", "challan_no", "total_deposit_amount", "status")
    list_filter = ("status", "financial_year", "month")


@admin.register(TcsDepositAllocation)
class TcsDepositAllocationAdmin(admin.ModelAdmin):
    list_display = ("deposit", "collection", "allocated_amount", "created_at")


@admin.register(TcsQuarterlyReturn)
class TcsQuarterlyReturnAdmin(admin.ModelAdmin):
    list_display = ("entity", "fy", "quarter", "form_name", "return_type", "status", "ack_no")
    list_filter = ("form_name", "status", "quarter", "fy")


@admin.register(GstTcsEcoProfile)
class GstTcsEcoProfileAdmin(admin.ModelAdmin):
    list_display = ("entity", "gstin", "is_eco", "default_rate", "effective_from", "is_active")
    list_filter = ("is_eco", "is_active")


@admin.register(GstTcsComputation)
class GstTcsComputationAdmin(admin.ModelAdmin):
    list_display = ("entity", "document_type", "document_id", "doc_date", "gst_tcs_rate", "gst_tcs_amount", "status")
    list_filter = ("status", "fy", "month")
