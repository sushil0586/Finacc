#import imp
#from sre_parse import Verbose
from django.db import models
from django.forms import DateField
from helpers.models import TrackingModel
from Authentication.models import User
from financial.models import account,accountHead,ShippingDetails,accounttype
from inventory.models import Product
from entity.models import Entity,entityfinancialyear,subentity
from inventory.models import Product
from django.db.models import Sum 
import datetime
from django.core.exceptions import ValidationError
from django.db.models import Index, Func, DateField, F
from django.db.models.functions import Cast
from geography.models import Country,State,District,City


# Create your models here.


class doctype(TrackingModel):
    docname = models.CharField(max_length= 255,verbose_name= 'Purchase tax type')
    doccode = models.CharField(max_length= 255,verbose_name= 'Purchase tax Code')
    entity = models.ForeignKey(Entity,null=True,on_delete=models.PROTECT)
    createdby = models.ForeignKey(to= User, on_delete=models.PROTECT)


class DocumentNumberSettings(models.Model):
    doctype = models.ForeignKey(doctype,null=True,on_delete=models.PROTECT)
    prefix = models.CharField(max_length=20, default='DOC')
    suffix = models.CharField(max_length=20, blank=True, null=True)
    starting_number = models.IntegerField(default=1)
    current_number = models.IntegerField(default=1)
    number_padding = models.IntegerField(default=0)
    include_year = models.BooleanField(default=False)
    include_month = models.BooleanField(default=False)
    separator = models.CharField(max_length=5, default='-')

    RESET_CHOICES = [
        ('none', 'Do not reset'),
        ('monthly', 'Reset every month'),
        ('yearly', 'Reset every year'),
    ]
    reset_frequency = models.CharField(max_length=10, choices=RESET_CHOICES, default='none')
    last_reset_date = models.DateField(null=True, blank=True)

    custom_format = models.CharField(
        max_length=100,
        blank=True,
        help_text="Use placeholders: {prefix}, {year}, {month}, {number}, {suffix}"
    )

    class Meta:
        abstract = True  # base model, not a table


class SalesInvoiceSettings(DocumentNumberSettings):
    entity = models.ForeignKey(Entity, on_delete=models.CASCADE)
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.PROTECT,verbose_name= 'entity Financial year',null= True)

class PurchaseSettings(DocumentNumberSettings):
    entity = models.ForeignKey(Entity, on_delete=models.CASCADE)
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.PROTECT,verbose_name= 'entity Financial year',null= True)

class ReceiptSettings(DocumentNumberSettings):
    entity = models.ForeignKey(Entity, on_delete=models.CASCADE)
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.PROTECT,verbose_name= 'entity Financial year',null= True)
    


def validate_file_size(value):
    limit = 1000 * 1024  # 100 KB
    if value.size > limit:
        raise ValidationError('File size should not exceed 100 KB.')

class purchasetaxtype(TrackingModel):
    taxtypename = models.CharField(max_length= 255,verbose_name= 'Purchase tax type')
    taxtypecode = models.CharField(max_length= 255,verbose_name= 'Purchase tax Code')
    entity = models.ForeignKey(Entity,null=True,on_delete=models.PROTECT)
    createdby = models.ForeignKey(to= User, on_delete=models.PROTECT)


    def __str__(self):
        return f'{self.taxtypename} '
    

class InvoiceType(TrackingModel):
    invoicetype = models.CharField(max_length=100, verbose_name='Invoice Type')
    invoicetypecode = models.CharField(max_length=20, verbose_name='Invoice Type Code')
    entity = models.ForeignKey(Entity, null=True, on_delete=models.PROTECT)
    createdby = models.ForeignKey(to=User, on_delete=models.PROTECT)

    def __str__(self):
        return f'{self.invoicetype} '
    

class Paymentmodes(TrackingModel):
    paymentmode = models.CharField(max_length=200, verbose_name='Payment Mode')
    paymentmodecode = models.CharField(max_length=20, verbose_name='Payment Mode Code')
    iscash =   models.BooleanField(default=True,verbose_name='IsCash Transaction')
    createdby = models.ForeignKey(to=User, on_delete=models.PROTECT)

    def __str__(self):
        return f'{self.paymentmode}'
    

    


class defaultvaluesbyentity(TrackingModel):
    taxtype = models.ForeignKey(to=purchasetaxtype, on_delete=models.PROTECT)
    invoicetype = models.ForeignKey(to=InvoiceType, on_delete=models.PROTECT)
    subentity = models.ForeignKey(to=subentity, on_delete=models.PROTECT)
    entity = models.ForeignKey(Entity,null=True,on_delete=models.PROTECT)
   # createdby = models.ForeignKey(to= User, on_delete=models.PROTECT)


    def __str__(self):
        return f'{self.purchasetaxtype} - {self.entity}'

        


class gstorderservices(TrackingModel):
    orderdate = models.DateTimeField(verbose_name='Order date',null = True)
    billno = models.IntegerField(verbose_name='Bill No')
    account = models.ForeignKey(to = account, on_delete=models.PROTECT,blank=True)
    taxtype = models.IntegerField(verbose_name='Tax Type')
    billcash = models.IntegerField(verbose_name='Bill/Cash')
    grno = models.CharField(max_length=50,verbose_name='GR No',null=True)
    state       = models.ForeignKey(to=State,on_delete=models.PROTECT,null=True)
    district    = models.ForeignKey(to=District,on_delete=models.PROTECT,null=True)
    city       = models.ForeignKey(to=City,on_delete=models.PROTECT,null=True)
    pincode = models.CharField(max_length=50,verbose_name='pincode',null=True)
    vehicle = models.CharField(max_length=50, null=True,verbose_name='Vehicle')
    orderType = models.CharField(max_length=5,verbose_name='Order Type',null=True)
    totalgst =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'totalgst')
    subtotal =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'Sub Total')
    expensesbeforetax =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'Expenses before tax')
    agent = models.CharField(max_length=50,verbose_name='Agent',null=True)
    cgst =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'C.GST')
    sgst =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'S.GST')
    igstreverse =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'I.GST Reverse')
    cgstreverse =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'C.GST Reverse')
    sgstreverse =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'S.GST Reverse')
    igst =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'I.GST')
    multiplier = models.IntegerField(verbose_name='multiplier',default=0,blank = True)
    expensesaftertax =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'Expenses after tax')
    gtotal =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'Grand Total')
    remarks = models.CharField(max_length=500, null=True,verbose_name='Remarks')
    subentity = models.ForeignKey(subentity,on_delete=models.PROTECT,verbose_name= 'subentity',null= True)
    entity = models.ForeignKey(Entity,on_delete=models.PROTECT,verbose_name= 'entity',null= True)
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.PROTECT,verbose_name= 'entity Financial year',null= True)
    createdby = models.ForeignKey(to= User, on_delete=models.PROTECT,null=True)

    class Meta:
        unique_together = ('billno', 'entity','orderType','entityfinid',)

    def __str__(self):
        return f'{self.billno}'


class gstorderservicesdetails(TrackingModel):
    gstorderservices = models.ForeignKey(to = gstorderservices,related_name='gstorderservicesdetails', on_delete=models.PROTECT,verbose_name= 'Gst services Number')
    account = models.ForeignKey(to = account, on_delete=models.PROTECT,blank=True)
    accountdesc = models.CharField(max_length=500, null=True,verbose_name='account Desc')
    # orderqty =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Order Qty')
    # pieces =  models.IntegerField(verbose_name='pieces')
    multiplier =  models.IntegerField(verbose_name='multiplier')
    rate =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Rate')
    amount =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Amount',null = True)
    cgst =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'CGST',null = True)
    sgst =  models.DecimalField(max_digits=14,null = True, decimal_places=4,verbose_name= 'SGST')
    igst =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'IGST',null = True)
    cgstreverse =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'CGST Reverse',null = True,default = 0)
    sgstreverse =  models.DecimalField(max_digits=14,null = True, decimal_places=4,verbose_name= 'SGST Reverse',default = 0)
    igstreverse =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'IGST Reverse',null = True,default = 0)
    # cess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Cess',default=0)
    linetotal =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Line Total')
    subentity = models.ForeignKey(subentity,on_delete=models.PROTECT,verbose_name= 'subentity',null= True)
    entity = models.ForeignKey(Entity,on_delete=models.PROTECT,verbose_name= 'entity')
    #createdby = models.ForeignKey(to= User, on_delete=models.PROTECT,null=True)


    def __str__(self):
        return f'{self.account}'


class gstorderservicesAttachment(models.Model):
    gst_order = models.ForeignKey('gstorderservices', on_delete=models.PROTECT, related_name='gstosattachments')
    file = models.FileField(upload_to='gst_order_attachments/', validators=[validate_file_size])
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Attachment for  {self.gst_order.gst_order}"


    



