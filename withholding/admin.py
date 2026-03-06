from django.contrib import admin
from withholding.models import (
    EntityWithholdingConfig,
    GstTcsComputation,
    GstTcsEcoProfile,
    PartyTaxProfile,
    TcsCollection,
    TcsComputation,
    TcsDeposit,
    TcsDepositAllocation,
    TcsQuarterlyReturn,
    WithholdingSection,
)

@admin.register(WithholdingSection)
class WithholdingSectionAdmin(admin.ModelAdmin):
    list_display = ("tax_type", "section_code", "rate_default", "effective_from", "effective_to", "is_active")
    list_filter = ("tax_type", "is_active")
    search_fields = ("section_code", "description")

@admin.register(PartyTaxProfile)
class PartyTaxProfileAdmin(admin.ModelAdmin):
    list_display = ("party_account", "pan", "is_pan_available", "is_exempt_withholding", "lower_deduction_rate")
    search_fields = ("party_account__name", "pan")

@admin.register(EntityWithholdingConfig)
class EntityWithholdingConfigAdmin(admin.ModelAdmin):
    list_display = ("entity", "entityfin", "subentity", "enable_tds", "enable_tcs", "effective_from")
    list_filter = ("enable_tds", "enable_tcs")


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
