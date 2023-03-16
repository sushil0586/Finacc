from django.contrib import admin
from invoice.models import SalesOderHeader,salesOrderdetails,purchaseorder,PurchaseOrderDetails,journal,salereturn,salereturnDetails,Transactions,StockTransactions,Purchasereturndetails,PurchaseReturn,journalmain,journaldetails,entry,stockdetails,stockmain,goodstransaction,purchasetaxtype,tdsmain,tdstype,productionmain,productiondetails,tdsreturns,gstorderservices,gstorderservicesdetails,jobworkchalan,jobworkchalanDetails
from import_export.admin import ImportExportMixin

class TransactionsAdmin(admin.ModelAdmin):
    list_display = ['account','transactiontype','desc','drcr','amount','entity','createdby']

class StockTransactionAdmin(admin.ModelAdmin):
    list_display = ['accounthead','account','transactiontype','desc','debitamount','creditamount']


class journalAdmin(admin.ModelAdmin):
    list_display = ['voucherno','vouchertype','account','drcr','amount','entrydate']

class tdsreturnAdmin(ImportExportMixin,admin.ModelAdmin):
    list_display = ['tdsreturnname','tdsreturndesc']

class tdstypeAdmin(ImportExportMixin,admin.ModelAdmin):
    list_display = ['tdstypename','tdssection','tdsreturn']
    

# Register your models here.

admin.site.register(SalesOderHeader)
admin.site.register(salesOrderdetails)
admin.site.register(gstorderservices)
admin.site.register(gstorderservicesdetails)
admin.site.register(jobworkchalan)
admin.site.register(jobworkchalanDetails)
admin.site.register(PurchaseReturn)
admin.site.register(Purchasereturndetails)

admin.site.register(purchaseorder)
admin.site.register(PurchaseOrderDetails)
admin.site.register(salereturn)
admin.site.register(salereturnDetails)
admin.site.register(journal,journalAdmin)
admin.site.register(Transactions,TransactionsAdmin)
admin.site.register(StockTransactions,StockTransactionAdmin)
admin.site.register(journalmain)
admin.site.register(journaldetails)
admin.site.register(entry)
admin.site.register(stockmain)
admin.site.register(stockdetails)
admin.site.register(goodstransaction)
admin.site.register(purchasetaxtype)
admin.site.register(tdsmain)
admin.site.register(tdstype,tdstypeAdmin)
admin.site.register(productionmain)
admin.site.register(productiondetails)
admin.site.register(tdsreturns,tdsreturnAdmin)