class SalesOderHeader(TrackingModel):
    #RevisonNumber =models.IntegerFieldverbose_name=_('Main category'))
    sorderdate = models.DateTimeField(verbose_name='Sales Order date',null = True)
    billno = models.IntegerField(verbose_name='Bill No')
    invoicenumber = models.CharField(max_length=50, null=True,verbose_name='Invoice Number')
    accountid = models.ForeignKey(to = account, on_delete=models.PROTECT,blank=True)
    latepaymentalert = models.BooleanField(verbose_name='Late Payment Alert',default = True,null = True)
    grno = models.CharField(max_length=50,verbose_name='GR No',null=True)
    terms = models.IntegerField(verbose_name='Terms')
    vehicle = models.CharField(max_length=50, null=True,verbose_name='Vehicle')
    taxtype = models.IntegerField(verbose_name='Tax Type')
    billcash = models.IntegerField(verbose_name='Bill/Cash')
    supply = models.IntegerField(verbose_name='Supply')
    state       = models.ForeignKey(to=State,on_delete=models.PROTECT,null=True)
    district    = models.ForeignKey(to=District,on_delete=models.PROTECT,null=True)
    city       = models.ForeignKey(to=City,on_delete=models.PROTECT,null=True)
    pincode = models.CharField(max_length=50,verbose_name='pincode',null=True)
    totalpieces = models.IntegerField(verbose_name='totalpieces',default=0,blank = True)
    totalquanity =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,blank = True,verbose_name= 'totalquanity')
    advance =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,blank = True,verbose_name= 'advance')
    shippedto =  models.ForeignKey(to = ShippingDetails, on_delete=models.PROTECT,null=True,related_name='shippedto')
    ecom =  models.ForeignKey(to = 'financial.account', on_delete=models.PROTECT,null=True,related_name='ecommerce4')
    remarks = models.CharField(max_length=500, null=True,verbose_name= 'Remarks')
    transport =  models.ForeignKey(account, on_delete=models.PROTECT,null=True,related_name='sotransport')
    broker =  models.ForeignKey(account, on_delete=models.PROTECT,null=True,related_name='sobroker')
    taxid = models.IntegerField(verbose_name='Terms',default = 0)
    tds194q =  models.DecimalField(max_digits=14, decimal_places=4,default=0, verbose_name= 'TDS 194 @')
    tds194q1 =  models.DecimalField(max_digits=14, decimal_places=4,default=0, verbose_name= 'TDS 194 @')
    tcs206c1ch1 =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,verbose_name= 'Tcs 206C1cH1')
    tcs206c1ch2 =  models.DecimalField(max_digits=14, decimal_places=4,default=0, verbose_name= 'Tcs 206C1cH2')
    tcs206c1ch3 =  models.DecimalField(max_digits=14, decimal_places=4,default=0, verbose_name= 'Tcs tcs206c1ch3')
    tcs206C1 =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,verbose_name= 'Tcs 206C1')
    tcs206C2 =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,verbose_name= 'Tcs 206C2')
    duedate = models.DateField(verbose_name='Due Date',null = True)
    totalgst =  models.DecimalField(max_digits=14,null = True,decimal_places=4,verbose_name= 'totalgst')
    stbefdiscount = models.DecimalField(max_digits=14,null=True,decimal_places=4,default=0,verbose_name= 'Sub Total before Discount')
    discount = models.DecimalField(max_digits=14,null=True, decimal_places=4,default=0, verbose_name= 'Discount')
    subtotal =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'Sub Total')
    addless =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'Add/Less')
    apptaxrate =  models.DecimalField(max_digits=4, decimal_places=2,default=0,verbose_name= 'app tax rate')
    cgst =  models.DecimalField(max_digits=14,null = True, decimal_places=4,verbose_name= 'C.GST')
    sgst =  models.DecimalField(max_digits=14,null = True, decimal_places=4,verbose_name= 'S.GST')
    igst =  models.DecimalField(max_digits=14,null = True, decimal_places=4,verbose_name= 'I.GST')
    isigst =   models.BooleanField(default=False,verbose_name= 'IsIgst')
    invoicetype = models.ForeignKey(InvoiceType,on_delete=models.PROTECT,verbose_name= 'Invoice Type',null= True)
    reversecharge =   models.BooleanField(default=False,verbose_name= 'Reverse charge')
    cess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Cess',default=0)
    expenses =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'EXpenses')
    gtotal =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'Grand Total')
    roundOff =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'Raw Grand Total')
    subentity = models.ForeignKey(subentity,on_delete=models.PROTECT,verbose_name= 'subentity',null= True)
    entity = models.ForeignKey(Entity,on_delete=models.PROTECT,verbose_name= 'entity',null= True)
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.PROTECT,verbose_name= 'entity Financial year',null= True)
    eway =   models.BooleanField(default=False)
    einvoice =   models.BooleanField(default=False)
    einvoicepluseway =   models.BooleanField(default=False)
    createdby = models.ForeignKey(to= User, on_delete=models.PROTECT,null=True)
   

    class Meta:
        unique_together = ('billno', 'entity','entityfinid',)


    def __str__(self):
        return f'{self.billno} '

class salesOrderdetails(TrackingModel):
    salesorderheader = models.ForeignKey(to = SalesOderHeader,related_name='saleInvoiceDetails', on_delete=models.PROTECT,verbose_name= 'Sale Order Number')
    product = models.ForeignKey(to = Product, on_delete=models.PROTECT,verbose_name= 'Product',null = True)
    productdesc = models.CharField(max_length=500, null=True,verbose_name='product Desc')
    orderqty =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Order Qty')
    pieces =  models.IntegerField(verbose_name='pieces')
    befDiscountProductAmount = models.DecimalField(max_digits=14,null = True, decimal_places=4,verbose_name= 'befDiscountProductAmount')
    ratebefdiscount =  models.DecimalField(max_digits=14,null = True, decimal_places=4,verbose_name= 'ratebefdiscount')
    orderDiscount =  models.DecimalField(max_digits=14,null = True, decimal_places=4,verbose_name= 'Discount')
    orderDiscountValue =  models.DecimalField(max_digits=14,null = True, decimal_places=4,verbose_name= 'Discount')
    rate =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Rate')
    amount =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Amount')
   # account   = models.ForeignKey(to = account, on_delete=models.PROTECT,blank=True,null=True,verbose_name= 'Other account')
    othercharges =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'other charges',default=0,null=True)
    cgst =  models.DecimalField(max_digits=14,null = True, decimal_places=4,verbose_name= 'CGST')
    sgst =  models.DecimalField(max_digits=14,null = True, decimal_places=4,verbose_name= 'SGST')
    igst =  models.DecimalField(max_digits=14,null = True, decimal_places=4,verbose_name= 'IGST')
    isigst =   models.BooleanField(default=False)
    cgstpercent =  models.DecimalField(max_digits=14,null = True, decimal_places=4,verbose_name= 'CGST Percent')
    sgstpercent =  models.DecimalField(max_digits=14,null = True, decimal_places=4,verbose_name= 'SGST Percent')
    igstpercent =  models.DecimalField(max_digits=14,null = True, decimal_places=4,verbose_name= 'IGST Percent')
    # cgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'C.GST Cess',default=0)
    # sgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'S.GST Cess',default=0)
    cess = models.DecimalField(max_digits=14,null = True, decimal_places=4,verbose_name= 'Cess')
    linetotal =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Line Total')
    isService = models.CharField(max_length=10,default = 'N',verbose_name='is Service')
    subentity = models.ForeignKey(subentity,on_delete=models.PROTECT,verbose_name= 'subentity',null= True)
    entity = models.ForeignKey(Entity,on_delete=models.PROTECT,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete=models.PROTECT,null=True)


    def __str__(self):
        return f'{self.product} '
    

class SalesOder(TrackingModel):
    #RevisonNumber =models.IntegerFieldverbose_name=_('Main category'))
    sorderdate = models.DateTimeField(verbose_name='Sales Order date',null = True)
    billno = models.IntegerField(verbose_name='Bill No')
    accountid = models.ForeignKey(to = account, on_delete=models.PROTECT,blank=True)
    latepaymentalert = models.BooleanField(verbose_name='Late Payment Alert',default = True,null = True)
    grno = models.CharField(max_length=50,verbose_name='GR No',null=True)
    terms = models.IntegerField(verbose_name='Terms')
    vehicle = models.CharField(max_length=50, null=True,verbose_name='Vehicle')
    taxtype = models.IntegerField(verbose_name='Tax Type')
    billcash = models.IntegerField(verbose_name='Bill/Cash')
    supply = models.IntegerField(verbose_name='Supply')
    state       = models.ForeignKey(to=State,on_delete=models.PROTECT,null=True)
    district    = models.ForeignKey(to=District,on_delete=models.PROTECT,null=True)
    city       = models.ForeignKey(to=City,on_delete=models.PROTECT,null=True)
    pincode = models.CharField(max_length=50,verbose_name='pincode',null=True)
    totalpieces = models.IntegerField(verbose_name='totalpieces',default=0,blank = True)
    totalquanity =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,blank = True,verbose_name= 'totalquanity')
    advance =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,blank = True,verbose_name= 'advance')
    shippedto =  models.ForeignKey(to = ShippingDetails, on_delete=models.PROTECT,null=True,related_name='soshippedto')
    remarks = models.CharField(max_length=500, null=True,verbose_name= 'Remarks')
    transport =  models.ForeignKey(account, on_delete=models.PROTECT,null=True,related_name='stransport')
    broker =  models.ForeignKey(account, on_delete=models.PROTECT,null=True,related_name='sbroker')
    taxid = models.IntegerField(verbose_name='Terms',default = 0)
    tds194q =  models.DecimalField(max_digits=14, decimal_places=4,default=0, verbose_name= 'TDS 194 @')
    tds194q1 =  models.DecimalField(max_digits=14, decimal_places=4,default=0, verbose_name= 'TDS 194 @')
    tcs206c1ch1 =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,verbose_name= 'Tcs 206C1cH1')
    tcs206c1ch2 =  models.DecimalField(max_digits=14, decimal_places=4,default=0, verbose_name= 'Tcs 206C1cH2')
    tcs206c1ch3 =  models.DecimalField(max_digits=14, decimal_places=4,default=0, verbose_name= 'Tcs tcs206c1ch3')
    tcs206C1 =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,verbose_name= 'Tcs 206C1')
    tcs206C2 =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,verbose_name= 'Tcs 206C2')
    duedate = models.DateField(verbose_name='Due Date',null = True)
    totalgst =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'totalgst')
    subtotal =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'Sub Total')
    addless =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'Add/Less')
    cgst =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'C.GST')
    sgst =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'S.GST')
    igst =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'I.GST')
    # cgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'C.GST Cess',default=0)
    # sgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'S.GST Cess',default=0)
    cess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Cess',default=0)
    expenses =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'EXpenses')
    gtotal =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'Grand Total')
    subentity = models.ForeignKey(subentity,on_delete=models.PROTECT,verbose_name= 'subentity',null= True)
    entity = models.ForeignKey(Entity,on_delete=models.PROTECT,verbose_name= 'entity',null= True)
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.PROTECT,verbose_name= 'entity Financial year',null= True)
    createdby = models.ForeignKey(to= User, on_delete=models.PROTECT,null=True)

    class Meta:
        unique_together = ('billno', 'entity','entityfinid',)


    def __str__(self):
        return f'{self.billno} '

