from django.contrib import admin
from import_export.admin import ImportExportMixin

from financial.models import accountHead,account
# Register your models here.


class accountheadAdmin(ImportExportMixin,admin.ModelAdmin):
    list_display = ['name','code','accountheadsr','entity','owner']
    
class accountAdmin(ImportExportMixin,admin.ModelAdmin):
    list_display = ['accountname','accounthead','accountcode','gstno','entity','owner']


admin.site.register(accountHead, accountheadAdmin)


admin.site.register(account,accountAdmin)
# admin.site.register(account_detials1)
# admin.site.register(account_detials2)
