from django.contrib import admin
from geography.models import country,state,district,city
from import_export.admin import ImportExportMixin

# Register your models here.


class countryAdmin(ImportExportMixin,admin.ModelAdmin):
    list_display = ['countrycode','countryname']



class stateAdmin(ImportExportMixin,admin.ModelAdmin):
    list_display = ['statecode','statename']

class districtAdmin(ImportExportMixin,admin.ModelAdmin):
    list_display = ['districtname','districtcode','state']
    search_fields = ['districtname']
    list_filter = (
        ('state', admin.RelatedOnlyFieldListFilter),
    )

class cityAdmin(ImportExportMixin,admin.ModelAdmin):
    list_display = ['cityname','citycode','distt','pincode']
    search_fields = ['cityname','pincode']
    list_filter = (
        ('distt', admin.RelatedOnlyFieldListFilter),
    )
   
    

admin.site.register(country,countryAdmin)

admin.site.register(state,stateAdmin)

admin.site.register(district,districtAdmin)

admin.site.register(city,cityAdmin)