class salesOrderdetail(TrackingModel):
    salesorderheader = models.ForeignKey(to = SalesOder,related_name='salesOrderDetail', on_delete=models.PROTECT,verbose_name= 'Sale Order Number')
    product = models.ForeignKey(to = Product, on_delete=models.PROTECT,verbose_name= 'Product',null = True)
    productdesc = models.CharField(max_length=500, null=True,verbose_name='product Desc')
    orderqty =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Order Qty')
    pieces =  models.IntegerField(verbose_name='pieces')
    rate =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Rate')
    amount =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Amount')
   # account   = models.ForeignKey(to = account, on_delete=models.PROTECT,blank=True,null=True,verbose_name= 'Other account')
    othercharges =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'other charges',default=0,null=True)
    cgst =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'CGST')
    sgst =  models.DecimalField(max_digits=14,null = True, decimal_places=4,verbose_name= 'SGST')
    igst =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'IGST')
    # cgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'C.GST Cess',default=0)
    # sgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'S.GST Cess',default=0)
    cess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Cess',default=0)
    linetotal =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Line Total')
    subentity = models.ForeignKey(subentity,on_delete=models.PROTECT,verbose_name= 'subentity',null= True)
    entity = models.ForeignKey(Entity,on_delete=models.PROTECT,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete=models.PROTECT,null=True)


    def __str__(self):
        return f'{self.product} '
    
class saleothercharges(TrackingModel):
    salesorderdetail = models.ForeignKey(to = salesOrderdetails,related_name='otherchargesdetail', on_delete=models.PROTECT,verbose_name= 'Sale Order Number',null=True)
    account = models.ForeignKey(to = account, on_delete=models.PROTECT,null = True,)
    amount =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'amount')


    def __str__(self):
        return f'{self.salesorderdetail}'
    







    




class PurchaseReturn(TrackingModel):
    #RevisonNumber =models.IntegerFieldverbose_name=_('Main category'))
    sorderdate = models.DateTimeField(verbose_name='Sales Order date',null = True)
    billno = models.IntegerField(verbose_name='Bill No')
    accountid = models.ForeignKey(to = account, on_delete=models.PROTECT,blank=True)
    latepaymentalert = models.BooleanField(verbose_name='Late Payment Alert',default = True,null = True)
    grno = models.CharField(max_length=50,verbose_name='GR No',null=True)
    terms = models.IntegerField(verbose_name='Terms')
    vehicle = models.CharField(max_length=50, null=True,verbose_name='Vehicle')
    taxtype = models.IntegerField(verbose_name='Tax Type')
    billcash = models.IntegerField(verbose_name='Bill/Cash')
    supply = models.IntegerField(verbose_name='Supply')
    state       = models.ForeignKey(to=State,on_delete=models.PROTECT,null=True)
    district    = models.ForeignKey(to=District,on_delete=models.PROTECT,null=True)
    city       = models.ForeignKey(to=City,on_delete=models.PROTECT,null=True)
    pincode = models.CharField(max_length=50,verbose_name='pincode',null=True)
    totalpieces = models.IntegerField(verbose_name='totalpieces',default=0,blank = True)
    totalquanity =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,blank = True,verbose_name= 'totalquanity')
    advance =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,blank = True,verbose_name= 'advance')
    shippedto =  models.ForeignKey(to = ShippingDetails, on_delete=models.PROTECT,null=True,related_name='shippedto1')
    remarks = models.CharField(max_length=500, null=True,verbose_name= 'Remarks')
    transport =  models.ForeignKey(to = account, on_delete=models.PROTECT,null=True,related_name='transport1')
    broker =  models.ForeignKey(to = account, on_delete=models.PROTECT,null=True,related_name='broker1')
    taxid = models.IntegerField(verbose_name='Terms',default = 0)
    tds194q =  models.DecimalField(max_digits=14, decimal_places=4,default=0, verbose_name= 'TDS 194 @')
    tds194q1 =  models.DecimalField(max_digits=14, decimal_places=4,default=0, verbose_name= 'TDS 194 @')
    tcs206c1ch1 =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,verbose_name= 'Tcs 206C1cH1')
    tcs206c1ch2 =  models.DecimalField(max_digits=14, decimal_places=4,default=0, verbose_name= 'Tcs 206C1cH2')
    tcs206c1ch3 =  models.DecimalField(max_digits=14, decimal_places=4,default=0, verbose_name= 'Tcs tcs206c1ch3')
    tcs206C1 =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,verbose_name= 'Tcs 206C1')
    tcs206C2 =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,verbose_name= 'Tcs 206C2')
    duedate = models.DateField(verbose_name='Due Date',auto_now_add=True)
    totalgst =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'totalgst')
    subtotal =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'Sub Total')
    addless =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'Add/Less')
    cgst =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'C.GST')
    sgst =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'S.GST')
    igst =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'I.GST')
    apptaxrate =  models.DecimalField(max_digits=4, decimal_places=2,default=0,verbose_name= 'app tax rate')
    invoicetype = models.ForeignKey(InvoiceType,on_delete=models.PROTECT,verbose_name= 'Invoice Type',null= True)
    reversecharge =   models.BooleanField(default=False,verbose_name= 'Reverse charge')
    ecom =  models.ForeignKey(to = 'financial.account', on_delete=models.PROTECT,null=True,related_name='ecommerce2')
    # cgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'C.GST Cess',default=0)
    # sgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'S.GST Cess',default=0)
    cess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Cess',default=0)
    expenses =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'EXpenses')
    gtotal =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'Grand Total')
    subentity = models.ForeignKey(subentity,on_delete=models.PROTECT,verbose_name= 'subentity',null= True)
    entity = models.ForeignKey(Entity,on_delete=models.PROTECT,verbose_name= 'entity',null= True)
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.PROTECT,verbose_name= 'entity Financial year',null= True)
    createdby = models.ForeignKey(to= User, on_delete=models.PROTECT,null=True)

    # class Meta:
    #     #unique_together = ('billno', 'entity',)


    def __str__(self):
        return f'{self.billno} '

class Purchasereturndetails(TrackingModel):
    purchasereturn = models.ForeignKey(to = PurchaseReturn,related_name='purchasereturndetails', on_delete=models.PROTECT,verbose_name= 'Sale Order Number')
    product = models.ForeignKey(to = Product, on_delete=models.PROTECT,verbose_name= 'Product',null = True)
    productdesc = models.CharField(max_length=500, null=True,verbose_name='product Desc')
    orderqty =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Order Qty')
    pieces =  models.IntegerField(verbose_name='pieces')
    rate =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Rate')
    amount =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Amount')
    #account   = models.ForeignKey(to = account, on_delete=models.PROTECT,blank=True,null=True,verbose_name= 'Other account')
    othercharges =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'other charges',default=0,null=True)
    cgst =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'CGST')
    sgst =  models.DecimalField(max_digits=14,null = True,decimal_places=4,verbose_name= 'SGST')
    igst =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'IGST')
    isigst =   models.BooleanField(default=True)
    cgstpercent = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'C.GST Percent',default=0)
    sgstpercent = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'S.GST Percent',default=0)
    igstpercent = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'I.GST Percent',default=0)
    # cgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'C.GST Cess',default=0)
    # sgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'S.GST Cess',default=0)
    cess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Cess',default=0)
    linetotal =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Line Total')
    subentity = models.ForeignKey(subentity,on_delete=models.PROTECT,verbose_name= 'subentity',null= True)
    entity = models.ForeignKey(Entity,on_delete=models.PROTECT,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete=models.PROTECT,null=True)


    def __str__(self):
        return f'{self.product} '
    

class Purchasereturnothercharges(TrackingModel):
    purchasereturnorderdetail = models.ForeignKey(to = Purchasereturndetails,related_name='otherchargesdetail', on_delete=models.PROTECT,verbose_name= 'Sale Order Number',null=True)
    account = models.ForeignKey(to = account, on_delete=models.PROTECT,null = True,)
    amount =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'amount')


    def __str__(self):
        return f'{self.purchasereturnorderdetail}'
    

