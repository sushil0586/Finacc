from django.contrib import admin
from .models import (
    purchasetaxtype, InvoiceType, gstorderservices, gstorderservicesdetails, 
    SalesOderHeader,  salesOrderdetail, saleothercharges, PurchaseReturn, Purchasereturndetails, Purchasereturnothercharges,SalesOder,
    jobworkchalan, jobworkchalanDetails, purchaseorderimport, PurchaseOrderimportdetails, purchaseotherimportcharges,purchaseorder, PurchaseOrderDetails, purchaseothercharges, newpurchaseorder, newPurchaseOrderDetails, salereturn,
    salereturnDetails, salereturnothercharges, journalmain, journaldetails, stockmain, 
    stockdetails, productionmain, productiondetails, journal, Transactions, entry, 
    accountentry, StockTransactions,goodstransaction, tdsreturns, tdstype, tdsmain,
    debitcreditnote, closingstock, supplytype,PurchaseOrderAttachment,salesOrderdetails,defaultvaluesbyentity,Paymentmodes,SalesInvoiceSettings,doctype,ReceiptVoucherInvoiceAllocation,ReceiptVoucher,invoicetypes,EInvoiceDetails,ExpDtls,EwbDtls,AddlDocDtls,RefDtls,PayDtls,JournalLine, InventoryMove, TxnType,SalesQuotationDetail,SalesQuotationHeader
)
from django.utils.translation import gettext_lazy as _
from import_export.admin import ImportExportMixin
from simple_history.admin import SimpleHistoryAdmin
from decimal import Decimal
from django.http import HttpResponse
from django.db.models import Q, Sum
import csv


from financial.models import account
from inventory.models import Product
from financial.models import ShippingDetails
from entity.models import Entity, subentity, entityfinancialyear

# Helper to (re)register with search_fields
def ensure_admin_with_search(model, admin_class, **kwargs):
    try:
        admin.site.unregister(model)
    except admin.sites.NotRegistered:
        pass
    admin.site.register(model, admin_class)

# ---- Account admin ----
# ---- Product admin ----







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


# Admin for InvoiceType
class InvoiceTypesAdmin(admin.ModelAdmin):
    list_display = ('invoicetypename', 'invoicetypecode')
    search_fields = ('invoicetypename', 'invoicetypecode')
    ordering = ('invoicetypename',)

admin.site.register(invoicetypes, InvoiceTypesAdmin)


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
    list_display = ('salesorderheader', 'id', 'product', 'orderqty', 'pieces', 'rate', 'amount', 'cgst', 'sgst', 'igst', 'linetotal', 'entity', 'subentity')
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
    list_display = ['accounthead','id', 'account', 'stock', 'transactiontype', 'transactionid', 'voucherno', 'desc', 'stockttype', 'quantity', 'rate', 'drcr', 'debitamount', 'creditamount', 'entry', 'entrydate', 'entrydatetime', 'accounttype', 'pieces', 'weightqty', 'iscashtransaction', 'isbalancesheet', 'istrial', 'entity', 'createdby']
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
admin.site.register(EInvoiceDetails)
admin.site.register(PayDtls)
admin.site.register(RefDtls)
admin.site.register(AddlDocDtls)
admin.site.register(EwbDtls)
admin.site.register(ExpDtls)

ZERO2 = Decimal("0.00")


# --- Filters ---------------------------------------------------------

class SideFilter(admin.SimpleListFilter):
    title = "side"
    parameter_name = "side"

    def lookups(self, request, model_admin):
        return (("dr", "Debit"), ("cr", "Credit"))

    def queryset(self, request, queryset):
        if self.value() == "dr":
            return queryset.filter(drcr=True)
        if self.value() == "cr":
            return queryset.filter(drcr=False)
        return queryset


# --- Actions ---------------------------------------------------------

def export_as_csv(modeladmin, request, queryset):
    meta = modeladmin.model._meta
    field_names = [f.name for f in meta.fields]
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{meta.model_name}.csv"'
    writer = csv.writer(response)
    writer.writerow(field_names)
    for obj in queryset:
        writer.writerow([getattr(obj, f) for f in field_names])
    return response
export_as_csv.short_description = "Export selected rows to CSV"

