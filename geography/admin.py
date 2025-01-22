from django.contrib import admin
from geography.models import Country,State,District,City
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
   
    

admin.site.register(Country,countryAdmin)

admin.site.register(State,stateAdmin)

admin.site.register(District,districtAdmin)

admin.site.register(City,cityAdmin)