class jobworkchalan(TrackingModel):
    voucherdate = models.DateField(verbose_name='Vocucher Date',auto_now_add=True)
    voucherno = models.IntegerField(verbose_name='Voucher No')
    account = models.ForeignKey(to = account, on_delete=models.PROTECT,null=True,blank=True)
    billno = models.IntegerField(verbose_name='Bill No')
    billdate = models.DateTimeField(verbose_name='Bill Date',null = True)
    terms = models.IntegerField(verbose_name='Terms')
    taxtype = models.IntegerField(verbose_name='TaxType')
    billcash = models.IntegerField(verbose_name='Bill/Cash')
    state       = models.ForeignKey(to=State,on_delete=models.PROTECT,null=True)
    district    = models.ForeignKey(to=District,on_delete=models.PROTECT,null=True)
    city       = models.ForeignKey(to=City,on_delete=models.PROTECT,null=True)
    pincode = models.CharField(max_length=50,verbose_name='pincode',null=True)
    totalpieces = models.IntegerField(verbose_name='totalpieces',default=0,blank = True)
    totalquanity =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,blank = True,verbose_name= 'totalquanity')
    advance =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,blank = True,verbose_name= 'advance')
    remarks = models.CharField(max_length=500, null=True,verbose_name= 'Remarks')
    transport =  models.ForeignKey(to = 'financial.account', on_delete=models.PROTECT,null=True,related_name='jwtransport')
    broker =  models.ForeignKey(to = 'financial.account', on_delete=models.PROTECT,null=True,related_name='jwbroker')
    taxid = models.IntegerField(verbose_name='Terms',default = 0)
    tds194q =  models.DecimalField(max_digits=14, decimal_places=4,default=0, verbose_name= 'TDS 194 @')
    tds194q1 =  models.DecimalField(max_digits=14, decimal_places=4,default=0, verbose_name= 'TDS 194 @')
    tcs206c1ch1 =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,verbose_name= 'Tcs 206C1cH1')
    tcs206c1ch2 =  models.DecimalField(max_digits=14, decimal_places=4,default=0, verbose_name= 'Tcs 206C1cH2')
    tcs206c1ch3 =  models.DecimalField(max_digits=14, decimal_places=4,default=0, verbose_name= 'Tcs tcs206c1ch3')
    tcs206C1 =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,verbose_name= 'Tcs 206C1')
    tcs206C2 =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,verbose_name= 'Tcs 206C2')
    duedate = models.DateTimeField(verbose_name='Due Date',null = True)
    inputdate = models.DateTimeField(verbose_name='Input Date',null = True)
    vehicle = models.CharField(max_length=50, null=True,verbose_name='Vehicle')
    ordertype = models.CharField(max_length=5, null=True,verbose_name='Order Type')
    grno = models.CharField(max_length=50,null=True,verbose_name='GR No')
    gstr2astatus = models.BooleanField(verbose_name='GstR 2A Status',default= 1)
    showledgeraccount = models.BooleanField(verbose_name='Show Ledger Account',default= 1)
    subtotal = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Sub Total')
    cgst = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'C.GST',default=0)
    sgst = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'S.GST',default=0)
    igst = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'I.GST',default=0)
    addless =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'Add/Less')
    # cgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'C.GST Cess',default=0)
    # sgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'S.GST Cess',default=0)
    cess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Cess',default=0)
    expenses = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Expenses',default=0)
    gtotal = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'G Total')
    subentity = models.ForeignKey(subentity,on_delete=models.PROTECT,verbose_name= 'subentity',null= True)
    entity = models.ForeignKey(Entity,on_delete=models.PROTECT,verbose_name= 'entity')
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.PROTECT,verbose_name= 'entity Financial year',null= True)
    createdby = models.ForeignKey(to= User, on_delete=models.PROTECT,null=True)


    class Meta:
        unique_together = ('voucherno', 'entity',)
        unique_together = ('billno', 'account','entity','ordertype','entityfinid',)
        

    def __str__(self):
        return f'{self.voucherno} '

class jobworkchalanDetails(models.Model):
    jobworkchalan = models.ForeignKey(to = jobworkchalan,related_name='jobworkchalanDetails', on_delete=models.PROTECT,verbose_name= 'Purchase Order Number')
    product = models.ForeignKey(to = Product, on_delete=models.PROTECT,verbose_name= 'Product',null = True)
    productdesc = models.CharField(max_length=500, null=True,verbose_name='Product Desc')
    orderqty =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Order Qty')
    pieces =  models.IntegerField(verbose_name='pieces')
    rate =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Rate')
    amount =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Amount')
    cgst =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'CGST')
    sgst =  models.DecimalField(max_digits=14,null = True,decimal_places=4,verbose_name= 'SGST')
    igst =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'IGST')
    # cgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'C.GST Cess',default=0)
    # sgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'S.GST Cess',default=0)
    cess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Cess',default=0)
    linetotal =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Line Total')
    subentity = models.ForeignKey(subentity,on_delete=models.PROTECT,verbose_name= 'subentity',null= True)
    
    entity = models.ForeignKey(Entity,on_delete=models.PROTECT,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete=models.PROTECT,null=True)


class purchaseorderimport(TrackingModel):
    voucherdate = models.DateField(verbose_name='Vocucher Date',auto_now_add=True)
    voucherno = models.IntegerField(verbose_name='Voucher No')
    account = models.ForeignKey(to = account, on_delete=models.PROTECT,null=True,blank=True)
    billno = models.IntegerField(verbose_name='Bill No')
    billdate = models.DateTimeField(verbose_name='Bill Date',null = True)
    terms = models.IntegerField(verbose_name='Terms')
    taxtype = models.IntegerField(verbose_name='TaxType')
    billcash = models.IntegerField(verbose_name='Bill/Cash')
    state       = models.ForeignKey(to=State,on_delete=models.PROTECT,null=True)
    district    = models.ForeignKey(to=District,on_delete=models.PROTECT,null=True)
    city       = models.ForeignKey(to=City,on_delete=models.PROTECT,null=True)
    pincode = models.CharField(max_length=50,verbose_name='pincode',null=True)
    totalpieces = models.IntegerField(verbose_name='totalpieces',default=0,blank = True)
    totalquanity =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,blank = True,verbose_name= 'totalquanity')
    advance =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,blank = True,verbose_name= 'advance')
    remarks = models.CharField(max_length=500, null=True,verbose_name= 'Remarks')
    transport =  models.ForeignKey(to = 'financial.account', on_delete=models.PROTECT,null=True,related_name='sitransport')
    broker =  models.ForeignKey(to = 'financial.account', on_delete=models.PROTECT,null=True,related_name='sibroker')
    taxid = models.IntegerField(verbose_name='Terms',default = 0)
    tds194q =  models.DecimalField(max_digits=14, decimal_places=4,default=0, verbose_name= 'TDS 194 @')
    tds194q1 =  models.DecimalField(max_digits=14, decimal_places=4,default=0, verbose_name= 'TDS 194 @')
    tcs206c1ch1 =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,verbose_name= 'Tcs 206C1cH1')
    tcs206c1ch2 =  models.DecimalField(max_digits=14, decimal_places=4,default=0, verbose_name= 'Tcs 206C1cH2')
    tcs206c1ch3 =  models.DecimalField(max_digits=14, decimal_places=4,default=0, verbose_name= 'Tcs tcs206c1ch3')
    tcs206C1 =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,verbose_name= 'Tcs 206C1')
    tcs206C2 =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,verbose_name= 'Tcs 206C2')
    duedate = models.DateTimeField(verbose_name='Due Date',null = True)
    inputdate = models.DateTimeField(verbose_name='Input Date',null = True)
    vehicle = models.CharField(max_length=50, null=True,verbose_name='Vehicle')
    grno = models.CharField(max_length=50,null=True,verbose_name='GR No')
    gstr2astatus = models.BooleanField(verbose_name='GstR 2A Status',default= 1)
    showledgeraccount = models.BooleanField(verbose_name='Show Ledger Account',default= 1)
    subtotal = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Sub Total')
    igst = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'I.GST',default=0)
    addless =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'Add/Less')
    cess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Cess',default=0)
    expenses = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Expenses',default=0)
    gtotal = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'G Total')
    importgtotal = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Import G Total')
    subentity = models.ForeignKey(subentity,on_delete=models.PROTECT,verbose_name= 'subentity',null= True)
    entity = models.ForeignKey(Entity,on_delete=models.PROTECT,verbose_name= 'entity')
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.PROTECT,verbose_name= 'entity Financial year',null= True)
    createdby = models.ForeignKey(to= User, on_delete=models.PROTECT,null=True)


    class Meta:
        unique_together = ('voucherno', 'entity',)
        unique_together = ('billno', 'account','entity','entityfinid',)
        

    def __str__(self):
        return f'{self.voucherno}'
    


class PurchaseOrderimportdetails(models.Model):
    purchaseorder = models.ForeignKey(to = purchaseorderimport,related_name='PurchaseOrderimportdetails', on_delete=models.PROTECT,verbose_name= 'Purchase Order Number')
    product = models.ForeignKey(to = Product, on_delete=models.PROTECT,verbose_name= 'Product',null = True)
    productdesc = models.CharField(max_length=500, null=True,verbose_name='Product Desc')
    orderqty =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Order Qty')
    pieces =  models.IntegerField(verbose_name='pieces')
    rate =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Rate')
    actualamount =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Actual amount')
    importamount =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Import Amount')
    igst =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'IGST')
  #  othercharges =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'other charges',default=0,null=True)
    cess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Cess',default=0)
    linetotal =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Line Total')
    subentity = models.ForeignKey(subentity,on_delete=models.PROTECT,verbose_name= 'subentity',null= True)
    entity = models.ForeignKey(Entity,on_delete=models.PROTECT,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete=models.PROTECT,null=True)



class purchaseotherimportcharges(TrackingModel):
    purchaseorderdetail = models.ForeignKey(to = PurchaseOrderimportdetails,related_name='otherchargesdetail', on_delete=models.PROTECT,verbose_name= 'Purchase Order detail',null=True)
    account = models.ForeignKey(to = account, on_delete=models.PROTECT,null = True,)
    amount =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'amount')


    def __str__(self):
        return f'{self.purchaseorderdetail}'
    

class purchaseotherimporAttachment(models.Model):
    purchase_order_import = models.ForeignKey('purchaseorderimport', on_delete=models.PROTECT, related_name='piattachments')
    file = models.FileField(upload_to='purchase_order_import_attachments/', validators=[validate_file_size])
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Attachment for PO {self.purchase_order_import.voucherno}"
    





    



