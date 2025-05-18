from django.contrib import admin
from .models import (
    purchasetaxtype, InvoiceType, gstorderservices, gstorderservicesdetails, 
    SalesOderHeader,  salesOrderdetail, saleothercharges, PurchaseReturn, Purchasereturndetails, Purchasereturnothercharges,SalesOder,
    jobworkchalan, jobworkchalanDetails, purchaseorderimport, PurchaseOrderimportdetails, purchaseotherimportcharges,purchaseorder, PurchaseOrderDetails, purchaseothercharges, newpurchaseorder, newPurchaseOrderDetails, salereturn,
    salereturnDetails, salereturnothercharges, journalmain, journaldetails, stockmain, 
    stockdetails, productionmain, productiondetails, journal, Transactions, entry, 
    accountentry, StockTransactions,goodstransaction, tdsreturns, tdstype, tdsmain,
    debitcreditnote, closingstock, supplytype,PurchaseOrderAttachment,salesOrderdetails,defaultvaluesbyentity,Paymentmodes,SalesInvoiceSettings,doctype,ReceiptVoucherInvoiceAllocation,ReceiptVoucher
)
from django.utils.translation import gettext_lazy as _
from import_export.admin import ImportExportMixin
from simple_history.admin import SimpleHistoryAdmin



# Admin for purchasetaxtype
class PurchaseTaxTypeAdmin(admin.ModelAdmin):
    list_display = ('taxtypename', 'taxtypecode', 'entity', 'createdby', 'created_at')
    search_fields = ('taxtypename', 'taxtypecode')
    ordering = ('taxtypename',)

admin.site.register(purchasetaxtype, PurchaseTaxTypeAdmin)


# Admin for InvoiceType
class InvoiceTypeAdmin(admin.ModelAdmin):
    list_display = ('invoicetype', 'invoicetypecode', 'entity', 'createdby', 'created_at')
    search_fields = ('invoicetype', 'invoicetypecode')
    ordering = ('invoicetype',)

admin.site.register(InvoiceType, InvoiceTypeAdmin)


# Admin for gstorderservices
class GstOrderServicesAdmin(admin.ModelAdmin):
    list_display = ('billno', 'orderdate', 'totalgst', 'gtotal', 'entity', 'subentity', 'createdby', 'created_at')
    search_fields = ('billno', 'grno', 'vehicle', 'agent')
    ordering = ('billno',)
    date_hierarchy = 'orderdate'

admin.site.register(gstorderservices, GstOrderServicesAdmin)


# Admin for gstorderservicesdetails
class GstOrderServicesDetailsAdmin(admin.ModelAdmin):
    list_display = ('gstorderservices', 'account', 'multiplier', 'rate', 'amount', 'cgst', 'sgst', 'igst', 'linetotal', 'entity', 'subentity')
    search_fields = ('account__name', 'accountdesc')
    ordering = ('gstorderservices',)

admin.site.register(gstorderservicesdetails, GstOrderServicesDetailsAdmin)


# Admin for SalesOderHeader
class SalesOrderHeaderAdmin(SimpleHistoryAdmin):
    list_display = ('billno', 'sorderdate', 'totalgst', 'gtotal', 'entity', 'subentity', 'createdby',  'created_at')
    search_fields = ('billno', 'grno', 'vehicle', 'remarks', 'terms')
    ordering = ('billno',)
    date_hierarchy = 'sorderdate'

admin.site.register(SalesOderHeader, SalesOrderHeaderAdmin)


# Admin for salesOrderdetails
@admin.register(salesOrderdetails)
class SalesOrderDetailsAdmin(SimpleHistoryAdmin):
    list_display = ('salesorderheader', 'product', 'orderqty', 'pieces', 'rate', 'amount', 'cgst', 'sgst', 'igst', 'linetotal', 'entity', 'subentity')
    search_fields = ('product__name', 'productdesc')
    ordering = ('salesorderheader',)

@admin.register(SalesOder)
class SalesOderAdmin(admin.ModelAdmin):
    list_display = ('billno', 'sorderdate', 'accountid', 'shippedto', 'totalpieces', 'gtotal', 'createdby', 'due_date')
    search_fields = ('billno', 'accountid__name', 'remarks')
   

    def due_date(self, obj):
        return obj.duedate
    due_date.admin_order_field = 'duedate'
    due_date.short_description = _('Due Date')


