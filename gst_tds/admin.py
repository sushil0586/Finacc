from django.contrib import admin

from gst_tds.models import EntityGstTdsConfig, GstTdsContractLedger


@admin.register(EntityGstTdsConfig)
class EntityGstTdsConfigAdmin(admin.ModelAdmin):
    list_display = ("id", "entity", "subentity", "enabled", "threshold_amount", "enforce_pos_rule")
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