def show_totals(modeladmin, request, queryset):
    sums = queryset.aggregate(
        debit=Sum("amount", filter=Q(drcr=True)),
        credit=Sum("amount", filter=Q(drcr=False)),
    )
    modeladmin.message_user(
        request,
        f"Totals — Debit: {sums['debit'] or ZERO2} | Credit: {sums['credit'] or ZERO2}"
    )
show_totals.short_description = "Show DR/CR totals for selection"


@admin.register(JournalLine)
class JournalLineAdmin(admin.ModelAdmin):
    date_hierarchy = "entrydate"
    list_per_page = 50
    preserve_filters = True

    list_display = (
        "id", "entrydate", "voucherno", "transactiontype",
        "entity", "account", "accounthead",
        "side", "debit", "credit",
        "amount", "desc",
        "transactionid", "detailid", "createdby", "entry",
    )
    list_filter = ("transactiontype", "entity", "entrydate", "createdby")
    search_fields = ("id", "voucherno", "desc", "transactionid", "detailid")
    ordering = ("-entrydate", "-id")
    list_select_related = ("entity", "account", "accounthead", "entry", "createdby")

    # FIX: use raw_id_fields instead of autocomplete_fields
    raw_id_fields = ("entity", "account", "accounthead", "entry", "createdby")

    actions = [export_as_csv, show_totals]

    def side(self, obj): return "Debit" if obj.drcr else "Credit"
    def debit(self, obj): return obj.amount if obj.drcr else ZERO2
    def credit(self, obj): return obj.amount if not obj.drcr else ZERO2


@admin.register(InventoryMove)
class InventoryMoveAdmin(admin.ModelAdmin):
    date_hierarchy = "entrydate"
    list_per_page = 50
    preserve_filters = True

    list_display = (
        "id", "entrydate", "voucherno", "transactiontype",
        "entity", "product", "qty", "unit_cost", "ext_cost",
        "move_type", "transactionid", "detailid",
        "location", "uom", "createdby", "entry",
    )
    list_filter = ("transactiontype", "entity", "move_type", "entrydate", "product", "location")
    search_fields = ("id", "voucherno", "transactionid", "detailid")
    ordering = ("-entrydate", "-id")
    list_select_related = ("entity", "product", "entry", "createdby")  # keep only real FKs here

    # ✅ Only include actual FK/M2M fields:
    raw_id_fields = ("entity", "product", "entry", "createdby")




from decimal import Decimal
from django.contrib import admin, messages
from django.db import transaction
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
ZERO4 = Decimal("0.0000")

# from .models import SalesQuotationHeader, SalesQuotationDetail
# from invoice.services import convert_quotation_to_invoice  # import your service

try:
    from simple_history.admin import SimpleHistoryAdmin
    _BaseAdmin = SimpleHistoryAdmin
except Exception:
    _BaseAdmin = admin.ModelAdmin


# ------------
# Inline (Lines)
# ------------
class SalesQuotationLineInline(admin.TabularInline):
    model = SalesQuotationDetail
    extra = 1
    fields = (
        "product", "productdesc", "qty", "pieces",
        "ratebefdiscount", "line_discount", "rate", "amount",
        "cgstpercent", "sgstpercent", "igstpercent",
        "cgst", "sgst", "igst", "linetotal",
        "is_service",
    )
    readonly_fields = ("cgst", "sgst", "igst", "linetotal")
    autocomplete_fields = ("product",)


