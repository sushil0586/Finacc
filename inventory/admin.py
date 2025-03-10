from django.contrib import admin
from inventory.models import Album,Track,Product,ProductCategory,UnitofMeasurement,typeofgoods,stkvaluationby,stkcalculateby,Ratecalculate,gsttype,HsnCode,HsnChaper,BillOfMaterial, BOMItem,ProductionOrder, ProductionConsumption
from import_export.admin import ImportExportMixin


class HSNChapterAdmin(ImportExportMixin,admin.ModelAdmin):
    list_display = ['Chapter','Description']
    search_fields = ['Chapter','Description']

class HSNAdmin(ImportExportMixin,admin.ModelAdmin):
    list_display = ['Chapter','hsnCode','Hsndescription','GSTRate']
    search_fields = ['hsnCode','Hsndescription']


class prductAdmin(ImportExportMixin,admin.ModelAdmin):
    list_display = ('productname',)
   

admin.site.register(Album)
admin.site.register(Track)
admin.site.register(ProductCategory)
admin.site.register(Product,prductAdmin)
admin.site.register(UnitofMeasurement)
admin.site.register(typeofgoods)
admin.site.register(stkvaluationby)
admin.site.register(stkcalculateby)
admin.site.register(Ratecalculate)
admin.site.register(gsttype)
admin.site.register(HsnChaper,HSNChapterAdmin)
admin.site.register(HsnCode,HSNAdmin)




@admin.register(BillOfMaterial)
class BillOfMaterialAdmin(admin.ModelAdmin):
    list_display = ['finished_good', 'version', 'is_active', 'created_at']
    list_filter = ['is_active', 'finished_good']
   
  

@admin.register(BOMItem)
class BOMItemAdmin(admin.ModelAdmin):
    list_display = ['bom', 'raw_material', 'wastage_material', 'is_percentage',
                    'quantity_required_per_unit', 'quantity_produced_per_unit']
    list_filter = ['is_percentage']


# Inline for ProductionConsumption inside ProductionOrder
class ProductionConsumptionInline(admin.TabularInline):
    model = ProductionConsumption
    extra = 1  # how many blank rows to show
    readonly_fields = ('batch_number', 'expiry_date')  # if needed
    fields = ('raw_material', 'quantity_consumed','wastage_sku', 'scrap_or_wastage', 'batch_number', 'expiry_date')

@admin.register(ProductionOrder)
class ProductionOrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'finished_good_display', 'bom', 'quantity_to_produce', 'status', 'production_date', 'created_by', 'updated_at')
    list_filter = ('status', 'production_date')
    search_fields = ('id', 'finished_good__productname', 'bom__id')
    inlines = [ProductionConsumptionInline]

    def finished_good_display(self, obj):
        return obj.finished_good.productname  # Ensure this field exists
    finished_good_display.short_description = "Finished Good"

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return ['production_date', 'created_by']
        return []

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)

@admin.register(ProductionConsumption)
class ProductionConsumptionAdmin(admin.ModelAdmin):
    list_display = ('production_order', 'raw_material_display', 'quantity_consumed','wastage_sku', 'scrap_or_wastage', 'batch_number', 'expiry_date')
    search_fields = ('production_order__id', 'raw_material__productname')

    def raw_material_display(self, obj):
        return obj.raw_material.productname  # Ensure this exists
    raw_material_display.short_description = "Raw Material"
   


# Register your models here.