class purchaseorder(TrackingModel):
    voucherdate = models.DateField(verbose_name='Vocucher Date',auto_now_add=True)
    voucherno = models.IntegerField(verbose_name='Voucher No')
    account = models.ForeignKey(to = account, on_delete=models.PROTECT,null=True,blank=True)
    billno = models.IntegerField(verbose_name='Bill No')
    billdate = models.DateTimeField(verbose_name='Bill Date',null = True)
    terms = models.IntegerField(verbose_name='Terms')
    taxtype = models.IntegerField(verbose_name='TaxType')
    billcash = models.IntegerField(verbose_name='Bill/Cash')
    totalpieces = models.IntegerField(verbose_name='totalpieces',default=0,blank = True)
    state       = models.ForeignKey(to=State,on_delete=models.PROTECT,null=True)
    district    = models.ForeignKey(to=District,on_delete=models.PROTECT,null=True)
    city       = models.ForeignKey(to=City,on_delete=models.PROTECT,null=True)
    pincode = models.CharField(max_length=50,verbose_name='pincode',null=True)
    totalquanity =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,blank = True,verbose_name= 'totalquanity')
    advance =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,blank = True,verbose_name= 'advance')
    remarks = models.CharField(max_length=500, null=True,verbose_name= 'Remarks')
    transport =  models.ForeignKey(to = 'financial.account', on_delete=models.PROTECT,null=True,related_name='potransport')
    broker =  models.ForeignKey(to = 'financial.account', on_delete=models.PROTECT,null=True,related_name='pobroker')
    taxid = models.IntegerField(verbose_name='Terms',default = 0)
    tds194q =  models.DecimalField(max_digits=14, decimal_places=4,default=0, verbose_name= 'TDS 194 @')
    tds194q1 =  models.DecimalField(max_digits=14, decimal_places=4,default=0, verbose_name= 'TDS 194 @')
    tcs206c1ch1 =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,verbose_name= 'Tcs 206C1cH1')
    tcs206c1ch2 =  models.DecimalField(max_digits=14, decimal_places=4,default=0, verbose_name= 'Tcs 206C1cH2')
    tcs206c1ch3 =  models.DecimalField(max_digits=14, decimal_places=4,default=0, verbose_name= 'Tcs tcs206c1ch3')
    tcs206C1 =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,verbose_name= 'Tcs 206C1')
    tcs206C2 =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,verbose_name= 'Tcs 206C2')
    duedate = models.DateTimeField(verbose_name='Due Date',null = True)
    inputdate = models.DateTimeField(verbose_name='Input Date',null = True)
    vehicle = models.CharField(max_length=50, null=True,verbose_name='Vehicle')
    invoicetype = models.ForeignKey(InvoiceType,on_delete=models.PROTECT,verbose_name= 'Invoice Type',null= True)
    reversecharge =   models.BooleanField(default=False,verbose_name= 'Reverse charge')
    grno = models.CharField(max_length=50,null=True,verbose_name='GR No')
    gstr2astatus = models.BooleanField(verbose_name='GstR 2A Status',default= 1)
    showledgeraccount = models.BooleanField(verbose_name='Show Ledger Account',default= 1)
    subtotal = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Sub Total')
    cgst = models.DecimalField(max_digits=14,null=True, decimal_places=4,verbose_name= 'C.GST',default=0)
    sgst = models.DecimalField(max_digits=14,null=True, decimal_places=4,verbose_name= 'S.GST',default=0)
    igst = models.DecimalField(max_digits=14,null=True, decimal_places=4,verbose_name= 'I.GST',default=0)
    addless =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'Add/Less')
    ecom = models.ForeignKey(to='financial.account',on_delete=models.PROTECT,null=True,related_name='ecommerce1')
    apptaxrate =  models.DecimalField(max_digits=4, decimal_places=2,default=0,verbose_name= 'app tax rate')
    # cgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'C.GST Cess',default=0)
    # sgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'S.GST Cess',default=0)
    cess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Cess',default=0)
    expenses = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Expenses',default=0)
    gtotal = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'G Total')
    roundOff = models.DecimalField(max_digits=14, decimal_places=4,default=0 , verbose_name= 'G Total')
    finalAmount = models.DecimalField(max_digits=14, decimal_places=4,default=0 , verbose_name= 'G Total')
    subentity = models.ForeignKey(subentity,on_delete=models.PROTECT,verbose_name= 'subentity',null= True)
    entity = models.ForeignKey(Entity,on_delete=models.PROTECT,verbose_name= 'entity')
    
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.PROTECT,verbose_name= 'entity Financial year',null= True)
    createdby = models.ForeignKey(to= User, on_delete=models.PROTECT,null=True)


    class Meta:
        unique_together = ('voucherno', 'entity','entityfinid',)
        unique_together = ('billno', 'account','entity','entityfinid',)
        

    def __str__(self):
        return f'{self.voucherno} '

class PurchaseOrderDetails(models.Model):
    purchaseorder = models.ForeignKey(to = purchaseorder,related_name='purchaseInvoiceDetails', on_delete=models.PROTECT,verbose_name= 'Purchase Order Number')
    product = models.ForeignKey(to = Product, on_delete=models.PROTECT,verbose_name= 'Product',null = True)
    productdesc = models.CharField(max_length=500, null=True,verbose_name='Product Desc')
    orderqty =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Order Qty')
    pieces =  models.IntegerField(verbose_name='pieces')
    rate =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Rate')
    amount =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Amount')
    cgst =  models.DecimalField(max_digits=14,null=True, decimal_places=4,verbose_name= 'CGST')
    sgst =  models.DecimalField(max_digits=14,null = True,decimal_places=4,verbose_name= 'SGST')
    igst =  models.DecimalField(max_digits=14,null=True, decimal_places=4,verbose_name= 'IGST')
    isigst =   models.BooleanField(default=False)
    cgstpercent =  models.DecimalField(max_digits=14,null=True, decimal_places=4,verbose_name= 'CGST percent')
    sgstpercent =  models.DecimalField(max_digits=14,null = True,decimal_places=4,verbose_name= 'SGST percent')
    igstpercent =  models.DecimalField(max_digits=14,null=True, decimal_places=4,verbose_name= 'IGST percent')
    othercharges =  models.DecimalField(max_digits=14,null=True, decimal_places=4,verbose_name= 'other charges',default=0)
    cess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Cess',default=0)
    linetotal =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Line Total')
    subentity = models.ForeignKey(subentity,on_delete=models.PROTECT,verbose_name= 'subentity',null= True)
    entity = models.ForeignKey(Entity,on_delete=models.PROTECT,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete=models.PROTECT,null=True)



class purchaseothercharges(TrackingModel):
    purchaseorderdetail = models.ForeignKey(to = PurchaseOrderDetails,related_name='otherchargesdetail', on_delete=models.PROTECT,verbose_name= 'Purchase Order detail',null=True)
    account = models.ForeignKey(to = account, on_delete=models.PROTECT,null = True,)
    amount =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'amount')


    def __str__(self):
        return f'{self.purchaseorderdetail}'
    


class PurchaseOrderAttachment(models.Model):
    purchase_order = models.ForeignKey('purchaseorder', on_delete=models.PROTECT, related_name='attachments')
    file = models.FileField(upload_to='purchase_order_attachments/', validators=[validate_file_size])
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Attachment for PO {self.purchase_order.voucherno}"


class newpurchaseorder(TrackingModel):
    voucherdate = models.DateField(verbose_name='Vocucher Date',auto_now_add=True)
    voucherno = models.IntegerField(verbose_name='Voucher No')
    account = models.ForeignKey(to = account, on_delete=models.PROTECT,null=True,blank=True)
    billno = models.IntegerField(verbose_name='Bill No')
    billdate = models.DateTimeField(verbose_name='Bill Date',null = True)
    terms = models.IntegerField(verbose_name='Terms')
    taxtype = models.IntegerField(verbose_name='TaxType')
    billcash = models.IntegerField(verbose_name='Bill/Cash')
    state       = models.ForeignKey(to=State,on_delete=models.PROTECT,null=True)
    district    = models.ForeignKey(to=District,on_delete=models.PROTECT,null=True)
    city       = models.ForeignKey(to=City,on_delete=models.PROTECT,null=True)
    pincode = models.CharField(max_length=50,verbose_name='pincode',null=True)
    totalpieces = models.IntegerField(verbose_name='totalpieces',default=0,blank = True)
    totalquanity =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,blank = True,verbose_name= 'totalquanity')
    advance =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,blank = True,verbose_name= 'advance')
    remarks = models.CharField(max_length=500, null=True,verbose_name= 'Remarks')
    transport =  models.IntegerField(verbose_name='transport',null = True)
    transport =  models.ForeignKey(to = 'financial.account', on_delete=models.PROTECT,null=True,related_name='nptransport')
    broker =  models.ForeignKey(to = 'financial.account', on_delete=models.PROTECT,null=True,related_name='npbroker')
    tds194q =  models.DecimalField(max_digits=14, decimal_places=4,default=0, verbose_name= 'TDS 194 @')
    tds194q1 =  models.DecimalField(max_digits=14, decimal_places=4,default=0, verbose_name= 'TDS 194 @')
    tcs206c1ch1 =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,verbose_name= 'Tcs 206C1cH1')
    tcs206c1ch2 =  models.DecimalField(max_digits=14, decimal_places=4,default=0, verbose_name= 'Tcs 206C1cH2')
    tcs206c1ch3 =  models.DecimalField(max_digits=14, decimal_places=4,default=0, verbose_name= 'Tcs tcs206c1ch3')
    tcs206C1 =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,verbose_name= 'Tcs 206C1')
    tcs206C2 =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,verbose_name= 'Tcs 206C2')
    duedate = models.DateTimeField(verbose_name='Due Date',null = True)
    inputdate = models.DateTimeField(verbose_name='Input Date',null = True)
    vehicle = models.CharField(max_length=50, null=True,verbose_name='Vehicle')
    grno = models.CharField(max_length=50,null=True,verbose_name='GR No')
    gstr2astatus = models.BooleanField(verbose_name='GstR 2A Status',default= 1)
    showledgeraccount = models.BooleanField(verbose_name='Show Ledger Account',default= 1)
    subtotal = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Sub Total')
    cgst = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'C.GST',default=0)
    sgst = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'S.GST',default=0)
    igst = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'I.GST',default=0)
    addless =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'Add/Less')
    # cgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'C.GST Cess',default=0)
    # sgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'S.GST Cess',default=0)
    cess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Cess',default=0)
    expenses = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Expenses',default=0)
    gtotal = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'G Total')
    subentity = models.ForeignKey(subentity,on_delete=models.PROTECT,verbose_name= 'subentity',null= True)
    entity = models.ForeignKey(Entity,on_delete=models.PROTECT,verbose_name= 'entity')
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.PROTECT,verbose_name= 'entity Financial year',null= True)
    createdby = models.ForeignKey(to= User, on_delete=models.PROTECT,null=True)


    class Meta:
        unique_together = ('voucherno', 'entity',)
        unique_together = ('billno', 'account','entity','entityfinid',)
        

    def __str__(self):
        return f'{self.voucherno} '
    
