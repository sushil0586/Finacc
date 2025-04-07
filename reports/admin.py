from django.contrib import admin
from import_export.admin import ImportExportMixin
from reports.models import TransactionType



class TransactionTypeAdmin(ImportExportMixin,admin.ModelAdmin):
    list_display = ['transactiontype','transactioncode']
    search_fields = ['transactiontype','transactioncode']

admin.site.register(TransactionType,TransactionTypeAdmin)

# Register your models here.
