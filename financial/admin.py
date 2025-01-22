from django.contrib import admin
from import_export.admin import ImportExportMixin

from financial.models import accountHead,account,accounttype
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

admin.site.register(accounttype)