@admin.register(salesOrderdetail)
class SalesOrderDetailAdmin(admin.ModelAdmin):
    list_display = ('salesorderheader', 'product', 'orderqty', 'pieces', 'rate', 'amount', 'cgst', 'sgst', 'igst', 'cess')
    search_fields = ('salesorderheader__billno', 'product__name', 'productdesc')
   


@admin.register(saleothercharges)
class SaleOtherChargesAdmin(admin.ModelAdmin):
    list_display = ('salesorderdetail', 'account', 'amount')
    search_fields = ('salesorderdetail__salesorderheader__billno', 'account__name')
  

@admin.register(PurchaseReturn)
class PurchaseReturnAdmin(admin.ModelAdmin):
    list_display = ('billno', 'sorderdate', 'accountid', 'shippedto', 'totalpieces', 'gtotal', 'createdby', 'due_date')
    search_fields = ('billno', 'accountid__name', 'remarks')
  

    def due_date(self, obj):
        return obj.duedate
    due_date.admin_order_field = 'duedate'
    due_date.short_description = _('Due Date')


@admin.register(Purchasereturndetails)
class PurchaseReturnDetailsAdmin(admin.ModelAdmin):
    list_display = ('purchasereturn', 'product', 'orderqty', 'pieces', 'rate', 'amount', 'cgst', 'sgst', 'igst', 'cess')
    search_fields = ('purchasereturn__billno', 'product__name', 'productdesc')
   


@admin.register(Purchasereturnothercharges)
class PurchaseReturnOtherChargesAdmin(admin.ModelAdmin):
    list_display = ('purchasereturnorderdetail', 'account', 'amount')
    search_fields = ('purchasereturnorderdetail__purchasereturn__billno', 'account__name')
  



# jobworkchalan Admin
class JobworkChalanAdmin(admin.ModelAdmin):
    list_display = ('voucherno', 'voucherdate', 'account', 'totalpieces', 'gtotal')
    search_fields = ('voucherno', 'account__name')  # Assuming 'name' field in 'account' model
  

class JobworkChalanDetailsAdmin(admin.ModelAdmin):
    list_display = ('jobworkchalan', 'product', 'orderqty', 'pieces', 'linetotal')
    search_fields = ('jobworkchalan__voucherno', 'product__name')  # Assuming 'name' field in 'product' model
   

# purchaseorderimport Admin
class PurchaseOrderImportAdmin(admin.ModelAdmin):
    list_display = ('voucherno', 'voucherdate', 'account', 'totalpieces', 'gtotal')
    search_fields = ('voucherno', 'account__name')
   

class PurchaseOrderImportDetailsAdmin(admin.ModelAdmin):
    list_display = ('purchaseorder', 'product', 'orderqty', 'pieces', 'linetotal')
    search_fields = ('purchaseorder__voucherno', 'product__name')
   

# purchaseotherimportcharges Admin
class PurchaseOtherImportChargesAdmin(admin.ModelAdmin):
    list_display = ('purchaseorderdetail', 'account', 'amount')
    search_fields = ('purchaseorderdetail__purchaseorder__voucherno', 'account__name')
    

# Register your models with the admin site
admin.site.register(jobworkchalan, JobworkChalanAdmin)
admin.site.register(jobworkchalanDetails, JobworkChalanDetailsAdmin)
admin.site.register(purchaseorderimport, PurchaseOrderImportAdmin)
admin.site.register(PurchaseOrderimportdetails, PurchaseOrderImportDetailsAdmin)
admin.site.register(purchaseotherimportcharges, PurchaseOtherImportChargesAdmin)


# Admin for purchaseorder
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ['voucherno', 'account', 'billno', 'terms', 'totalpieces', 'totalquanity', 'gtotal', 'createdby']
    search_fields = ['voucherno', 'billno', 'remarks']
    date_hierarchy = 'voucherdate'

admin.site.register(purchaseorder, PurchaseOrderAdmin)

# Admin for PurchaseOrderDetails
class PurchaseOrderDetailsAdmin(admin.ModelAdmin):
    list_display = ['purchaseorder', 'product', 'orderqty', 'pieces', 'rate', 'amount', 'cgst', 'sgst', 'igst', 'linetotal']
    search_fields = ['productdesc']

admin.site.register(PurchaseOrderDetails, PurchaseOrderDetailsAdmin)

# Admin for purchaseothercharges
class PurchaseOtherChargesAdmin(admin.ModelAdmin):
    list_display = ['purchaseorderdetail', 'account', 'amount']
    search_fields = ['purchaseorderdetail__purchaseorder__voucherno']

