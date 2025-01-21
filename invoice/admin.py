from django.contrib import admin
from invoice.models import (
    SalesOderHeader, salesOrderdetails, purchaseorder, PurchaseOrderDetails, journal, salereturn, salereturnDetails,
    Transactions, StockTransactions, Purchasereturndetails, PurchaseReturn, journalmain, journaldetails, entry,
    stockdetails, stockmain, goodstransaction, purchasetaxtype, tdsmain, tdstype, productionmain, productiondetails,
    tdsreturns, gstorderservices, gstorderservicesdetails, jobworkchalan, jobworkchalanDetails, debitcreditnote,
    closingstock, saleothercharges, purchaseothercharges, Purchasereturnothercharges, salereturnothercharges,
    purchaseorderimport, PurchaseOrderimportdetails, purchaseotherimportcharges, newpurchaseorder, 
    newPurchaseOrderDetails, SalesOder, salesOrderdetail, InvoiceType
)
from import_export.admin import ImportExportMixin


class TransactionsAdmin(admin.ModelAdmin):
    list_display = ['account', 'transactiontype', 'desc', 'drcr', 'amount', 'entity', 'createdby']


class StockTransactionAdmin(admin.ModelAdmin):
    list_display = ['accounthead', 'account', 'transactiontype', 'desc', 'debitamount', 'creditamount']


class JournalAdmin(admin.ModelAdmin):
    list_display = ['voucherno', 'vouchertype', 'account', 'drcr', 'amount', 'entrydate']


class TDSReturnAdmin(ImportExportMixin, admin.ModelAdmin):
    list_display = ['tdsreturnname', 'tdsreturndesc']


class TDSTypeAdmin(ImportExportMixin, admin.ModelAdmin):
    list_display = ['tdstypename', 'tdssection', 'tdsreturn']


# Register your models here.
models_to_register = [
    SalesOderHeader, salesOrderdetails, purchaseorder, PurchaseOrderDetails, journalmain, journaldetails, entry,
    stockdetails, stockmain, goodstransaction, purchasetaxtype, tdsmain, productionmain, productiondetails,
    debitcreditnote, closingstock, saleothercharges, purchaseothercharges, Purchasereturnothercharges,
    salereturnothercharges, purchaseorderimport, PurchaseOrderimportdetails, purchaseotherimportcharges,
    newPurchaseOrderDetails, newpurchaseorder, SalesOder, salesOrderdetail, InvoiceType, gstorderservices,
    gstorderservicesdetails, jobworkchalan, jobworkchalanDetails, PurchaseReturn, Purchasereturndetails,
    salereturn, salereturnDetails
]

for model in models_to_register:
    admin.site.register(model)

admin.site.register(journal, JournalAdmin)
admin.site.register(Transactions, TransactionsAdmin)
admin.site.register(StockTransactions, StockTransactionAdmin)
admin.site.register(tdsreturns, TDSReturnAdmin)
admin.site.register(tdstype, TDSTypeAdmin)
