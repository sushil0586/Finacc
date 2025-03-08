from django.contrib import admin
from inventory.models import Album,Track,Product,ProductCategory,UnitofMeasurement,typeofgoods,stkvaluationby,stkcalculateby,Ratecalculate,gsttype,HsnCode,HsnChaper
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


# Register your models here.
