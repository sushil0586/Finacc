from django.contrib import admin
from geography.models import country,state,district,city
from import_export.admin import ImportExportMixin

# Register your models here.


class countryAdmin(ImportExportMixin,admin.ModelAdmin):
    list_display = ['countrycode','countryname']



class stateAdmin(ImportExportMixin,admin.ModelAdmin):
    list_display = ['statecode','statename']
   
    

admin.site.register(country,countryAdmin)

admin.site.register(state,stateAdmin)

admin.site.register(district)

admin.site.register(city)
