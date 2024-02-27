import imp
#from sre_parse import Verbose
from django.db import models
from django.forms import DateField
from helpers.models import TrackingModel
from Authentication.models import User
from financial.models import account,accountHead
from inventory.models import Product
from entity.models import entity,entityfinancialyear,subentity
from inventory.models import Product
from django.db.models import Sum 
import datetime


# Create your models here.

class purchasetaxtype(TrackingModel):
    taxtypename = models.CharField(max_length= 255,verbose_name= 'Purchase tax type')
    taxtypecode = models.CharField(max_length= 255,verbose_name= 'Purchase tax Code')
    entity = models.ForeignKey(entity,null=True,on_delete=models.CASCADE)
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE)


    def __str__(self):
        return f'{self.taxtypename} '


class gstorderservices(TrackingModel):
    orderdate = models.DateTimeField(verbose_name='Order date',null = True)
    billno = models.IntegerField(verbose_name='Bill No')
    account = models.ForeignKey(to = account, on_delete= models.CASCADE,blank=True)
    taxtype = models.IntegerField(verbose_name='Tax Type',default = 1)
    billcash = models.IntegerField(verbose_name='Bill/Cash',default = 1)
    grno = models.CharField(max_length=50,verbose_name='GR No',null=True)
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
    subentity = models.ForeignKey(subentity,on_delete=models.CASCADE,verbose_name= 'subentity',null= True)
    entity = models.ForeignKey(entity,on_delete=models.CASCADE,verbose_name= 'entity',null= True)
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.CASCADE,verbose_name= 'entity Financial year',null= True)
    owner = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True)

    class Meta:
        unique_together = ('billno', 'entity','orderType','entityfinid',)

    def __str__(self):
        return f'{self.billno}'


class gstorderservicesdetails(TrackingModel):
    gstorderservices = models.ForeignKey(to = gstorderservices,related_name='gstorderservicesdetails', on_delete= models.CASCADE,verbose_name= 'Gst services Number')
    account = models.ForeignKey(to = account, on_delete= models.CASCADE,blank=True)
    accountdesc = models.CharField(max_length=500, null=True,verbose_name='account Desc')
    # orderqty =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Order Qty')
    # pieces =  models.IntegerField(verbose_name='pieces')
    multiplier =  models.IntegerField(verbose_name='multiplier')
    rate =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Rate')
    amount =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Amount',null = True)
    cgst =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'CGST',null = True)
    sgst =  models.DecimalField(max_digits=14,null = True,default = 1, decimal_places=4,verbose_name= 'SGST')
    igst =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'IGST',null = True)
    cgstreverse =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'CGST Reverse',null = True,default = 0)
    sgstreverse =  models.DecimalField(max_digits=14,null = True, decimal_places=4,verbose_name= 'SGST Reverse',default = 0)
    igstreverse =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'IGST Reverse',null = True,default = 0)
    # cess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Cess',default=0)
    linetotal =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Line Total')
    subentity = models.ForeignKey(subentity,on_delete=models.CASCADE,verbose_name= 'subentity',null= True)
    entity = models.ForeignKey(entity,on_delete=models.CASCADE,verbose_name= 'entity')
    #createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True)


    def __str__(self):
        return f'{self.account}'


    



class SalesOderHeader(TrackingModel):
    #RevisonNumber =models.IntegerFieldverbose_name=_('Main category'))
    sorderdate = models.DateTimeField(verbose_name='Sales Order date',null = True)
    billno = models.IntegerField(verbose_name='Bill No')
    accountid = models.ForeignKey(to = account, on_delete= models.CASCADE,blank=True)
    latepaymentalert = models.BooleanField(verbose_name='Late Payment Alert',default = True,null = True)
    grno = models.CharField(max_length=50,verbose_name='GR No',null=True)
    terms = models.IntegerField(verbose_name='Terms',default = 1)
    vehicle = models.CharField(max_length=50, null=True,verbose_name='Vehicle')
    taxtype = models.IntegerField(verbose_name='Tax Type',default = 1)
    billcash = models.IntegerField(verbose_name='Bill/Cash',default = 1)
    supply = models.IntegerField(verbose_name='Supply')
    totalpieces = models.IntegerField(verbose_name='totalpieces',default=0,blank = True)
    totalquanity =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,blank = True,verbose_name= 'totalquanity')
    advance =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,blank = True,verbose_name= 'advance')
    shippedto =  models.ForeignKey(to = account, on_delete= models.CASCADE,null=True,related_name='shippedto')
    remarks = models.CharField(max_length=500, null=True,verbose_name= 'Remarks')
    transport =  models.IntegerField(verbose_name='Transport',null = True)
    broker =  models.IntegerField(verbose_name='broker',null = True)
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
    discount = models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'Discount')
    cgst =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'C.GST')
    sgst =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'S.GST')
    igst =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'I.GST')
    # cgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'C.GST Cess',default=0)
    # sgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'S.GST Cess',default=0)
    cess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Cess',default=0)
    expenses =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'EXpenses')
    gtotal =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'Grand Total')
    subentity = models.ForeignKey(subentity,on_delete=models.CASCADE,verbose_name= 'subentity',null= True)
    entity = models.ForeignKey(entity,on_delete=models.CASCADE,verbose_name= 'entity',null= True)
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.CASCADE,verbose_name= 'entity Financial year',null= True)
    owner = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True)

    class Meta:
        unique_together = ('billno', 'entity','entityfinid',)


    def __str__(self):
        return f'{self.billno} '