# --------------
# Header Admin
# --------------
@admin.register(SalesQuotationHeader)
class SalesQuotationHeaderAdmin(_BaseAdmin):
    inlines = [SalesQuotationLineInline]

    list_display = (
        "quote_no", "quote_date", "account", "status", "valid_until",
        "subtotal", "totalgst", "gtotal", "isigst",
        "entity", "version", "_convert_btn",
    )
    list_filter = (
        "status", "isigst", "entity", "subentity", "entityfinid",
        ("quote_date", admin.DateFieldListFilter), ("valid_until", admin.DateFieldListFilter),
    )
    search_fields = (
        "quote_no", "contact_name", "contact_email",
        "account__accountname",
    )
    ordering = ("-quote_date", "-id")
    # autocomplete_fields = ("account", "shippedto", "entity", "subentity", "entityfinid")

    # keep totals read-only; we recompute them from lines
    readonly_fields = ("version", "stbefdiscount", "subtotal", "cgst", "sgst", "igst", "totalgst", "gtotal")

    fieldsets = (
        ("Quotation", {
            "fields": ("quote_no", "quote_date", "version", "status", "valid_until")
        }),
        ("Party & Ship To", {
            "fields": ("account", "contact_name", "contact_email", "shippedto")
        }),
        ("Commercials", {
            "fields": ("price_list", "currency", "remarks", "isigst", "addless", "discount", "cess")
        }),
        ("Roll-up Totals", {
            "fields": ("stbefdiscount", "subtotal", "cgst", "sgst", "igst", "totalgst", "gtotal")
        }),
        ("Scope", {
            "fields": ("entity", "subentity", "entityfinid", "createdby")
        }),
    )

    actions = [
        "action_mark_sent", "action_mark_accepted", "action_mark_rejected", "action_mark_expired",
        "action_convert_to_invoice",
    ]

    readonly_when_final = ("version",)

    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj))
        if obj:
            # Freeze a bunch of fields once the quote is finalized
            if obj.status in (
                SalesQuotationHeader.Status.ACCEPTED,
                SalesQuotationHeader.Status.REJECTED,
                SalesQuotationHeader.Status.EXPIRED,
            ):
                ro += [
                    "quote_no", "quote_date", "account", "shippedto", "valid_until",
                    "price_list", "currency", "remarks", "isigst",
                    # totals are already read-only globally; keep them here for clarity
                    "stbefdiscount", "discount", "subtotal", "addless", "cess", "cgst", "sgst", "igst", "totalgst", "gtotal",
                    "entity", "subentity", "entityfinid", "createdby",
                ]
            ro += list(self.readonly_when_final)
        # dedupe
        return tuple(dict.fromkeys(ro))

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        # optional: bump version when significant header fields change
        if change and form.changed_data:
            significant = {"price_list", "currency", "account", "valid_until", "remarks"}
            if significant.intersection(set(form.changed_data)):
                obj.version = (obj.version or 1) + 1
        super().save_model(request, obj, form, change)

    @transaction.atomic
    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        # Recalculate totals based on current lines
        hdr: SalesQuotationHeader = form.instance
        lines = list(hdr.lines.all())

        def d(v, fallback=ZERO2):
            return v if v is not None else fallback

        stbef = sum(d(ln.ratebefdiscount) * (ln.qty or ZERO4) for ln in lines)

        sum_amount = ZERO2
        sum_cgst = ZERO2
        sum_sgst = ZERO2
        sum_igst = ZERO2

        for ln in lines:
            qty = ln.qty or ZERO4
            amount = d(ln.amount)
            if amount == ZERO2:
                amount = d(ln.rate) * qty - d(ln.line_discount)

            if hdr.isigst:
                igst = amount * (d(ln.igstpercent) / Decimal("100")) if ln.igstpercent is not None else d(ln.igst)
                cgst = ZERO2
                sgst = ZERO2
            else:
                cgst = amount * (d(ln.cgstpercent) / Decimal("100")) if ln.cgstpercent is not None else d(ln.cgst)
                sgst = amount * (d(ln.sgstpercent) / Decimal("100")) if ln.sgstpercent is not None else d(ln.sgst)
                igst = ZERO2

            # normalize line values so inline shows the computed numbers
            ln.amount = amount
            ln.cgst = cgst
            ln.sgst = sgst
            ln.igst = igst
            ln.linetotal = amount + cgst + sgst + igst
            ln.save(update_fields=["amount", "cgst", "sgst", "igst", "linetotal"])

            sum_amount += amount
            sum_cgst += cgst
            sum_sgst += sgst
            sum_igst += igst

        totalgst = sum_cgst + sum_sgst + sum_igst
        hdr.stbefdiscount = stbef
        hdr.subtotal = sum_amount
        hdr.cgst = sum_cgst
        hdr.sgst = sum_sgst
        hdr.igst = sum_igst
        hdr.totalgst = totalgst
        hdr.gtotal = sum_amount - d(hdr.discount) + d(hdr.addless) + totalgst + d(hdr.cess)

        hdr.save(update_fields=["stbefdiscount", "subtotal", "cgst", "sgst", "igst", "totalgst", "gtotal"])

    # ---------
    # Buttons & actions
    # ---------
    @admin.display(description="Convert")
    def _convert_btn(self, obj: "SalesQuotationHeader"):
        if obj.status == SalesQuotationHeader.Status.ACCEPTED:
            url = reverse("admin:salesquotation_convert", args=[obj.id])
            return format_html('<a class="button" href="{}">Convert</a>', url)
        return mark_safe("—")

    @admin.action(description="Mark as Sent")
    def action_mark_sent(self, request, queryset):
        updated = queryset.update(status=SalesQuotationHeader.Status.SENT)
        self.message_user(request, f"{updated} quotation(s) marked as Sent", level=messages.SUCCESS)

    @admin.action(description="Mark as Accepted")
    def action_mark_accepted(self, request, queryset):
        updated = queryset.update(status=SalesQuotationHeader.Status.ACCEPTED)
        self.message_user(request, f"{updated} quotation(s) marked as Accepted", level=messages.SUCCESS)

    @admin.action(description="Mark as Rejected")
    def action_mark_rejected(self, request, queryset):
        updated = queryset.update(status=SalesQuotationHeader.Status.REJECTED)
        self.message_user(request, f"{updated} quotation(s) marked as Rejected", level=messages.WARNING)

    @admin.action(description="Mark as Expired")
    def action_mark_expired(self, request, queryset):
        updated = queryset.update(status=SalesQuotationHeader.Status.EXPIRED)
        self.message_user(request, f"{updated} quotation(s) marked as Expired", level=messages.INFO)