class newPurchaseOrderDetails(models.Model):
    purchaseorder = models.ForeignKey(to = newpurchaseorder,related_name='purchaseorderdetails', on_delete=models.PROTECT,verbose_name= 'Purchase Order Number')
    product = models.ForeignKey(to = Product, on_delete=models.PROTECT,verbose_name= 'Product',null = True)
    productdesc = models.CharField(max_length=500, null=True,verbose_name='Product Desc')
    orderqty =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Order Qty')
    pieces =  models.IntegerField(verbose_name='pieces')
    rate =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Rate')
    amount =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Amount')
    cgst =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'CGST')
    sgst =  models.DecimalField(max_digits=14,null = True,decimal_places=4,verbose_name= 'SGST')
    igst =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'IGST')
    othercharges =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'other charges',default=0,null=True)
    cess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Cess',default=0)
    linetotal =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Line Total')
    subentity = models.ForeignKey(subentity,on_delete=models.PROTECT,verbose_name= 'subentity',null= True)
    entity = models.ForeignKey(Entity,on_delete=models.PROTECT,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete=models.PROTECT,null=True)


class salereturn(TrackingModel):
    voucherdate = models.DateField(verbose_name='Vocucher Date',auto_now_add=True)
    voucherno = models.IntegerField(verbose_name='Voucher No')
    account = models.ForeignKey(to = account, on_delete=models.PROTECT,null=True,blank=True)
    billno = models.IntegerField(verbose_name='Bill No')
    billdate = models.DateTimeField(verbose_name='Bill Date',null = True)
    terms = models.IntegerField(verbose_name='Terms')
    taxtype = models.IntegerField(verbose_name='TaxType')
    billcash = models.IntegerField(verbose_name='Bill/Cash')
    state       = models.ForeignKey(to=State,on_delete=models.PROTECT,null=True)
    district    = models.ForeignKey(to=District,on_delete=models.PROTECT,null=True)
    city       = models.ForeignKey(to=City,on_delete=models.PROTECT,null=True)
    pincode = models.CharField(max_length=50,verbose_name='pincode',null=True)
    totalpieces = models.IntegerField(verbose_name='totalpieces',default=0,blank = True)
    totalquanity =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,blank = True,verbose_name= 'totalquanity')
    advance =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,blank = True,verbose_name= 'advance')
    remarks = models.CharField(max_length=500, null=True,verbose_name= 'Remarks')
    transport =  models.ForeignKey(to = 'financial.account', on_delete=models.PROTECT,null=True,related_name='srtransport')
    broker =  models.ForeignKey(to = 'financial.account', on_delete=models.PROTECT,null=True,related_name='srbroker')
    taxid = models.IntegerField(verbose_name='Terms',default = 0)
    tds194q =  models.DecimalField(max_digits=14, decimal_places=4,default=0, verbose_name= 'TDS 194 @')
    tds194q1 =  models.DecimalField(max_digits=14, decimal_places=4,default=0, verbose_name= 'TDS 194 @')
    tcs206c1ch1 =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,verbose_name= 'Tcs 206C1cH1')
    tcs206c1ch2 =  models.DecimalField(max_digits=14, decimal_places=4,default=0, verbose_name= 'Tcs 206C1cH2')
    tcs206c1ch3 =  models.DecimalField(max_digits=14, decimal_places=4,default=0, verbose_name= 'Tcs tcs206c1ch3')
    tcs206C1 =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,verbose_name= 'Tcs 206C1')
    tcs206C2 =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,verbose_name= 'Tcs 206C2')
    duedate = models.DateTimeField(verbose_name='Due Date',null = True)
    inputdate = models.DateTimeField(verbose_name='Input Date',null = True)
    vehicle = models.CharField(max_length=50, null=True,verbose_name='Vehicle')
    grno = models.CharField(max_length=50,null=True,verbose_name='GR No')
    gstr2astatus = models.BooleanField(verbose_name='GstR 2A Status',default= 1)
    showledgeraccount = models.BooleanField(verbose_name='Show Ledger Account',default= 1)
    subtotal = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Sub Total')
    cgst = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'C.GST',default=0)
    sgst = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'S.GST',default=0)
    igst = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'I.GST',default=0)
    apptaxrate =  models.DecimalField(max_digits=4, decimal_places=2,default=0,verbose_name= 'app tax rate')
    invoicetype = models.ForeignKey(InvoiceType,on_delete=models.PROTECT,verbose_name= 'Invoice Type',null= True)
    ecom =  models.ForeignKey(to = 'financial.account', on_delete=models.PROTECT,null=True,related_name='ecommerce3')
    reversecharge =   models.BooleanField(default=False,verbose_name= 'Reverse charge')
    addless =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'Add/Less')
    # cgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'C.GST Cess',default=0)
    # sgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'S.GST Cess',default=0)
    cess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Cess',default=0)
    expenses = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Expenses',default=0)
    gtotal = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'G Total')
    subentity = models.ForeignKey(subentity,on_delete=models.PROTECT,verbose_name= 'subentity',null= True)
    entity = models.ForeignKey(Entity,on_delete=models.PROTECT,verbose_name= 'entity')
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.PROTECT,verbose_name= 'entity Financial year',null= True)
    createdby = models.ForeignKey(to= User, on_delete=models.PROTECT,null=True)

    class Meta:
        unique_together = ('voucherno', 'entity','entityfinid',)


    def __str__(self):
        return f'{self.voucherno} '

class salereturnDetails(models.Model):
    salereturn = models.ForeignKey(to = salereturn,related_name='salereturndetails', on_delete=models.PROTECT,verbose_name= 'Purchase Order Number')
    product = models.ForeignKey(to = Product, on_delete=models.PROTECT,verbose_name= 'Product',null = True)
    productdesc = models.CharField(max_length=500, null=True,verbose_name='Prduct Desc')
    orderqty =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Order Qty')
    pieces =  models.IntegerField(verbose_name='pieces')
    rate =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Rate')
    amount =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Amount')
   # account   = models.ForeignKey(to = account, on_delete=models.PROTECT,blank=True,null=True,verbose_name= 'Other account')
    othercharges =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'other charges',default=0,null=True)
    cgst =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'CGST')
    sgst =  models.DecimalField(max_digits=14,null = True,decimal_places=4,verbose_name= 'SGST')
    igst =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'IGST')
    isigst =   models.BooleanField(default=True)
    cgstpercent = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'C.GST Percent',default=0)
    sgstpercent = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'S.GST Percent',default=0)
    igstpercent = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'I.GST Percent',default=0)
    # cgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'C.GST Cess',default=0)
    # sgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'S.GST Cess',default=0)
    cess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Cess',default=0)
    linetotal =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Line Total')
    #test =  models.IntegerField(null=True)
    subentity = models.ForeignKey(subentity,on_delete=models.PROTECT,verbose_name= 'subentity',null= True)
    entity = models.ForeignKey(Entity,on_delete=models.PROTECT,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete=models.PROTECT,null=True)




class salereturnothercharges(TrackingModel):
    salesreturnorderdetail = models.ForeignKey(to = salereturnDetails,related_name='otherchargesdetail', on_delete=models.PROTECT,verbose_name= 'Sale Order Number',null=True)
    account = models.ForeignKey(to = account, on_delete=models.PROTECT,null = True,)
    amount =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'amount')


    def __str__(self):
        return f'{self.salesreturnorderdetail}'




class journalmain(TrackingModel):
    voucherdate = models.DateField(verbose_name='Vocucher Date',auto_now_add=True)
    voucherno = models.IntegerField(verbose_name='Voucher No')
    vouchertype = models.CharField(max_length=50, null=True,verbose_name='Voucher Type',default='J')
    mainaccountid = models.IntegerField(verbose_name='Main account Id',null=True)
    entrydate = models.DateTimeField(verbose_name='Entry Date')
    entity = models.ForeignKey(Entity,on_delete=models.PROTECT,verbose_name= 'entity')
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.PROTECT,verbose_name= 'entity Financial year',null= True)
    createdby = models.ForeignKey(to= User, on_delete=models.PROTECT,null=True)


    class Meta:
        unique_together = ('voucherno','vouchertype','entity',)
        


    def __str__(self):
        return f'{self.voucherno}  '



class journaldetails(TrackingModel):
    Journalmain = models.ForeignKey(to = journalmain,related_name='journaldetails', on_delete=models.PROTECT,null=True,blank=True,verbose_name='Journal Main')
    account = models.ForeignKey(to = account, on_delete=models.PROTECT,null=True,blank=True,verbose_name='Account Name')
    desc = models.CharField(max_length=500, null=True,verbose_name='Description')
    drcr = models.BooleanField(verbose_name='Debit/Credit')
    debitamount =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Debit Amount',null=True)
    creditamount =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Credit Amount',null=True)
    discount =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Discount',null=True,default=0)
    bankcharges =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Bank Charges',null=True,default=0)
    tds =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'tds',null=True,default=0)
    chqbank = models.CharField(max_length=500, null=True,verbose_name='Chq.no + Bank')
    entity = models.ForeignKey(Entity,on_delete=models.PROTECT,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete=models.PROTECT,null=True)



class ReceiptVoucher(TrackingModel):
    voucher_number = models.IntegerField(max_length=50,)
    vouchernumber = models.CharField(max_length=50,null= True)
    voucherdate = models.DateTimeField(verbose_name='Vocucher Date',null=True, blank=True)
    received_in = models.ForeignKey(account,on_delete=models.CASCADE)
    received_from = models.ForeignKey(account, related_name='receipt_vouchers', on_delete=models.CASCADE)
    account_type = models.ForeignKey(accounttype, related_name='account_type',null=True, blank=True, on_delete=models.CASCADE)
    payment_mode = models.ForeignKey(Paymentmodes, related_name='Payment_mode',null=True, on_delete=models.CASCADE)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    narration = models.TextField(blank=True, null=True)
    reference_number = models.CharField(max_length=100, blank=True, null=True)
    isledgerposting =   models.BooleanField(default=False)
    receiverbankname = models.CharField(max_length=100,null=True, blank=True, )
    chqno = models.CharField(max_length=50,null=True, blank=True, )
    chqdate =  models.DateTimeField(verbose_name='chq Date',null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_receipt_vouchers')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_receipt_vouchers')
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    entity = models.ForeignKey(Entity,on_delete=models.PROTECT,null=True, verbose_name= 'entity')
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.PROTECT,verbose_name= 'entity Financial year',null= True)

    def __str__(self):
        return f"Receipt Voucher #{self.voucher_number}"