class salesOrderdetails(TrackingModel):
    salesorderheader = models.ForeignKey(to = SalesOderHeader,related_name='saleInvoiceDetails', on_delete= models.CASCADE,verbose_name= 'Sale Order Number')
    product = models.ForeignKey(to = Product, on_delete= models.CASCADE,verbose_name= 'Product',null = True,default = 1)
    productdesc = models.CharField(max_length=500, null=True,verbose_name='product Desc')
    orderqty =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Order Qty')
    pieces =  models.IntegerField(verbose_name='pieces')
    rate =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Rate')
    amount =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Amount')
   # account   = models.ForeignKey(to = account, on_delete= models.CASCADE,blank=True,null=True,verbose_name= 'Other account')
    othercharges =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'other charges',default=0,null=True)
    cgst =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'CGST')
    sgst =  models.DecimalField(max_digits=14,null = True,default = 1, decimal_places=4,verbose_name= 'SGST')
    igst =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'IGST')
    # cgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'C.GST Cess',default=0)
    # sgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'S.GST Cess',default=0)
    cess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Cess',default=0)
    linetotal =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Line Total')
    subentity = models.ForeignKey(subentity,on_delete=models.CASCADE,verbose_name= 'subentity',null= True)
    entity = models.ForeignKey(entity,on_delete=models.CASCADE,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True)


    def __str__(self):
        return f'{self.product} '
    

class SalesOder(TrackingModel):
    #RevisonNumber =models.IntegerFieldverbose_name=_('Main category'))
    sorderdate = models.DateTimeField(verbose_name='Sales Order date',null = True)
    billno = models.IntegerField(verbose_name='Bill No')
    accountid = models.ForeignKey(to = account, on_delete= models.CASCADE,blank=True)
    latepaymentalert = models.BooleanField(verbose_name='Late Payment Alert',default = True,null = True)
    grno = models.CharField(max_length=50,verbose_name='GR No',null=True)
    terms = models.IntegerField(verbose_name='Terms',default = 1)
    vehicle = models.CharField(max_length=50, null=True,verbose_name='Vehicle')
    taxtype = models.IntegerField(verbose_name='Tax Type',default = 1)
    billcash = models.IntegerField(verbose_name='Bill/Cash',default = 1)
    supply = models.IntegerField(verbose_name='Supply')
    totalpieces = models.IntegerField(verbose_name='totalpieces',default=0,blank = True)
    totalquanity =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,blank = True,verbose_name= 'totalquanity')
    advance =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,blank = True,verbose_name= 'advance')
    shippedto =  models.ForeignKey(to = account, on_delete= models.CASCADE,null=True,related_name='soshippedto')
    remarks = models.CharField(max_length=500, null=True,verbose_name= 'Remarks')
    transport =  models.IntegerField(verbose_name='Transport',null = True)
    broker =  models.IntegerField(verbose_name='broker',null = True)
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
    discount = models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'Discount')
    cgst =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'C.GST')
    sgst =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'S.GST')
    igst =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'I.GST')
    # cgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'C.GST Cess',default=0)
    # sgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'S.GST Cess',default=0)
    cess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Cess',default=0)
    expenses =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'EXpenses')
    gtotal =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'Grand Total')
    subentity = models.ForeignKey(subentity,on_delete=models.CASCADE,verbose_name= 'subentity',null= True)
    entity = models.ForeignKey(entity,on_delete=models.CASCADE,verbose_name= 'entity',null= True)
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.CASCADE,verbose_name= 'entity Financial year',null= True)
    owner = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True)

    class Meta:
        unique_together = ('billno', 'entity','entityfinid',)


    def __str__(self):
        return f'{self.billno} '

class salesOrderdetail(TrackingModel):
    salesorderheader = models.ForeignKey(to = SalesOder,related_name='salesOrderDetail', on_delete= models.CASCADE,verbose_name= 'Sale Order Number')
    product = models.ForeignKey(to = Product, on_delete= models.CASCADE,verbose_name= 'Product',null = True,default = 1)
    productdesc = models.CharField(max_length=500, null=True,verbose_name='product Desc')
    orderqty =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Order Qty')
    pieces =  models.IntegerField(verbose_name='pieces')
    rate =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Rate')
    amount =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Amount')
   # account   = models.ForeignKey(to = account, on_delete= models.CASCADE,blank=True,null=True,verbose_name= 'Other account')
    othercharges =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'other charges',default=0,null=True)
    cgst =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'CGST')
    sgst =  models.DecimalField(max_digits=14,null = True,default = 1, decimal_places=4,verbose_name= 'SGST')
    igst =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'IGST')
    # cgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'C.GST Cess',default=0)
    # sgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'S.GST Cess',default=0)
    cess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Cess',default=0)
    linetotal =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Line Total')
    subentity = models.ForeignKey(subentity,on_delete=models.CASCADE,verbose_name= 'subentity',null= True)
    entity = models.ForeignKey(entity,on_delete=models.CASCADE,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True)


    def __str__(self):
        return f'{self.product} '
    
class saleothercharges(TrackingModel):
    salesorderdetail = models.ForeignKey(to = salesOrderdetails,related_name='otherchargesdetail', on_delete= models.CASCADE,verbose_name= 'Sale Order Number',null=True)
    account = models.ForeignKey(to = account, on_delete= models.CASCADE,null = True,)
    amount =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'amount')


    def __str__(self):
        return f'{self.salesorderdetail}'
    







    