admin.site.register(purchaseothercharges, PurchaseOtherChargesAdmin)

# Admin for newpurchaseorder
class NewPurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ['voucherno', 'account', 'billno', 'terms', 'totalpieces', 'totalquanity', 'gtotal', 'createdby']
    search_fields = ['voucherno', 'billno', 'remarks']
    date_hierarchy = 'voucherdate'

admin.site.register(newpurchaseorder, NewPurchaseOrderAdmin)

# Admin for newPurchaseOrderDetails
class NewPurchaseOrderDetailsAdmin(admin.ModelAdmin):
    list_display = ['purchaseorder', 'product', 'orderqty', 'pieces', 'rate', 'amount', 'cgst', 'sgst', 'igst', 'linetotal']
    search_fields = ['productdesc']

admin.site.register(newPurchaseOrderDetails, NewPurchaseOrderDetailsAdmin)

# Admin for salereturn
class SaleReturnAdmin(admin.ModelAdmin):
    list_display = ['voucherno', 'account', 'billno', 'terms', 'totalpieces', 'totalquanity', 'gtotal', 'createdby']
    search_fields = ['voucherno', 'billno', 'remarks']
    date_hierarchy = 'voucherdate'

admin.site.register(salereturn, SaleReturnAdmin)



class salereturnDetailsAdmin(admin.ModelAdmin):
    list_display = ['salereturn', 'product', 'orderqty', 'pieces', 'rate', 'amount', 'othercharges', 'cgst', 'sgst', 'igst', 'cess', 'linetotal', 'subentity', 'entity', 'createdby']
    search_fields = ['salereturn__id', 'product__name']
  

class salereturnotherchargesAdmin(admin.ModelAdmin):
    list_display = ['salesreturnorderdetail', 'account', 'amount']
    search_fields = ['salesreturnorderdetail__id', 'account__name']


class journalmainAdmin(admin.ModelAdmin):
    list_display = ['voucherdate', 'voucherno', 'vouchertype', 'mainaccountid', 'entrydate', 'entity', 'entityfinid', 'createdby']
    search_fields = ['voucherno', 'vouchertype', 'entity__name']
   

class journaldetailsAdmin(admin.ModelAdmin):
    list_display = ['Journalmain', 'account', 'desc', 'drcr', 'debitamount', 'creditamount', 'discount', 'bankcharges', 'tds', 'chqbank', 'entity', 'createdby']
    search_fields = ['Journalmain__voucherno', 'account__name']
  


class stockmainAdmin(admin.ModelAdmin):
    list_display = ['voucherdate', 'voucherno', 'vouchertype', 'entrydate', 'entity', 'entityfinid', 'createdby']
    search_fields = ['voucherno', 'vouchertype', 'entity__name']
   


class stockdetailsAdmin(admin.ModelAdmin):
    list_display = ['stockmain', 'stock', 'desc', 'issuereceived', 'issuedquantity', 'recivedquantity', 'entity', 'createdby']
    search_fields = ['stockmain__voucherno', 'stock__name']
  


class productionmainAdmin(admin.ModelAdmin):
    list_display = ['voucherdate', 'voucherno', 'vouchertype', 'entrydate', 'entity', 'entityfinid', 'createdby']
    search_fields = ['voucherno', 'vouchertype', 'entity__name']
  


class productiondetailsAdmin(admin.ModelAdmin):
    list_display = ['stockmain', 'stock', 'desc', 'issuereceived', 'quantity', 'rate', 'entity', 'createdby']
    search_fields = ['stockmain__voucherno', 'stock__name']
  


class journalAdmin(admin.ModelAdmin):
    list_display = ['voucherdate', 'voucherno', 'vouchertype', 'account', 'desc', 'drcr', 'amount', 'entrydate', 'entity', 'createdby']
    search_fields = ['voucherno', 'vouchertype', 'account__name']
   


class TransactionsAdmin(admin.ModelAdmin):
    list_display = ['account', 'transactiontype', 'transactionid', 'desc', 'drcr', 'amount', 'entrydate', 'entity', 'createdby']
    search_fields = ['transactionid', 'account__name']
  

class entryAdmin(admin.ModelAdmin):
    list_display = ['entrydate1', 'account', 'openingbalance', 'closingbalance', 'entity']
    search_fields = ['account__name', 'entity__name']


