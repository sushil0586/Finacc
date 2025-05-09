from django.contrib import admin
from import_export.admin import ImportExportMixin

from financial.models import accountHead,account,accounttype,ShippingDetails,staticacounts,staticacountsmapping
# Register your models here.


class accountheadAdmin(ImportExportMixin,admin.ModelAdmin):
    list_display = ['name','code','accountheadsr','entity','createdby']
    list_filter = (
        ('entity', admin.RelatedOnlyFieldListFilter),
    )
    
class accountAdmin(ImportExportMixin,admin.ModelAdmin):
    list_display = ['accountname','accounthead','accountcode','gstno','entity','createdby']
    list_filter = (
        ('entity', admin.RelatedOnlyFieldListFilter),
    )
    

admin.site.register(accountHead, accountheadAdmin)


admin.site.register(account,accountAdmin)
# admin.site.register(account_detials1)
# admin.site.register(account_detials2)

class accounttypeadmin(ImportExportMixin,admin.ModelAdmin):
    list_display = ['id', 'accounttypename','accounttypecode','entity']

admin.site.register(accounttype,accounttypeadmin)
admin.site.register(ShippingDetails)

class staticacountsadAdmin(ImportExportMixin,admin.ModelAdmin):
    list_display = ['accounttype','staticaccount','code']
 
admin.site.register(staticacounts,staticacountsadAdmin)
admin.site.register(staticacountsmapping)





