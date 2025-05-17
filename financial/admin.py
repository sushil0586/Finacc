from django.contrib import admin
from import_export.admin import ImportExportMixin


from financial.models import accountHead,account,accounttype,ShippingDetails,staticacounts,staticacountsmapping,ContactDetails
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
@admin.register(ContactDetails)
class ContactDetailsAdmin(admin.ModelAdmin):
    list_display = (
        'full_name',
        'account_name',
        'address1',
        'city',
        'district',
        'state',
        'country',
        'pincode',
        'phoneno',
    )
    search_fields = ('full_name', 'account__accountname', 'phoneno', 'pincode')
    list_filter = ('country', 'state', 'district', 'city')

    def account_name(self, obj):
        return obj.account.accountname
    account_name.short_description = 'Account Name'

class staticacountsadAdmin(ImportExportMixin,admin.ModelAdmin):
    list_display = ['accounttype','staticaccount','code']
 
admin.site.register(staticacounts,staticacountsadAdmin)

class staticacountsmappingAdmin(ImportExportMixin,admin.ModelAdmin):
    list_display = ['staticaccount','account','entity']
    list_filter = (
        ('entity', admin.RelatedOnlyFieldListFilter),
    )



admin.site.register(staticacountsmapping,staticacountsmappingAdmin)