class accountentryAdmin(admin.ModelAdmin):
    list_display = ['entrydate2', 'account', 'openingbalance', 'closingbalance', 'entity']
    search_fields = ['account__name', 'entity__name']


class StockTransactionsAdmin(ImportExportMixin,admin.ModelAdmin):
    list_display = ['accounthead', 'account', 'stock', 'transactiontype', 'transactionid', 'voucherno', 'desc', 'stockttype', 'quantity', 'rate', 'drcr', 'debitamount', 'creditamount', 'entry', 'entrydate', 'entrydatetime', 'accounttype', 'pieces', 'weightqty', 'iscashtransaction', 'isbalancesheet', 'istrial', 'entity', 'createdby']
    search_fields = ['transactionid', 'account__name', 'stock__name', 'entity__name']
   


class GoodsTransactionAdmin(admin.ModelAdmin):
    list_display = ('account', 'stock', 'transactiontype', 'transactionid', 'entrydate', 'entity', 'createdby')
    search_fields = ('account__name', 'stock__name', 'transactiontype', 'transactionid', 'desc')
 
    ordering = ('-entrydate',)

class TdsReturnsAdmin(admin.ModelAdmin):
    list_display = ('tdsreturnname', 'tdsreturndesc')
    search_fields = ('tdsreturnname', 'tdsreturndesc')

class TdsTypeAdmin(admin.ModelAdmin):
    list_display = ('tdstypename', 'tdssection', 'tdsreturn')
    search_fields = ('tdstypename', 'tdssection')
   

class TdsMainAdmin(admin.ModelAdmin):
    list_display = ('voucherno', 'voucherdate', 'creditaccountid', 'debitaccountid', 'tdsaccountid', 'amount', 'debitamount', 'tdsvalue', 'grandtotal', 'entityid', 'createdby')
    search_fields = ('voucherno', 'creditaccountid__name', 'debitaccountid__name', 'tdsaccountid__name', 'tdsreturnccountid__tdsreturnname', 'tdsvalue')
   
    ordering = ('-voucherdate',)

class DebitCreditNoteAdmin(admin.ModelAdmin):
    list_display = ('voucherno', 'voucherdate', 'debitaccount', 'creditaccount', 'quantity', 'rate', 'basicvalue', 'cndnamount', 'tdssection', 'entity', 'createdby')
    search_fields = ('voucherno', 'debitaccount__name', 'creditaccount__name', 'product__name', 'tdssection__tdstypename')
   

class ClosingStockAdmin(admin.ModelAdmin):
    list_display = ('stock', 'stockdate', 'closingrate', 'entity', 'createdby')
    search_fields = ('stock__name', 'entity__name')
   

class SupplyTypeAdmin(admin.ModelAdmin):
    list_display = ('supplytypecode', 'supplytypename')
    search_fields = ('supplytypecode', 'supplytypename')


# Register the models and their respective admin classes
admin.site.register(salereturnDetails, salereturnDetailsAdmin)
admin.site.register(salereturnothercharges, salereturnotherchargesAdmin)
admin.site.register(journalmain, journalmainAdmin)
admin.site.register(journaldetails, journaldetailsAdmin)
admin.site.register(stockmain, stockmainAdmin)
admin.site.register(stockdetails, stockdetailsAdmin)
admin.site.register(productionmain, productionmainAdmin)
admin.site.register(productiondetails, productiondetailsAdmin)
admin.site.register(journal, journalAdmin)
admin.site.register(Transactions, TransactionsAdmin)
admin.site.register(entry, entryAdmin)
admin.site.register(accountentry, accountentryAdmin)
admin.site.register(StockTransactions, StockTransactionsAdmin)
# Register the models and their admin classes
admin.site.register(goodstransaction, GoodsTransactionAdmin)
admin.site.register(tdsreturns, TdsReturnsAdmin)
admin.site.register(tdstype, TdsTypeAdmin)
admin.site.register(tdsmain, TdsMainAdmin)
admin.site.register(debitcreditnote, DebitCreditNoteAdmin)
admin.site.register(closingstock, ClosingStockAdmin)
admin.site.register(supplytype, SupplyTypeAdmin)
admin.site.register(PurchaseOrderAttachment)
admin.site.register(defaultvaluesbyentity)
admin.site.register(Paymentmodes)
admin.site.register(SalesInvoiceSettings)
admin.site.register(doctype)
admin.site.register(ReceiptVoucher)
admin.site.register(ReceiptVoucherInvoiceAllocation)









