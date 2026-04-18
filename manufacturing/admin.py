from django.contrib import admin

from .models import (
    ManufacturingBOM,
    ManufacturingBOMMaterial,
    ManufacturingSettings,
    ManufacturingWorkOrder,
    ManufacturingWorkOrderMaterial,
    ManufacturingWorkOrderOutput,
)


@admin.register(ManufacturingBOM)
class ManufacturingBOMAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "entity", "subentity", "finished_product", "is_active")
    list_filter = ("entity", "subentity", "is_active")
    search_fields = ("code", "name", "finished_product__productname", "finished_product__sku")


@admin.register(ManufacturingWorkOrder)
class ManufacturingWorkOrderAdmin(admin.ModelAdmin):
    list_display = ("work_order_no", "production_date", "entity", "subentity", "status", "posting_entry_id")
    list_filter = ("entity", "subentity", "status")
    search_fields = ("work_order_no", "reference_no", "narration")


admin.site.register(ManufacturingBOMMaterial)
admin.site.register(ManufacturingSettings)
admin.site.register(ManufacturingWorkOrderMaterial)
admin.site.register(ManufacturingWorkOrderOutput)