class ReceiptVoucherInvoiceAllocation(models.Model):
    receipt_voucher = models.ForeignKey(ReceiptVoucher, related_name='invoice_allocations', on_delete=models.CASCADE)
    invoice = models.ForeignKey('SalesOderHeader', on_delete=models.CASCADE)
    trans_amount = models.DecimalField(max_digits=12, decimal_places=2,default =0,null=True, blank=True, )
    otheraccount = models.ForeignKey(account,on_delete=models.CASCADE,null=True,blank=True,)
    other_amount = models.DecimalField(max_digits=12, decimal_places=2,default =0,null=True, blank=True, )
    allocated_amount = models.DecimalField(max_digits=12, decimal_places=2)
    isfullamtreceived =   models.BooleanField(default=False)

    def __str__(self):
        return f"{self.receipt_voucher.voucher_number} - Invoice {self.invoice.invoicenumber}"
    









class stockmain(TrackingModel):
    voucherdate = models.DateField(verbose_name='Vocucher Date',auto_now_add=True)
    voucherno = models.IntegerField(verbose_name='Voucher No')
    vouchertype = models.CharField(max_length=50, null=True,verbose_name='Voucher Type',default='PC')
    entrydate = models.DateTimeField(verbose_name='Entry Date')
    entity = models.ForeignKey(Entity,on_delete=models.PROTECT,verbose_name= 'entity')
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.PROTECT,verbose_name= 'entity Financial year',null= True)
    createdby = models.ForeignKey(to= User, on_delete=models.PROTECT,null=True)


    class Meta:
        unique_together = ('voucherno','vouchertype','entity','entityfinid',)

    def __str__(self):
        return f'{self.voucherno} '



class stockdetails(TrackingModel):
    stockmain = models.ForeignKey(to = stockmain,related_name='stockdetails', on_delete=models.PROTECT,null=True,blank=True,verbose_name='Journal Main')
    stock = models.ForeignKey(to = Product, on_delete=models.PROTECT,null=True,blank=True,verbose_name='Product Name')
    desc = models.CharField(max_length=500, null=True,verbose_name='Description')
    issuereceived = models.BooleanField(verbose_name='Issue/Receipt')
    issuedquantity =  models.DecimalField(max_digits=14,null = True, decimal_places=4,verbose_name= 'Issued quantity')
    recivedquantity =  models.DecimalField(max_digits=14,null = True, decimal_places=4,verbose_name= 'Received quantity')
    entity = models.ForeignKey(Entity,on_delete=models.PROTECT,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete=models.PROTECT,null=True)




class productionmain(TrackingModel):
    voucherdate = models.DateField(verbose_name='Vocucher Date',auto_now_add=True)
    voucherno = models.IntegerField(verbose_name='Voucher No')
    vouchertype = models.CharField(max_length=50, null=True,verbose_name='Voucher Type',default='PV')
    entrydate = models.DateTimeField(verbose_name='Entry Date')
    entity = models.ForeignKey(Entity,on_delete=models.PROTECT,verbose_name= 'entity')
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.PROTECT,verbose_name= 'entity Financial year',null= True)
    createdby = models.ForeignKey(to= User, on_delete=models.PROTECT,null=True)


    class Meta:
        unique_together = ('voucherno','vouchertype','entity','entityfinid',)

    def __str__(self):
        return f'{self.voucherno} '



class productiondetails(TrackingModel):
    stockmain = models.ForeignKey(to = productionmain,related_name='stockdetails', on_delete=models.PROTECT,null=True,blank=True,verbose_name='Journal Main')
    stock = models.ForeignKey(to = Product, on_delete=models.PROTECT,null=True,blank=True,verbose_name='Product Name')
    desc = models.CharField(max_length=500, null=True,verbose_name='Description')
    issuereceived = models.BooleanField(verbose_name='Issue/Receipt')
    quantity =  models.DecimalField(max_digits=14,null = True, decimal_places=4,verbose_name= 'Issued quantity')
    rate =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Rate',null = True)
    entity = models.ForeignKey(Entity,on_delete=models.PROTECT,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete=models.PROTECT,null=True)









class journal(TrackingModel):
    voucherdate = models.DateField(verbose_name='Vocucher Date',auto_now_add=True)
    voucherno = models.IntegerField(verbose_name='Voucher No')
    vouchertype = models.CharField(max_length=50, null=True,verbose_name='Voucher Type',default='J')
    account = models.ForeignKey(to = account, on_delete=models.PROTECT,null=True,blank=True,verbose_name='Account Name')
    desc = models.CharField(max_length=500, null=True,verbose_name='Description')
    drcr = models.BooleanField(verbose_name='Debit/Credit')
    amount =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Amount')
    entrydate = models.DateField(verbose_name='Entry Date',auto_now_add=True)
    entity = models.ForeignKey(Entity,on_delete=models.PROTECT,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete=models.PROTECT,null=True)

    
    class Meta:
        verbose_name = 'journal'
        verbose_name_plural = 'journal'
        




class Transactions(TrackingModel):
    account = models.ForeignKey(to = account, on_delete=models.PROTECT,null=True,blank=True,verbose_name='Account Name')
    transactiontype = models.CharField(max_length=50, null=True,verbose_name='TransactionType')
    transactionid = models.IntegerField(verbose_name='Transaction id')
    desc = models.CharField(max_length=500, null=True,verbose_name='Description')
    drcr = models.BooleanField(verbose_name='Debit/Credit')
    amount =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Amount')
    entrydate = models.DateField(verbose_name='Entry Date',auto_now_add=True)
    entity = models.ForeignKey(Entity,on_delete=models.PROTECT,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete=models.PROTECT,null=True)

class entry(TrackingModel):
    entrydate1 = models.DateField(verbose_name='entrydate1')
    account = models.ForeignKey(to = account, on_delete=models.PROTECT,null=True,blank=True,verbose_name='Account Name',related_name='accountentryrans')
    openingbalance =  models.DecimalField(max_digits=14,null = True,decimal_places=4,verbose_name= 'Opening Amount')
    closingbalance =  models.DecimalField(max_digits=14,null = True,decimal_places=4,verbose_name= 'closing Amount')
    entity = models.ForeignKey(Entity,null=True,on_delete=models.PROTECT,verbose_name= 'entity')
 

class accountentry(TrackingModel):
    entrydate2 = models.DateField()
    account = models.ForeignKey(to = account, on_delete=models.PROTECT,null=True,blank=True,verbose_name='Account Name',related_name='accountentryrans1')
    openingbalance =  models.DecimalField(max_digits=14,null = True,decimal_places=4,verbose_name= 'Opening Amount')
    closingbalance =  models.DecimalField(max_digits=14,null = True,decimal_places=4,verbose_name= 'closing Amount')
    entity = models.ForeignKey(Entity,null=True,on_delete=models.PROTECT,verbose_name= 'entity')

class ExtractDate(Func):
    function = 'DATE'
    output_field = DateField()

class StockTransactions(TrackingModel):
    accounthead = models.ForeignKey(to = accountHead, on_delete=models.PROTECT,null=True,blank=True,verbose_name='Account Head',related_name='headtrans')
    account = models.ForeignKey(to = account, on_delete=models.PROTECT,null=True,blank=True,verbose_name='Account Name',related_name='accounttrans')
    stock = models.ForeignKey(to = Product, on_delete=models.PROTECT,null=True,blank=True,verbose_name='Product Name',related_name='stocktrans')
    transactiontype = models.CharField(max_length=50, null=True,verbose_name='TransactionType')
    transactionid = models.IntegerField(verbose_name='Transaction id')
    voucherno = models.IntegerField(verbose_name='voucherno',null=True)
    desc = models.CharField(max_length=500, null=True,verbose_name='Description')
    stockttype = models.CharField(verbose_name='Stock Transaction',max_length=10,null=True)
    quantity =  models.DecimalField(max_digits=14,null = True, decimal_places=4,verbose_name= 'quantity',blank=True)
    rate =  models.DecimalField(max_digits=14,null = True, decimal_places=4,verbose_name= 'Rate',blank=True)
    drcr = models.BooleanField(verbose_name='Debit/Credit',null = True)
    debitamount =  models.DecimalField(max_digits=14,null = True,decimal_places=4,verbose_name= 'Debit Amount',blank=True)
    creditamount =  models.DecimalField(max_digits=14,null = True, decimal_places=4,verbose_name= 'Credit Amount',blank=True)
    entry = models.ForeignKey(entry,null=True,on_delete=models.PROTECT,related_name='cashtrans')
    entrydate = models.DateField(verbose_name='Entry Date',null=True,blank=True)
    entrydatetime = models.DateTimeField(verbose_name='Entry Date', null=True,blank=True)
    accounttype = models.CharField(max_length=10, null=True,verbose_name='accounttype',blank=True)
    # subtotal =  models.DecimalField(max_digits=14,null = True, decimal_places=4,verbose_name= 'Sub Total')
    pieces = models.IntegerField(verbose_name='Pieces',null=True,blank=True)
    weightqty =  models.DecimalField(max_digits=14,null = True, decimal_places=4,verbose_name= 'Weight Quantity',blank=True)
    iscashtransaction = models.BooleanField(verbose_name='Cash Transaction',default = False)
    isbalancesheet =   models.BooleanField(default=True)
    istrial =   models.BooleanField(default=True)
    entity = models.ForeignKey(Entity,on_delete=models.PROTECT,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete=models.PROTECT,null=True)

    # class Meta:
    #     indexes = [
    #         # Composite index on entity and entrydatetime
    #         Index(fields=['entity', 'entrydatetime'], name='entity_entry_dt_idx'),
            
    #         # Indexes on accounttype and transactiontype to speed up filters
    #         Index(fields=['accounttype'], name='accounttype_idx'),
    #         Index(fields=['transactiontype'], name='transactiontype_idx'),

    #         # Functional index using your custom immutable_date function
    #         Index(
    #             Func(F('entrydatetime'), function='immutable_date', output_field=DateField()),
    #             name='entrydate_idx'
    #         ),
    #     ]