class PurchaseReturn(TrackingModel):
    #RevisonNumber =models.IntegerFieldverbose_name=_('Main category'))
    sorderdate = models.DateTimeField(verbose_name='Sales Order date',null = True)
    billno = models.IntegerField(verbose_name='Bill No')
    accountid = models.ForeignKey(to = account, on_delete= models.CASCADE,blank=True)
    latepaymentalert = models.BooleanField(verbose_name='Late Payment Alert',default = True,null = True)
    grno = models.CharField(max_length=50,verbose_name='GR No',null=True)
    terms = models.IntegerField(verbose_name='Terms',default = 1)
    vehicle = models.CharField(max_length=50, null=True,verbose_name='Vehicle')
    taxtype = models.IntegerField(verbose_name='Tax Type',default = 1)
    billcash = models.IntegerField(verbose_name='Bill/Cash',default = 1)
    supply = models.IntegerField(verbose_name='Supply')
    totalpieces = models.IntegerField(verbose_name='totalpieces',default=0,blank = True)
    totalquanity =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,blank = True,verbose_name= 'totalquanity')
    advance =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,blank = True,verbose_name= 'advance')
    shippedto =  models.ForeignKey(to = account, on_delete= models.CASCADE,null=True,related_name='shippedto1')
    remarks = models.CharField(max_length=500, null=True,verbose_name= 'Remarks')
    transport =  models.ForeignKey(to = account, on_delete= models.CASCADE,null=True,related_name='transport1')
    broker =  models.ForeignKey(to = account, on_delete= models.CASCADE,null=True,related_name='broker1')
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
    # cgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'C.GST Cess',default=0)
    # sgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'S.GST Cess',default=0)
    cess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Cess',default=0)
    expenses =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'EXpenses')
    gtotal =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'Grand Total')
    subentity = models.ForeignKey(subentity,on_delete=models.CASCADE,verbose_name= 'subentity',null= True)
    entity = models.ForeignKey(entity,on_delete=models.CASCADE,verbose_name= 'entity',null= True)
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.CASCADE,verbose_name= 'entity Financial year',null= True)
    owner = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True)

    # class Meta:
    #     #unique_together = ('billno', 'entity',)


    def __str__(self):
        return f'{self.billno} '

class Purchasereturndetails(TrackingModel):
    purchasereturn = models.ForeignKey(to = PurchaseReturn,related_name='purchasereturndetails', on_delete= models.CASCADE,verbose_name= 'Sale Order Number')
    product = models.ForeignKey(to = Product, on_delete= models.CASCADE,verbose_name= 'Product',null = True,default = 1)
    productdesc = models.CharField(max_length=500, null=True,verbose_name='product Desc')
    orderqty =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Order Qty')
    pieces =  models.IntegerField(verbose_name='pieces')
    rate =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Rate')
    amount =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Amount')
    #account   = models.ForeignKey(to = account, on_delete= models.CASCADE,blank=True,null=True,verbose_name= 'Other account')
    othercharges =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'other charges',default=0,null=True)
    cgst =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'CGST')
    sgst =  models.DecimalField(max_digits=14,null = True,default = 1, decimal_places=4,verbose_name= 'SGST')
    igst =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'IGST')
    # cgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'C.GST Cess',default=0)
    # sgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'S.GST Cess',default=0)
    cess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Cess',default=0)
    linetotal =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Line Total')
    subentity = models.ForeignKey(subentity,on_delete=models.CASCADE,verbose_name= 'subentity',null= True)
    entity = models.ForeignKey(entity,on_delete=models.CASCADE,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True)


    def __str__(self):
        return f'{self.product} '
    

class Purchasereturnothercharges(TrackingModel):
    purchasereturnorderdetail = models.ForeignKey(to = Purchasereturndetails,related_name='otherchargesdetail', on_delete= models.CASCADE,verbose_name= 'Sale Order Number',null=True)
    account = models.ForeignKey(to = account, on_delete= models.CASCADE,null = True,)
    amount =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'amount')


    def __str__(self):
        return f'{self.purchasereturnorderdetail}'
    

class jobworkchalan(TrackingModel):
    voucherdate = models.DateField(verbose_name='Vocucher Date',auto_now_add=True)
    voucherno = models.IntegerField(verbose_name='Voucher No')
    account = models.ForeignKey(to = account, on_delete= models.CASCADE,null=True,blank=True)
    billno = models.IntegerField(verbose_name='Bill No')
    billdate = models.DateTimeField(verbose_name='Bill Date',null = True)
    terms = models.IntegerField(verbose_name='Terms')
    taxtype = models.IntegerField(verbose_name='TaxType')
    billcash = models.IntegerField(verbose_name='Bill/Cash')
    totalpieces = models.IntegerField(verbose_name='totalpieces',default=0,blank = True)
    totalquanity =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,blank = True,verbose_name= 'totalquanity')
    advance =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,blank = True,verbose_name= 'advance')
    remarks = models.CharField(max_length=500, null=True,verbose_name= 'Remarks')
    transport =  models.IntegerField(verbose_name='transport',null = True)
    broker =  models.IntegerField(verbose_name='broker',null = True)
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
    subentity = models.ForeignKey(subentity,on_delete=models.CASCADE,verbose_name= 'subentity',null= True)
    entity = models.ForeignKey(entity,on_delete=models.CASCADE,verbose_name= 'entity')
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.CASCADE,verbose_name= 'entity Financial year',null= True)
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True)


    class Meta:
        unique_together = ('voucherno', 'entity',)
        unique_together = ('billno', 'account','entity','ordertype','entityfinid',)
        

    def __str__(self):
        return f'{self.voucherno} '

class jobworkchalanDetails(models.Model):
    jobworkchalan = models.ForeignKey(to = jobworkchalan,related_name='jobworkchalanDetails', on_delete= models.CASCADE,verbose_name= 'Purchase Order Number')
    product = models.ForeignKey(to = Product, on_delete= models.CASCADE,verbose_name= 'Product',null = True,default = 1)
    productdesc = models.CharField(max_length=500, null=True,verbose_name='Product Desc')
    orderqty =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Order Qty')
    pieces =  models.IntegerField(verbose_name='pieces')
    rate =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Rate')
    amount =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Amount')
    cgst =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'CGST')
    sgst =  models.DecimalField(max_digits=14,null = True,default = 1, decimal_places=4,verbose_name= 'SGST')
    igst =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'IGST')
    # cgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'C.GST Cess',default=0)
    # sgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'S.GST Cess',default=0)
    cess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Cess',default=0)
    linetotal =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Line Total')
    subentity = models.ForeignKey(subentity,on_delete=models.CASCADE,verbose_name= 'subentity',null= True)
    
    entity = models.ForeignKey(entity,on_delete=models.CASCADE,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True)


