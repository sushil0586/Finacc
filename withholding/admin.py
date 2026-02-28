from django.contrib import admin
from withholding.models import WithholdingSection, PartyTaxProfile, EntityWithholdingConfig

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