class goodstransaction(TrackingModel):
    account = models.ForeignKey(to = account, on_delete=models.PROTECT,null=True,blank=True,verbose_name='Account Name',related_name='Goodaccount')
    stock = models.ForeignKey(to = Product, on_delete=models.PROTECT,null=True,blank=True,verbose_name='Product Name', related_name='goods')
    transactiontype = models.CharField(max_length=50, null=True,verbose_name='TransactionType')
    transactionid = models.IntegerField(verbose_name='Transaction id')
    desc = models.CharField(max_length=500, null=True,verbose_name='Description')
    stockttype = models.CharField(verbose_name='Stock Transaction',max_length=10,null=True)
    salequantity =  models.DecimalField(max_digits=14,null = True, decimal_places=4,verbose_name= 'Sale quantity')
    purchasequantity =  models.DecimalField(max_digits=14,null = True, decimal_places=4,verbose_name= 'Purchase quantity')
    issuedquantity =  models.DecimalField(max_digits=14,null = True, decimal_places=4,verbose_name= 'Issued quantity')
    recivedquantity =  models.DecimalField(max_digits=14,null = True, decimal_places=4,verbose_name= 'Received quantity')
    entry = models.ForeignKey(entry,null=True,on_delete=models.PROTECT,related_name='gooddatetrans')
    entrydate = models.DateField(verbose_name='Entry Date',null=True)
    entrydatetime = models.DateTimeField(verbose_name='Entry Date', null=True)
    goodstransactiontype = models.CharField(max_length=50, null=True,verbose_name='Goods TransactionType')
    entity = models.ForeignKey(Entity,on_delete=models.PROTECT,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete=models.PROTECT,null=True)





class tdsreturns(TrackingModel):
    tdsreturnname = models.CharField(max_length= 255,verbose_name= 'Tds return')
    tdsreturndesc = models.CharField(max_length= 255,verbose_name= 'Tds return desc')
    # entity = models.ForeignKey(entity,null=True,on_delete=models.PROTECT)
    # createdby = models.ForeignKey(to= User, on_delete=models.PROTECT)


    def __str__(self):
        return f'{self.tdsreturnname}'






class tdstype(TrackingModel):
    tdstypename = models.CharField(max_length= 255,verbose_name= 'Tds Type')
    tdssection = models.CharField(max_length= 255,verbose_name= 'Tds Type Code')
    tdsreturn = models.ForeignKey(tdsreturns,on_delete=models.PROTECT,verbose_name= 'Tds Return',null = True)
    # entity = models.ForeignKey(entity,null=True,on_delete=models.PROTECT)
    # createdby = models.ForeignKey(to= User, on_delete=models.PROTECT)


    def __str__(self):
        return f'{self.tdstypename}'



class tdsmain(TrackingModel):
    voucherdate = models.DateField(verbose_name='Vocucher Date',default=datetime.date.today)
    voucherno = models.IntegerField(verbose_name='Voucher No')
    creditaccountid = models.ForeignKey(to = account, on_delete=models.PROTECT,null=True,blank=True,verbose_name='Credit Account Name',related_name='tdscreditaccount')
    creditdesc = models.CharField(max_length= 255,verbose_name= 'Credit Acc desc',null=True)
    debitaccountid = models.ForeignKey(to = account, on_delete=models.PROTECT,null=True,blank=True,verbose_name='debit Account Name',related_name='tdsdebitaccount')
    debitdesc = models.CharField(max_length= 255,verbose_name= 'Debit Acc desc',null=True)
    tdsaccountid = models.ForeignKey(to = account, on_delete=models.PROTECT,null=True,blank=True,verbose_name='Tds Account Name',related_name='tdsaccount1')
    tdsdesc = models.CharField(max_length= 255,verbose_name= 'Tds Acc desc',null=True)
    tdsreturnccountid = models.ForeignKey(to = tdsreturns, on_delete=models.PROTECT,null=True,blank=True,verbose_name='Tds Account Name',related_name='tdsreturnaccount1')
    tdsreturndesc = models.CharField(max_length= 255,verbose_name= 'tds return Acc desc',null=True)
    tdstype = models.ForeignKey(to = tdstype, on_delete=models.PROTECT,null=True,blank=True,verbose_name='Tds Type',related_name='tdstype')
    amount = models.DecimalField(max_digits=14,decimal_places=4,verbose_name= 'Credit Amount',default=0)
    debitamount = models.DecimalField(max_digits=14,decimal_places=4,verbose_name= 'debit Amount',default=0)
    otherexpenses = models.DecimalField(max_digits=14,null = True,decimal_places=4,verbose_name= 'other expenses',default=0)
    tdsrate = models.DecimalField(max_digits=14,decimal_places=4,verbose_name= 'tds rate',default=0)
    tdsvalue = models.DecimalField(max_digits=14,decimal_places=4,verbose_name= 'tds Value',default=0)
    surchargerate = models.DecimalField(max_digits=14,null = True,decimal_places=4,verbose_name= 'Surcharge rate',default=0)
    surchargevalue = models.DecimalField(max_digits=14,null = True,decimal_places=4,verbose_name= 'Surcharge Value',default=0)
    cessrate = models.DecimalField(max_digits=14,null = True,decimal_places=4,verbose_name= 'Cess rate',default=0)
    cessvalue = models.DecimalField(max_digits=14,null = True,decimal_places=4,verbose_name= 'Cess Value',default=0)
    hecessrate = models.DecimalField(max_digits=14,null = True,decimal_places=4,verbose_name= 'HE Cess rate',default=0)
    hecessvalue = models.DecimalField(max_digits=14,null = True,decimal_places=4,verbose_name= 'HE Cess Value',default=0)
    grandtotal = models.DecimalField(max_digits=14,decimal_places=4,verbose_name= 'Grand Total',default=0)
    tdsreturndesc = models.CharField(max_length= 255,verbose_name= 'tds return Acc desc',null=True)
    vehicleno = models.CharField(max_length= 20,verbose_name= 'vehicle no',null=True)
    grno = models.CharField(max_length= 20,verbose_name= 'GR No',null=True)
    invoiceno = models.CharField(max_length= 20,verbose_name= 'Invoice No',null=True)
    grdate = models.DateField(verbose_name='GR Date',default=datetime.date.today)
    invoicedate = models.DateField(verbose_name='Invoice Date',default=datetime.date.today)
    weight = models.DecimalField(max_digits=14,null = True,decimal_places=4,verbose_name= 'weight')
    depositdate = models.DateField(verbose_name='deposit Date',default=datetime.date.today)
    chequeno = models.CharField(max_length= 255,verbose_name= 'Cheque No',null=True)
    ledgerposting = models.IntegerField(verbose_name= 'Ledger Posting',null=True)
    chalanno = models.CharField(max_length= 255,verbose_name= 'Chalan No',null=True)
    bank = models.CharField(max_length= 255,verbose_name= 'Bank',null=True)
    transactiontype = models.CharField(max_length= 10,verbose_name= 'Transaction Type',null=True)
    transactionno = models.IntegerField(verbose_name='Transaction No',null=True)
    entityid = models.ForeignKey(Entity,null=True,on_delete=models.PROTECT)
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.PROTECT,verbose_name= 'entity Financial year',null= True)
    createdby = models.ForeignKey(to= User, on_delete=models.PROTECT,null = True)


    class Meta:
        unique_together = ('voucherno', 'entityid','entityfinid',)


    def __str__(self):
        return f'{self.voucherno}'


class debitcreditnote(TrackingModel):
    voucherdate = models.DateTimeField(verbose_name='Vocucher Date',null=True)
    voucherno = models.IntegerField(verbose_name='Voucher No')
    debitaccount = models.ForeignKey(to = account, on_delete=models.PROTECT,null=True,blank=True,verbose_name='deditaccount',related_name='dcdebitaccount')
    creditaccount = models.ForeignKey(to = account, on_delete=models.PROTECT,null=True,blank=True,verbose_name='credit account',related_name='dccreditaccount')
    detail = models.CharField(max_length=500, null=True,verbose_name='detail')
    ledgereffect = models.BooleanField(verbose_name='Effect on Ledger')
    product = models.ForeignKey(to = Product, on_delete=models.PROTECT,verbose_name= 'Product',null = True)
    quantity =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'quantity')
    rate =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Rate')
    basicvalue =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Amount')
    cndnamount =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Credit/Debit Note')
    tdssection = models.ForeignKey(to = tdstype, on_delete=models.PROTECT,null=True,blank=True,verbose_name='Tds section')
    vouchertype = models.CharField(max_length=50, null=True,verbose_name='Voucher Type',default='D')
    entity = models.ForeignKey(Entity,on_delete=models.PROTECT,verbose_name= 'entity')
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.PROTECT,verbose_name= 'entity Financial year',null= True)
    createdby = models.ForeignKey(to= User, on_delete=models.PROTECT,null=True)


    #class Meta:
        #unique_together = ('voucherno','vouchertype','entity',)

    def __str__(self):
         return f'{self.voucherno} '
    

class closingstock(TrackingModel):
    stockdate = models.DateTimeField(verbose_name='Stock Date',null=True)
    stock = models.ForeignKey(to = Product, on_delete=models.PROTECT,verbose_name= 'stock Name',null = True)
    closingrate = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Closing Rate')
    entity = models.ForeignKey(Entity,on_delete=models.CASCADE,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete=models.PROTECT,null=True)


    #class Meta:
        #unique_together = ('voucherno','vouchertype','entity',)

    def __str__(self):
         return f'{self.stock} '
    



    

class supplytype(TrackingModel):
    supplytypecode = models.CharField(max_length=10, null=True,verbose_name='supplytypecode')
    supplytypename = models.CharField(max_length=100, null=True,verbose_name='supplytypename')

    def __str__(self):
         return f'{self.supplytypecode}'








    





    