class purchaseorderimport(TrackingModel):
    voucherdate = models.DateField(verbose_name='Vocucher Date',auto_now_add=True)
    voucherno = models.IntegerField(verbose_name='Voucher No')
    account = models.ForeignKey(to = account, on_delete= models.CASCADE,null=True,blank=True)
    billno = models.IntegerField(verbose_name='Bill No')
    billdate = models.DateTimeField(verbose_name='Bill Date',null = True)
    terms = models.IntegerField(verbose_name='Terms')
    taxtype = models.IntegerField(verbose_name='TaxType')
    billcash = models.IntegerField(verbose_name='Bill/Cash')
    totalpieces = models.IntegerField(verbose_name='totalpieces',default=0,blank = True)
    totalquanity =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,blank = True,verbose_name= 'totalquanity')
    advance =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,blank = True,verbose_name= 'advance')
    remarks = models.CharField(max_length=500, null=True,verbose_name= 'Remarks')
    transport =  models.IntegerField(verbose_name='transport',null = True)
    broker =  models.IntegerField(verbose_name='broker',null = True)
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
    subentity = models.ForeignKey(subentity,on_delete=models.CASCADE,verbose_name= 'subentity',null= True)
    entity = models.ForeignKey(entity,on_delete=models.CASCADE,verbose_name= 'entity')
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.CASCADE,verbose_name= 'entity Financial year',null= True)
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True)


    class Meta:
        unique_together = ('voucherno', 'entity',)
        unique_together = ('billno', 'account','entity','entityfinid',)
        

    def __str__(self):
        return f'{self.voucherno}'
    


class PurchaseOrderimportdetails(models.Model):
    purchaseorder = models.ForeignKey(to = purchaseorderimport,related_name='PurchaseOrderimportdetails', on_delete= models.CASCADE,verbose_name= 'Purchase Order Number')
    product = models.ForeignKey(to = Product, on_delete= models.CASCADE,verbose_name= 'Product',null = True,default = 1)
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
    subentity = models.ForeignKey(subentity,on_delete=models.CASCADE,verbose_name= 'subentity',null= True)
    entity = models.ForeignKey(entity,on_delete=models.CASCADE,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True)



class purchaseotherimportcharges(TrackingModel):
    purchaseorderdetail = models.ForeignKey(to = PurchaseOrderimportdetails,related_name='otherchargesdetail', on_delete= models.CASCADE,verbose_name= 'Purchase Order detail',null=True)
    account = models.ForeignKey(to = account, on_delete= models.CASCADE,null = True,)
    amount =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'amount')


    def __str__(self):
        return f'{self.purchaseorderdetail}'




    



class purchaseorder(TrackingModel):
    voucherdate = models.DateField(verbose_name='Vocucher Date',auto_now_add=True)
    voucherno = models.IntegerField(verbose_name='Voucher No')
    account = models.ForeignKey(to = account, on_delete= models.CASCADE,null=True,blank=True)
    billno = models.IntegerField(verbose_name='Bill No')
    billdate = models.DateTimeField(verbose_name='Bill Date',null = True)
    terms = models.IntegerField(verbose_name='Terms')
    taxtype = models.IntegerField(verbose_name='TaxType')
    billcash = models.IntegerField(verbose_name='Bill/Cash')
    totalpieces = models.IntegerField(verbose_name='totalpieces',default=0,blank = True)
    totalquanity =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,blank = True,verbose_name= 'totalquanity')
    advance =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,blank = True,verbose_name= 'advance')
    remarks = models.CharField(max_length=500, null=True,verbose_name= 'Remarks')
    transport =  models.IntegerField(verbose_name='transport',null = True)
    broker =  models.IntegerField(verbose_name='broker',null = True)
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
    addless =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'Add/Less')
    # cgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'C.GST Cess',default=0)
    # sgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'S.GST Cess',default=0)
    cess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Cess',default=0)
    expenses = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Expenses',default=0)
    gtotal = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'G Total')
    subentity = models.ForeignKey(subentity,on_delete=models.CASCADE,verbose_name= 'subentity',null= True)
    entity = models.ForeignKey(entity,on_delete=models.CASCADE,verbose_name= 'entity')
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.CASCADE,verbose_name= 'entity Financial year',null= True)
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True)


    class Meta:
        unique_together = ('voucherno', 'entity',)
        unique_together = ('billno', 'account','entity','entityfinid',)
        

    def __str__(self):
        return f'{self.voucherno} '

class PurchaseOrderDetails(models.Model):
    purchaseorder = models.ForeignKey(to = purchaseorder,related_name='purchaseInvoiceDetails', on_delete= models.CASCADE,verbose_name= 'Purchase Order Number')
    product = models.ForeignKey(to = Product, on_delete= models.CASCADE,verbose_name= 'Product',null = True,default = 1)
    productdesc = models.CharField(max_length=500, null=True,verbose_name='Product Desc')
    orderqty =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Order Qty')
    pieces =  models.IntegerField(verbose_name='pieces')
    rate =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Rate')
    amount =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Amount')
    cgst =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'CGST')
    sgst =  models.DecimalField(max_digits=14,null = True,default = 1, decimal_places=4,verbose_name= 'SGST')
    igst =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'IGST')
    othercharges =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'other charges',default=0,null=True)
    cess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Cess',default=0)
    linetotal =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Line Total')
    subentity = models.ForeignKey(subentity,on_delete=models.CASCADE,verbose_name= 'subentity',null= True)
    entity = models.ForeignKey(entity,on_delete=models.CASCADE,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True)