#     @admin.action(description="Convert to Invoice…")
#     def action_convert_to_invoice(self, request, queryset):
#         """Bulk convert accepted quotations. Uses a default pattern; customize as needed."""
#         count = 0
#         for q in queryset.select_related("entity", "entityfinid").prefetch_related("lines"):
#             if q.status != SalesQuotationHeader.Status.ACCEPTED:
#                 continue
#             # You may derive invoice_no/bill_no from sequences; here placeholders:
#             invoice_no = f"INV/{q.entity_id or 'X'}/{q.id}"
#             bill_no = q.id  # replace with your sequence
#             hdr = convert_quotation_to_invoice(q, invoice_no=invoice_no, bill_no=bill_no, tax_is_igst=bool(q.intend_igst))
#             count += 1
#         if count:
#             self.message_user(request, f"Converted {count} quotation(s) to invoice(s)", level=messages.SUCCESS)
#         else:
#             self.message_user(request, "No accepted quotations selected for conversion", level=messages.WARNING)


# # -------------------------
# # Optional: Custom admin view for single-click Convert button
# # -------------------------
# from django.urls import path
# from django.http import HttpResponseRedirect

# class SalesQuotationAdminUrls:
#     def get_urls(self):
#         urls = super().get_urls()
#         custom = [
#             path(
#                 "<int:qid>/convert/",
#                 self.admin_site.admin_view(self.convert_view),
#                 name="salesquotation_convert",
#             ),
#         ]
#         return custom + urls

#     @transaction.atomic
#     def convert_view(self, request, qid: int):
#         obj = SalesQuotationHeader.objects.prefetch_related("lines").get(id=qid)
#         if obj.status != SalesQuotationHeader.Status.ACCEPTED:
#             self.message_user(request, "Quotation must be Accepted before conversion", level=messages.ERROR)
#             return HttpResponseRedirect(request.META.get("HTTP_REFERER", "/admin/"))
#         invoice_no = f"INV/{obj.entity_id or 'X'}/{obj.id}"
#         bill_no = obj.id
#         hdr = convert_quotation_to_invoice(obj, invoice_no=invoice_no, bill_no=bill_no, tax_is_igst=bool(obj.intend_igst))
#         self.message_user(request, f"Invoice #{hdr.invoicenumber} created (bill {hdr.billno})", level=messages.SUCCESS)
#         return HttpResponseRedirect(reverse("admin:%s_%s_change" % (hdr._meta.app_label, hdr._meta.model_name), args=[hdr.id]))

# # Mix the custom URLs into the admin class
# SalesQuotationHeaderAdmin.__bases__ = (SalesQuotationAdminUrls, ) + SalesQuotationHeaderAdmin.__bases__












