from django.contrib import admin

from gst_tds.models import EntityGstTdsConfig, GstTdsContractLedger, GstTdsMasterRule


@admin.register(GstTdsMasterRule)
class GstTdsMasterRuleAdmin(admin.ModelAdmin):
    list_display = ("id", "code", "section_code", "total_rate", "effective_from", "effective_to", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "label", "section_code")


@admin.register(EntityGstTdsConfig)
class EntityGstTdsConfigAdmin(admin.ModelAdmin):
    list_display = ("id", "entity", "subentity", "master_rule", "enabled", "threshold_amount", "enforce_pos_rule")
    list_filter = ("enabled", "enforce_pos_rule", "entity")
    search_fields = ("entity__entityname", "subentity__subentityname")


@admin.register(GstTdsContractLedger)
class GstTdsContractLedgerAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "entity",
        "entityfinid",
        "subentity",
        "vendor",
        "contract_ref",
        "cumulative_taxable",
        "cumulative_tds",
        "updated_at",
    )
    list_filter = ("entity", "entityfinid", "subentity")
    search_fields = ("vendor__accountname", "contract_ref")