class purchaseothercharges(TrackingModel):
    purchaseorderdetail = models.ForeignKey(to = PurchaseOrderDetails,related_name='otherchargesdetail', on_delete= models.CASCADE,verbose_name= 'Purchase Order detail',null=True)
    account = models.ForeignKey(to = account, on_delete= models.CASCADE,null = True,)
    amount =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'amount')


    def __str__(self):
        return f'{self.purchaseorderdetail}'


class newpurchaseorder(TrackingModel):
    voucherdate = models.DateField(verbose_name='Vocucher Date',auto_now_add=True)
    voucherno = models.IntegerField(verbose_name='Voucher No')
    account = models.ForeignKey(to = account, on_delete= models.CASCADE,null=True,blank=True)
    billno = models.IntegerField(verbose_name='Bill No')
    billdate = models.DateTimeField(verbose_name='Bill Date',null = True)
    terms = models.IntegerField(verbose_name='Terms')
    taxtype = models.IntegerField(verbose_name='TaxType')
    billcash = models.IntegerField(verbose_name='Bill/Cash')
    totalpieces = models.IntegerField(verbose_name='totalpieces',default=0,blank = True)
    totalquanity =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,blank = True,verbose_name= 'totalquanity')
    advance =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,blank = True,verbose_name= 'advance')
    remarks = models.CharField(max_length=500, null=True,verbose_name= 'Remarks')
    transport =  models.IntegerField(verbose_name='transport',null = True)
    broker =  models.IntegerField(verbose_name='broker',null = True)
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
    addless =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'Add/Less')
    # cgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'C.GST Cess',default=0)
    # sgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'S.GST Cess',default=0)
    cess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Cess',default=0)
    expenses = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Expenses',default=0)
    gtotal = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'G Total')
    subentity = models.ForeignKey(subentity,on_delete=models.CASCADE,verbose_name= 'subentity',null= True)
    entity = models.ForeignKey(entity,on_delete=models.CASCADE,verbose_name= 'entity')
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.CASCADE,verbose_name= 'entity Financial year',null= True)
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True)


    class Meta:
        unique_together = ('voucherno', 'entity',)
        unique_together = ('billno', 'account','entity','entityfinid',)
        

    def __str__(self):
        return f'{self.voucherno} '
    
class newPurchaseOrderDetails(models.Model):
    purchaseorder = models.ForeignKey(to = newpurchaseorder,related_name='purchaseorderdetails', on_delete= models.CASCADE,verbose_name= 'Purchase Order Number')
    product = models.ForeignKey(to = Product, on_delete= models.CASCADE,verbose_name= 'Product',null = True,default = 1)
    productdesc = models.CharField(max_length=500, null=True,verbose_name='Product Desc')
    orderqty =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Order Qty')
    pieces =  models.IntegerField(verbose_name='pieces')
    rate =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Rate')
    amount =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Amount')
    cgst =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'CGST')
    sgst =  models.DecimalField(max_digits=14,null = True,default = 1, decimal_places=4,verbose_name= 'SGST')
    igst =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'IGST')
    othercharges =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'other charges',default=0,null=True)
    cess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Cess',default=0)
    linetotal =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Line Total')
    subentity = models.ForeignKey(subentity,on_delete=models.CASCADE,verbose_name= 'subentity',null= True)
    entity = models.ForeignKey(entity,on_delete=models.CASCADE,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True)


class salereturn(TrackingModel):
    voucherdate = models.DateField(verbose_name='Vocucher Date',auto_now_add=True)
    voucherno = models.IntegerField(verbose_name='Voucher No')
    account = models.ForeignKey(to = account, on_delete= models.CASCADE,null=True,blank=True)
    billno = models.IntegerField(verbose_name='Bill No')
    billdate = models.DateTimeField(verbose_name='Bill Date',null = True)
    terms = models.IntegerField(verbose_name='Terms')
    taxtype = models.IntegerField(verbose_name='TaxType')
    billcash = models.IntegerField(verbose_name='Bill/Cash')
    totalpieces = models.IntegerField(verbose_name='totalpieces',default=0,blank = True)
    totalquanity =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,blank = True,verbose_name= 'totalquanity')
    advance =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,blank = True,verbose_name= 'advance')
    remarks = models.CharField(max_length=500, null=True,verbose_name= 'Remarks')
    transport =  models.ForeignKey(to = 'financial.account', on_delete= models.CASCADE,null=True,related_name='srtransport')
    broker =  models.ForeignKey(to = 'financial.account', on_delete= models.CASCADE,null=True,related_name='srbroker')
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
    addless =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'Add/Less')
    # cgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'C.GST Cess',default=0)
    # sgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'S.GST Cess',default=0)
    cess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Cess',default=0)
    expenses = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Expenses',default=0)
    gtotal = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'G Total')
    subentity = models.ForeignKey(subentity,on_delete=models.CASCADE,verbose_name= 'subentity',null= True)
    entity = models.ForeignKey(entity,on_delete=models.CASCADE,verbose_name= 'entity')
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.CASCADE,verbose_name= 'entity Financial year',null= True)
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True)

    class Meta:
        unique_together = ('voucherno', 'entity','entityfinid',)


    def __str__(self):
        return f'{self.voucherno} '

class salereturnDetails(models.Model):
    salereturn = models.ForeignKey(to = salereturn,related_name='salereturndetails', on_delete= models.CASCADE,verbose_name= 'Purchase Order Number')
    product = models.ForeignKey(to = Product, on_delete= models.CASCADE,verbose_name= 'Product',null = True,default = 1)
    productdesc = models.CharField(max_length=500, null=True,verbose_name='Prduct Desc')
    orderqty =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Order Qty')
    pieces =  models.IntegerField(verbose_name='pieces')
    rate =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Rate')
    amount =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Amount')
   # account   = models.ForeignKey(to = account, on_delete= models.CASCADE,blank=True,null=True,verbose_name= 'Other account')
    othercharges =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'other charges',default=0,null=True)
    cgst =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'CGST')
    sgst =  models.DecimalField(max_digits=14,null = True,default = 1, decimal_places=4,verbose_name= 'SGST')
    igst =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'IGST')
    # cgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'C.GST Cess',default=0)
    # sgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'S.GST Cess',default=0)
    cess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Cess',default=0)
    linetotal =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Line Total')
    #test =  models.IntegerField(null=True)
    subentity = models.ForeignKey(subentity,on_delete=models.CASCADE,verbose_name= 'subentity',null= True)
    entity = models.ForeignKey(entity,on_delete=models.CASCADE,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True)




class salereturnothercharges(TrackingModel):
    salesreturnorderdetail = models.ForeignKey(to = salereturnDetails,related_name='otherchargesdetail', on_delete= models.CASCADE,verbose_name= 'Sale Order Number',null=True)
    account = models.ForeignKey(to = account, on_delete= models.CASCADE,null = True,)
    amount =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'amount')


    def __str__(self):
        return f'{self.salesreturnorderdetail}'




class journalmain(TrackingModel):
    voucherdate = models.DateField(verbose_name='Vocucher Date',auto_now_add=True)
    voucherno = models.IntegerField(verbose_name='Voucher No')
    vouchertype = models.CharField(max_length=50, null=True,verbose_name='Voucher Type',default='J')
    mainaccountid = models.IntegerField(verbose_name='Main account Id',null=True)
    entrydate = models.DateTimeField(verbose_name='Entry Date')
    entity = models.ForeignKey(entity,on_delete=models.CASCADE,verbose_name= 'entity')
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.CASCADE,verbose_name= 'entity Financial year',null= True)
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True)


    class Meta:
        unique_together = ('voucherno','vouchertype','entity',)
        


    def __str__(self):
        return f'{self.voucherno}  '



class journaldetails(TrackingModel):
    Journalmain = models.ForeignKey(to = journalmain,related_name='journaldetails', on_delete= models.CASCADE,null=True,blank=True,verbose_name='Journal Main')
    account = models.ForeignKey(to = account, on_delete= models.CASCADE,null=True,blank=True,verbose_name='Account Name')
    desc = models.CharField(max_length=500, null=True,verbose_name='Description')
    drcr = models.BooleanField(verbose_name='Debit/Credit')
    debitamount =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Debit Amount',null=True)
    creditamount =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Credit Amount',null=True)
    discount =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Discount',null=True,default=0)
    bankcharges =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Bank Charges',null=True,default=0)
    tds =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'tds',null=True,default=0)
    chqbank = models.CharField(max_length=500, null=True,verbose_name='Chq.no + Bank')
    entity = models.ForeignKey(entity,on_delete=models.CASCADE,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True)






class stockmain(TrackingModel):
    voucherdate = models.DateField(verbose_name='Vocucher Date',auto_now_add=True)
    voucherno = models.IntegerField(verbose_name='Voucher No')
    vouchertype = models.CharField(max_length=50, null=True,verbose_name='Voucher Type',default='PC')
    entrydate = models.DateTimeField(verbose_name='Entry Date')
    entity = models.ForeignKey(entity,on_delete=models.CASCADE,verbose_name= 'entity')
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.CASCADE,verbose_name= 'entity Financial year',null= True)
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True)


    class Meta:
        unique_together = ('voucherno','vouchertype','entity','entityfinid',)

    def __str__(self):
        return f'{self.voucherno} '



class stockdetails(TrackingModel):
    stockmain = models.ForeignKey(to = stockmain,related_name='stockdetails', on_delete= models.CASCADE,null=True,blank=True,verbose_name='Journal Main')
    stock = models.ForeignKey(to = Product, on_delete= models.CASCADE,null=True,blank=True,verbose_name='Product Name')
    desc = models.CharField(max_length=500, null=True,verbose_name='Description')
    issuereceived = models.BooleanField(verbose_name='Issue/Receipt')
    issuedquantity =  models.DecimalField(max_digits=14,null = True, decimal_places=4,verbose_name= 'Issued quantity')
    recivedquantity =  models.DecimalField(max_digits=14,null = True, decimal_places=4,verbose_name= 'Received quantity')
    entity = models.ForeignKey(entity,on_delete=models.CASCADE,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True)




class productionmain(TrackingModel):
    voucherdate = models.DateField(verbose_name='Vocucher Date',auto_now_add=True)
    voucherno = models.IntegerField(verbose_name='Voucher No')
    vouchertype = models.CharField(max_length=50, null=True,verbose_name='Voucher Type',default='PV')
    entrydate = models.DateTimeField(verbose_name='Entry Date')
    entity = models.ForeignKey(entity,on_delete=models.CASCADE,verbose_name= 'entity')
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.CASCADE,verbose_name= 'entity Financial year',null= True)
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True)


    class Meta:
        unique_together = ('voucherno','vouchertype','entity','entityfinid',)

    def __str__(self):
        return f'{self.voucherno} '



class productiondetails(TrackingModel):
    stockmain = models.ForeignKey(to = productionmain,related_name='stockdetails', on_delete= models.CASCADE,null=True,blank=True,verbose_name='Journal Main')
    stock = models.ForeignKey(to = Product, on_delete= models.CASCADE,null=True,blank=True,verbose_name='Product Name')
    desc = models.CharField(max_length=500, null=True,verbose_name='Description')
    issuereceived = models.BooleanField(verbose_name='Issue/Receipt')
    quantity =  models.DecimalField(max_digits=14,null = True, decimal_places=4,verbose_name= 'Issued quantity')
    rate =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Rate',null = True)
    entity = models.ForeignKey(entity,on_delete=models.CASCADE,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True)









class journal(TrackingModel):
    voucherdate = models.DateField(verbose_name='Vocucher Date',auto_now_add=True)
    voucherno = models.IntegerField(verbose_name='Voucher No')
    vouchertype = models.CharField(max_length=50, null=True,verbose_name='Voucher Type',default='J')
    account = models.ForeignKey(to = account, on_delete= models.CASCADE,null=True,blank=True,verbose_name='Account Name')
    desc = models.CharField(max_length=500, null=True,verbose_name='Description')
    drcr = models.BooleanField(verbose_name='Debit/Credit')
    amount =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Amount')
    entrydate = models.DateField(verbose_name='Entry Date',auto_now_add=True)
    entity = models.ForeignKey(entity,on_delete=models.CASCADE,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True)

    
    class Meta:
        verbose_name = 'journal'
        verbose_name_plural = 'journal'
        




class Transactions(TrackingModel):
    account = models.ForeignKey(to = account, on_delete= models.CASCADE,null=True,blank=True,verbose_name='Account Name')
    transactiontype = models.CharField(max_length=50, null=True,verbose_name='TransactionType')
    transactionid = models.IntegerField(verbose_name='Transaction id')
    desc = models.CharField(max_length=500, null=True,verbose_name='Description')
    drcr = models.BooleanField(verbose_name='Debit/Credit')
    amount =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Amount')
    entrydate = models.DateField(verbose_name='Entry Date',auto_now_add=True)
    entity = models.ForeignKey(entity,on_delete=models.CASCADE,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True)

class entry(TrackingModel):
    entrydate1 = models.DateField(verbose_name='entrydate1')
    account = models.ForeignKey(to = account, on_delete= models.CASCADE,null=True,blank=True,verbose_name='Account Name',related_name='accountentryrans')
    openingbalance =  models.DecimalField(max_digits=14,null = True,decimal_places=4,verbose_name= 'Opening Amount')
    closingbalance =  models.DecimalField(max_digits=14,null = True,decimal_places=4,verbose_name= 'closing Amount')
    entity = models.ForeignKey(entity,null=True,on_delete=models.CASCADE,verbose_name= 'entity')
 

class accountentry(TrackingModel):
    entrydate2 = models.DateField()
    account = models.ForeignKey(to = account, on_delete= models.CASCADE,null=True,blank=True,verbose_name='Account Name',related_name='accountentryrans1')
    openingbalance =  models.DecimalField(max_digits=14,null = True,decimal_places=4,verbose_name= 'Opening Amount')
    closingbalance =  models.DecimalField(max_digits=14,null = True,decimal_places=4,verbose_name= 'closing Amount')
    entity = models.ForeignKey(entity,null=True,on_delete=models.CASCADE,verbose_name= 'entity')



class StockTransactions(TrackingModel):
    accounthead = models.ForeignKey(to = accountHead, on_delete= models.CASCADE,null=True,blank=True,verbose_name='Account Head',related_name='headtrans')
    account = models.ForeignKey(to = account, on_delete= models.CASCADE,null=True,blank=True,verbose_name='Account Name',related_name='accounttrans')
    stock = models.ForeignKey(to = Product, on_delete= models.CASCADE,null=True,blank=True,verbose_name='Product Name',related_name='stocktrans')
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
    entry = models.ForeignKey(entry,null=True,on_delete=models.CASCADE,related_name='cashtrans')
    entrydate = models.DateField(verbose_name='Entry Date',null=True,blank=True)
    entrydatetime = models.DateTimeField(verbose_name='Entry Date', null=True,blank=True)
    accounttype = models.CharField(max_length=10, null=True,verbose_name='accounttype',blank=True)
    # subtotal =  models.DecimalField(max_digits=14,null = True, decimal_places=4,verbose_name= 'Sub Total')
    pieces = models.IntegerField(verbose_name='Pieces',null=True,blank=True)
    weightqty =  models.DecimalField(max_digits=14,null = True, decimal_places=4,verbose_name= 'Weight Quantity',blank=True)
    iscashtransaction = models.BooleanField(verbose_name='Cash Transaction',default = False)
    isbalancesheet =   models.BooleanField(default=True)
    istrial =   models.BooleanField(default=True)
    entity = models.ForeignKey(entity,on_delete=models.CASCADE,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True)



class goodstransaction(TrackingModel):
    account = models.ForeignKey(to = account, on_delete= models.CASCADE,null=True,blank=True,verbose_name='Account Name',related_name='Goodaccount')
    stock = models.ForeignKey(to = Product, on_delete= models.CASCADE,null=True,blank=True,verbose_name='Product Name', related_name='goods')
    transactiontype = models.CharField(max_length=50, null=True,verbose_name='TransactionType')
    transactionid = models.IntegerField(verbose_name='Transaction id')
    desc = models.CharField(max_length=500, null=True,verbose_name='Description')
    stockttype = models.CharField(verbose_name='Stock Transaction',max_length=10,null=True)
    salequantity =  models.DecimalField(max_digits=14,null = True, decimal_places=4,verbose_name= 'Sale quantity')
    purchasequantity =  models.DecimalField(max_digits=14,null = True, decimal_places=4,verbose_name= 'Purchase quantity')
    issuedquantity =  models.DecimalField(max_digits=14,null = True, decimal_places=4,verbose_name= 'Issued quantity')
    recivedquantity =  models.DecimalField(max_digits=14,null = True, decimal_places=4,verbose_name= 'Received quantity')
    entry = models.ForeignKey(entry,null=True,on_delete=models.CASCADE,related_name='gooddatetrans')
    entrydate = models.DateField(verbose_name='Entry Date',null=True)
    entrydatetime = models.DateTimeField(verbose_name='Entry Date', null=True)
    goodstransactiontype = models.CharField(max_length=50, null=True,verbose_name='Goods TransactionType')
    entity = models.ForeignKey(entity,on_delete=models.CASCADE,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True)





class tdsreturns(TrackingModel):
    tdsreturnname = models.CharField(max_length= 255,verbose_name= 'Tds return')
    tdsreturndesc = models.CharField(max_length= 255,verbose_name= 'Tds return desc')
    # entity = models.ForeignKey(entity,null=True,on_delete=models.CASCADE)
    # createdby = models.ForeignKey(to= User, on_delete= models.CASCADE)


    def __str__(self):
        return f'{self.tdsreturnname}'






class tdstype(TrackingModel):
    tdstypename = models.CharField(max_length= 255,verbose_name= 'Tds Type')
    tdssection = models.CharField(max_length= 255,verbose_name= 'Tds Type Code')
    tdsreturn = models.ForeignKey(tdsreturns,on_delete=models.CASCADE,verbose_name= 'Tds Return',null = True)
    # entity = models.ForeignKey(entity,null=True,on_delete=models.CASCADE)
    # createdby = models.ForeignKey(to= User, on_delete= models.CASCADE)


    def __str__(self):
        return f'{self.tdstypename}'



class tdsmain(TrackingModel):
    voucherdate = models.DateField(verbose_name='Vocucher Date',default=datetime.date.today)
    voucherno = models.IntegerField(verbose_name='Voucher No')
    creditaccountid = models.ForeignKey(to = account, on_delete= models.CASCADE,null=True,blank=True,verbose_name='Credit Account Name',related_name='tdscreditaccount')
    creditdesc = models.CharField(max_length= 255,verbose_name= 'Credit Acc desc',null=True)
    debitaccountid = models.ForeignKey(to = account, on_delete= models.CASCADE,null=True,blank=True,verbose_name='debit Account Name',related_name='tdsdebitaccount')
    debitdesc = models.CharField(max_length= 255,verbose_name= 'Debit Acc desc',null=True)
    tdsaccountid = models.ForeignKey(to = account, on_delete= models.CASCADE,null=True,blank=True,verbose_name='Tds Account Name',related_name='tdsaccount1')
    tdsdesc = models.CharField(max_length= 255,verbose_name= 'Tds Acc desc',null=True)
    tdsreturnccountid = models.ForeignKey(to = tdsreturns, on_delete= models.CASCADE,null=True,blank=True,verbose_name='Tds Account Name',related_name='tdsreturnaccount1')
    tdsreturndesc = models.CharField(max_length= 255,verbose_name= 'tds return Acc desc',null=True)
    tdstype = models.ForeignKey(to = tdstype, on_delete= models.CASCADE,null=True,blank=True,verbose_name='Tds Type',related_name='tdstype')
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
    entityid = models.ForeignKey(entity,null=True,on_delete=models.CASCADE)
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.CASCADE,verbose_name= 'entity Financial year',null= True)
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null = True)


    class Meta:
        unique_together = ('voucherno', 'entityid','entityfinid',)


    def __str__(self):
        return f'{self.voucherno}'


class debitcreditnote(TrackingModel):
    voucherdate = models.DateTimeField(verbose_name='Vocucher Date',null=True)
    voucherno = models.IntegerField(verbose_name='Voucher No')
    debitaccount = models.ForeignKey(to = account, on_delete= models.CASCADE,null=True,blank=True,verbose_name='deditaccount',related_name='dcdebitaccount')
    creditaccount = models.ForeignKey(to = account, on_delete= models.CASCADE,null=True,blank=True,verbose_name='credit account',related_name='dccreditaccount')
    detail = models.CharField(max_length=500, null=True,verbose_name='detail')
    ledgereffect = models.BooleanField(verbose_name='Effect on Ledger')
    product = models.ForeignKey(to = Product, on_delete= models.CASCADE,verbose_name= 'Product',null = True)
    quantity =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'quantity')
    rate =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Rate')
    basicvalue =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Amount')
    cndnamount =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Credit/Debit Note')
    tdssection = models.ForeignKey(to = tdstype, on_delete= models.CASCADE,null=True,blank=True,verbose_name='Tds section')
    vouchertype = models.CharField(max_length=50, null=True,verbose_name='Voucher Type',default='D')
    entity = models.ForeignKey(entity,on_delete=models.CASCADE,verbose_name= 'entity')
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.CASCADE,verbose_name= 'entity Financial year',null= True)
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True)


    #class Meta:
        #unique_together = ('voucherno','vouchertype','entity',)

    def __str__(self):
         return f'{self.voucherno} '
    

class closingstock(TrackingModel):
    stockdate = models.DateTimeField(verbose_name='Stock Date',null=True)
    stock = models.ForeignKey(to = Product, on_delete= models.CASCADE,verbose_name= 'stock Name',null = True)
    closingrate = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Closing Rate')
    entity = models.ForeignKey(entity,on_delete=models.CASCADE,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True)


    #class Meta:
        #unique_together = ('voucherno','vouchertype','entity',)

    def __str__(self):
         return f'{self.stock} '
    


class mastergstdetails(TrackingModel):
    username = models.CharField(max_length=100, null=True,verbose_name='username')
    password = models.CharField(max_length=100, null=True,verbose_name='password')
    client_id = models.CharField(max_length=200, null=True,verbose_name='clientid')
    client_secret = models.CharField(max_length=200, null=True,verbose_name='client_secret')
    gstin = models.CharField(max_length=20, null=True,verbose_name='gstin')

    def __str__(self):
         return f'{self.username}'
    

class supplytype(TrackingModel):
    supplytypecode = models.CharField(max_length=10, null=True,verbose_name='supplytypecode')
    supplytypename = models.CharField(max_length=100, null=True,verbose_name='supplytypename')

    def __str__(self):
         return f'{self.supplytypecode}'








    





    







