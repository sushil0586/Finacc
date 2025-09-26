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
from django.db.models import Sum,Q, CheckConstraint, UniqueConstraint
import datetime
from django.core.exceptions import ValidationError
from django.db.models import Index, Func, DateField, F
from django.db.models.functions import Cast
from geography.models import Country,State,District,City
from simple_history.models import HistoricalRecords
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from decimal import Decimal
ZERO2 = Decimal("0.00")
ZERO4 = Decimal("0.0000")


# Create your models here.


class invoicetypes(TrackingModel):
    invoicetypename = models.CharField(max_length= 255,verbose_name= 'Invoice Type Name')
    invoicetypecode = models.CharField(max_length= 255,verbose_name= 'Invoice Type Code')
   

    def __str__(self):
       # entity_name = self.entity.entityname if self.entity else "NoEntity"
        return f'{self.invoicetypename}-{self.invoicetypecode}'


class modeofpayment(TrackingModel):
    paymentmode = models.CharField(max_length= 255,verbose_name= 'Payment Mode')
    paymentmodecode = models.CharField(max_length= 255,verbose_name= 'Payment mode code')
   

    def __str__(self):
       # entity_name = self.entity.entityname if self.entity else "NoEntity"
        return f'{self.paymentmode}-{self.paymentmodecode}'
    
class transportmode(TrackingModel):
    transmode = models.CharField(max_length= 255,verbose_name= 'Transport Mode')
    transmodecode = models.CharField(max_length= 255,verbose_name= 'Transport mode code')
   

    def __str__(self):
       # entity_name = self.entity.entityname if self.entity else "NoEntity"
        return f'{self.transmode}-{self.transmodecode}'
    
    
class vehicalType(TrackingModel):
    vehicaltype = models.CharField(max_length= 255,verbose_name= 'Vehical Type')
    vehicaltypecode = models.CharField(max_length= 255,verbose_name= 'Vehical type code')
   

    def __str__(self):
       # entity_name = self.entity.entityname if self.entity else "NoEntity"
        return f'{self.vehicaltype}-{self.vehicaltypecode}'


class doctype(TrackingModel):
    docname = models.CharField(max_length= 255,verbose_name= 'Purchase tax type')
    doccode = models.CharField(max_length= 255,verbose_name= 'Purchase tax Code')
    entity = models.ForeignKey(Entity,null=True,on_delete=models.CASCADE)
    createdby = models.ForeignKey(to= User, on_delete=models.CASCADE)

    def __str__(self):
       # entity_name = self.entity.entityname if self.entity else "NoEntity"
        return f'{self.entity}-{self.docname}-{self.doccode}'


class DocumentNumberSettings(models.Model):
    doctype = models.ForeignKey(doctype,null=True,on_delete=models.CASCADE)
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
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.CASCADE,verbose_name= 'entity Financial year',null= True)

class PurchaseSettings(DocumentNumberSettings):
    entity = models.ForeignKey(Entity, on_delete=models.CASCADE)
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.CASCADE,verbose_name= 'entity Financial year',null= True)

class ReceiptSettings(DocumentNumberSettings):
    entity = models.ForeignKey(Entity, on_delete=models.CASCADE)
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.CASCADE,verbose_name= 'entity Financial year',null= True)
    


def validate_file_size(value):
    limit = 1000 * 1024  # 100 KB
    if value.size > limit:
        raise ValidationError('File size should not exceed 100 KB.')

class purchasetaxtype(TrackingModel):
    taxtypename = models.CharField(max_length= 255,verbose_name= 'Purchase tax type')
    taxtypecode = models.CharField(max_length= 255,verbose_name= 'Purchase tax Code')
    entity = models.ForeignKey(Entity,null=True,on_delete=models.CASCADE)
    createdby = models.ForeignKey(to= User, on_delete=models.CASCADE)


    def __str__(self):
        return f'{self.taxtypename} '
    

class InvoiceType(TrackingModel):
    invoicetype = models.CharField(max_length=100, verbose_name='Invoice Type')
    invoicetypecode = models.CharField(max_length=20, verbose_name='Invoice Type Code')
    entity = models.ForeignKey(Entity, null=True, on_delete=models.CASCADE)
    createdby = models.ForeignKey(to=User, on_delete=models.CASCADE)

    def __str__(self):
        return f'{self.invoicetype} '
    

class Paymentmodes(TrackingModel):
    paymentmode = models.CharField(max_length=200, verbose_name='Payment Mode')
    paymentmodecode = models.CharField(max_length=20, verbose_name='Payment Mode Code')
    iscash =   models.BooleanField(default=True,verbose_name='IsCash Transaction')
    createdby = models.ForeignKey(to=User, on_delete=models.CASCADE)

    def __str__(self):
        return f'{self.paymentmode}'
    

    


class defaultvaluesbyentity(TrackingModel):
    taxtype = models.ForeignKey(to=purchasetaxtype, on_delete=models.CASCADE)
    invoicetype = models.ForeignKey(to=InvoiceType, on_delete=models.CASCADE)
    subentity = models.ForeignKey(to=subentity, on_delete=models.CASCADE)
    entity = models.ForeignKey(Entity,null=True,on_delete=models.CASCADE)
   # createdby = models.ForeignKey(to= User, on_delete=models.CASCADE)


    def __str__(self):
        return f'{self.taxtype} - {self.entity}'

        


class gstorderservices(TrackingModel):
    orderdate = models.DateTimeField(verbose_name='Order date',null = True)
    billno = models.IntegerField(verbose_name='Bill No')
    account = models.ForeignKey(to = account, on_delete=models.CASCADE,blank=True)
    taxtype = models.IntegerField(verbose_name='Tax Type')
    billcash = models.IntegerField(verbose_name='Bill/Cash')
    grno = models.CharField(max_length=50,verbose_name='GR No',null=True)
    state       = models.ForeignKey(to=State,on_delete=models.CASCADE,null=True)
    district    = models.ForeignKey(to=District,on_delete=models.CASCADE,null=True)
    city       = models.ForeignKey(to=City,on_delete=models.CASCADE,null=True)
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
    subentity = models.ForeignKey(subentity,on_delete=models.CASCADE,verbose_name= 'subentity',null= True)
    entity = models.ForeignKey(Entity,on_delete=models.CASCADE,verbose_name= 'entity',null= True)
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.CASCADE,verbose_name= 'entity Financial year',null= True)
    createdby = models.ForeignKey(to= User, on_delete=models.CASCADE,null=True)

    class Meta:
        unique_together = ('billno', 'entity','orderType','entityfinid',)

    def __str__(self):
        return f'{self.billno}'


class gstorderservicesdetails(TrackingModel):
    gstorderservices = models.ForeignKey(to = gstorderservices,related_name='gstorderservicesdetails', on_delete=models.CASCADE,verbose_name= 'Gst services Number')
    account = models.ForeignKey(to = account, on_delete=models.CASCADE,blank=True)
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
    subentity = models.ForeignKey(subentity,on_delete=models.CASCADE,verbose_name= 'subentity',null= True)
    entity = models.ForeignKey(Entity,on_delete=models.CASCADE,verbose_name= 'entity')
    #createdby = models.ForeignKey(to= User, on_delete=models.CASCADE,null=True)


    def __str__(self):
        return f'{self.account}'


class gstorderservicesAttachment(models.Model):
    gst_order = models.ForeignKey('gstorderservices', on_delete=models.CASCADE, related_name='gstosattachments')
    file = models.FileField(upload_to='gst_order_attachments/', validators=[validate_file_size])
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Attachment for  {self.gst_order.gst_order}"


    



class SalesOderHeader(TrackingModel):  # keep your base class if TrackingModel; changed to models.Model for snippet only
    # --- Choices for clarity (optional but recommended) ---
    # class TaxType(models.IntegerChoices):
    #     INTRA = 1, "Intra-state (CGST+SGST)"
    #     INTER = 2, "Inter-state (IGST)"

    class BillCash(models.IntegerChoices):
        CREDIT = 1, "Credit"
        CASH   = 2, "Cash"

    class SupplyKind(models.IntegerChoices):
        GOODS    = 1, "Goods"
        SERVICES = 2, "Services"

    # Fields (kept the same names to avoid breaking your code)
    sorderdate     = models.DateTimeField("Sales Order date", null=True)
    billno         = models.IntegerField("Bill No")
    invoicenumber  = models.CharField("Invoice Number", max_length=50, null=True, blank=True)

    accountid      = models.ForeignKey(to=account, on_delete=models.CASCADE, blank=True, null=True)  # allow null
    invoicetypeid  = models.ForeignKey(to=invoicetypes, on_delete=models.CASCADE, blank=True, null=True)

    latepaymentalert = models.BooleanField("Late Payment Alert", default=True, null=True)
    grno           = models.CharField("GR No", max_length=50, null=True, blank=True)
    terms          = models.IntegerField("Terms")
    vehicle        = models.CharField("Vehicle", max_length=50, null=True, blank=True)

    taxtype        = models.IntegerField("Tax Type")
    billcash       = models.IntegerField("Bill/Cash", choices=BillCash.choices)
    supply         = models.IntegerField("Supply", choices=SupplyKind.choices)

    state    = models.ForeignKey(to=State, on_delete=models.CASCADE, null=True, blank=True)
    district = models.ForeignKey(to=District, on_delete=models.CASCADE, null=True, blank=True)
    city     = models.ForeignKey(to=City, on_delete=models.CASCADE, null=True, blank=True)
    pincode  = models.CharField("pincode", max_length=50, null=True, blank=True)

    totalpieces   = models.IntegerField("totalpieces", default=0, blank=True)
    totalquanity  = models.DecimalField("totalquanity", max_digits=14, decimal_places=4, default=ZERO4, blank=True)
    advance       = models.DecimalField("advance", max_digits=14, decimal_places=2, default=ZERO2, blank=True)

    shippedto = models.ForeignKey(to=ShippingDetails, on_delete=models.CASCADE, null=True, related_name='shippedto')
    ecom      = models.ForeignKey(to='financial.account', on_delete=models.CASCADE, null=True, related_name='ecommerce4')

    remarks       = models.CharField("Remarks", max_length=500, null=True, blank=True)
    cancelreason  = models.CharField("Cancelreason", max_length=500, null=True, blank=True)

    transport = models.ForeignKey(account, on_delete=models.CASCADE, null=True, blank=True, related_name='sotransport')
    broker    = models.ForeignKey(account, on_delete=models.CASCADE, null=True, blank=True, related_name='sobroker')

    taxid = models.IntegerField("Terms", default=0)

    # TDS/TCS (left as-is but kept non-null with sane defaults)
    tds194q      = models.DecimalField("TDS 194 @",      max_digits=5,  decimal_places=2, default=ZERO2)
    tds194q1     = models.DecimalField("TDS 194 @",      max_digits=5,  decimal_places=2, default=ZERO2)
    tcs206c1ch1  = models.DecimalField("Tcs 206C1cH1",   max_digits=5,  decimal_places=2, default=ZERO2)
    tcs206c1ch2  = models.DecimalField("Tcs 206C1cH2",   max_digits=5,  decimal_places=2, default=ZERO2)
    tcs206c1ch3  = models.DecimalField("Tcs tcs206c1ch3",max_digits=5,  decimal_places=2, default=ZERO2)
    tcs206C1     = models.DecimalField("Tcs 206C1",      max_digits=5,  decimal_places=2, default=ZERO2)
    tcs206C2     = models.DecimalField("Tcs 206C2",      max_digits=5,  decimal_places=2, default=ZERO2)

    duedate = models.DateField("Due Date", null=True)

    # Monetary/tax fields → non-null with defaults
    totalgst      = models.DecimalField("totalgst", max_digits=14, decimal_places=2, default=ZERO2)
    stbefdiscount = models.DecimalField("Sub Total before Discount", max_digits=14, decimal_places=2, default=ZERO2)
    discount      = models.DecimalField("Discount", max_digits=14, decimal_places=2, default=ZERO2)
    subtotal      = models.DecimalField("Sub Total", max_digits=14, decimal_places=2, default=ZERO2)
    addless       = models.DecimalField("Add/Less", max_digits=14, decimal_places=2, default=ZERO2)

    apptaxrate    = models.DecimalField("app tax rate", max_digits=5, decimal_places=2, default=ZERO2)

    cgst          = models.DecimalField("C.GST", max_digits=14, decimal_places=2, default=ZERO2)
    sgst          = models.DecimalField("S.GST", max_digits=14, decimal_places=2, default=ZERO2)
    igst          = models.DecimalField("I.GST", max_digits=14, decimal_places=2, default=ZERO2)
    isigst        = models.BooleanField("IsIgst", default=False)

    invoicetype   = models.ForeignKey(InvoiceType, on_delete=models.CASCADE, null=True, verbose_name='Invoice Type')
    reversecharge = models.BooleanField("Reverse charge", default=False)

    cess     = models.DecimalField("Cess", max_digits=14, decimal_places=2, default=ZERO2)
    expenses = models.DecimalField("EXpenses", max_digits=14, decimal_places=2, default=ZERO2)
    gtotal   = models.DecimalField("Grand Total", max_digits=14, decimal_places=2, default=ZERO2)
    roundOff = models.DecimalField("Raw Grand Total", max_digits=14, decimal_places=2, default=ZERO2)

    subentity   = models.ForeignKey(subentity, on_delete=models.CASCADE, null=True, verbose_name='subentity')
    entity      = models.ForeignKey(Entity, on_delete=models.CASCADE, null=True, verbose_name='entity')
    entityfinid = models.ForeignKey(entityfinancialyear, on_delete=models.CASCADE, null=True, verbose_name='entity Financial year')

    eway             = models.BooleanField(default=False)
    einvoice         = models.BooleanField(default=False)
    einvoicepluseway = models.BooleanField(default=False)
    isammended       = models.BooleanField(default=False)
    isadditionaldetail = models.BooleanField("Is Additional details", default=False)

    originalinvoice = models.ForeignKey("self", null=True, on_delete=models.CASCADE, verbose_name='Orinial invoice')
    createdby       = models.ForeignKey(to=User, on_delete=models.CASCADE, null=True)

    history = HistoricalRecords()

    class Meta:
        constraints = [
            UniqueConstraint(fields=("billno", "entity", "entityfinid"), name="uq_billno_entity_fin"),

            # IGST vs CGST/SGST mutual exclusivity:
            # - if isigst=True  → cgst=0 and sgst=0 (allow igst 0 for zero-rated)
            # - if isigst=False → igst=0
            CheckConstraint(
                name="ck_igst_vs_cgst_sgst_hdr",
                check=(Q(isigst=True) & Q(cgst=0) & Q(sgst=0)) | (Q(isigst=False) & Q(igst=0)),
            ),

            # Non-negative header money amounts
            CheckConstraint(
                name="ck_header_amounts_nonneg",
                check=(
                    Q(cgst__gte=0) & Q(sgst__gte=0) & Q(igst__gte=0) & Q(cess__gte=0) &
                    Q(stbefdiscount__gte=0) & Q(discount__gte=0) & Q(subtotal__gte=0) &
                    Q(totalgst__gte=0) & Q(expenses__gte=0) & Q(addless__gte=0) &
                    Q(advance__gte=0) & Q(gtotal__gte=0)
                ),
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "entityfinid", "billno"], name="ix_entity_fin_bill"),
            models.Index(fields=["invoicenumber"], name="ix_invoice_no"),
            models.Index(fields=["sorderdate"], name="ix_order_date"),
            models.Index(fields=["accountid"], name="ix_customer"),
        ]

    def __str__(self):
        return f"{self.billno}"


class salesOrderdetails(TrackingModel):  # keep your base class if TrackingModel
    salesorderheader = models.ForeignKey(to=SalesOderHeader, related_name='saleInvoiceDetails',
                                         on_delete=models.CASCADE, verbose_name='Sale Order Number')
    product     = models.ForeignKey(to=Product, on_delete=models.CASCADE, verbose_name='Product', null=True, blank=True)
    productdesc = models.CharField("product Desc", max_length=500, null=True, blank=True)

    orderqty = models.DecimalField("Order Qty", max_digits=14, decimal_places=4, default=ZERO4)
    pieces   = models.IntegerField("pieces", default=0)

    befDiscountProductAmount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    ratebefdiscount          = models.DecimalField("ratebefdiscount", max_digits=14, decimal_places=2, default=ZERO2)

    orderDiscount      = models.DecimalField("Discount", max_digits=14, decimal_places=2, default=ZERO2)
    orderDiscountValue = models.DecimalField("Discount", max_digits=14, decimal_places=2, default=ZERO2)

    rate   = models.DecimalField("Rate", max_digits=14, decimal_places=2, default=ZERO2)
    amount = models.DecimalField("Amount", max_digits=14, decimal_places=2, default=ZERO2)

    othercharges = models.DecimalField("other charges", max_digits=14, decimal_places=2, default=ZERO2, null=True, blank=True)

    cgst  = models.DecimalField("CGST", max_digits=14, decimal_places=2, default=ZERO2)
    sgst  = models.DecimalField("SGST", max_digits=14, decimal_places=2, default=ZERO2)
    igst  = models.DecimalField("IGST", max_digits=14, decimal_places=2, default=ZERO2)
    isigst = models.BooleanField(default=False)

    # percents as 5,2
    cgstpercent = models.DecimalField("CGST Percent", max_digits=5, decimal_places=2, default=ZERO2)
    sgstpercent = models.DecimalField("SGST Percent", max_digits=5, decimal_places=2, default=ZERO2)
    igstpercent = models.DecimalField("IGST Percent", max_digits=5, decimal_places=2, default=ZERO2)

    cess      = models.DecimalField("Cess", max_digits=14, decimal_places=2, default=ZERO2)
    linetotal = models.DecimalField("Line Total", max_digits=14, decimal_places=2, default=ZERO2)

    isService = models.BooleanField("Is Service", default=False)

    subentity = models.ForeignKey(subentity, on_delete=models.CASCADE, null=True, verbose_name='subentity')
    entity    = models.ForeignKey(Entity, on_delete=models.CASCADE, verbose_name='entity')
    createdby = models.ForeignKey(to=User, on_delete=models.CASCADE, null=True)

    history = HistoricalRecords()

    class Meta:
        constraints = [
            # Detail-level IGST vs CGST/SGST exclusivity
            CheckConstraint(
                name="ck_igst_vs_cgst_sgst_dtl",
                check=(Q(isigst=True) & Q(cgst=0) & Q(sgst=0)) | (Q(isigst=False) & Q(igst=0)),
            ),
            # Non-negative amounts and percent range 0..100
            CheckConstraint(
                name="ck_detail_amounts_nonneg",
                check=Q(cgst__gte=0) & Q(sgst__gte=0) & Q(igst__gte=0) & Q(cess__gte=0) &
                      Q(amount__gte=0) & Q(linetotal__gte=0) & Q(orderqty__gte=0) & Q(pieces__gte=0),
            ),
            CheckConstraint(
                name="ck_detail_percent_bounds",
                check=(Q(cgstpercent__gte=0) & Q(cgstpercent__lte=100) &
                       Q(sgstpercent__gte=0) & Q(sgstpercent__lte=100) &
                       Q(igstpercent__gte=0) & Q(igstpercent__lte=100)),
            ),
        ]
        indexes = [
            models.Index(fields=["salesorderheader"], name="ix_detail_header"),
            models.Index(fields=["product"], name="ix_detail_product"),
        ]

    def __str__(self):
        return f"{self.product or self.productdesc or '#'}"
    






class EInvoiceDetails(models.Model):
    # Generic relation to any invoice-like model (SalesOderHeader, CreditNote, etc.)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    document = GenericForeignKey('content_type', 'object_id')

    irn = models.CharField(max_length=100, unique=True)
    ack_no = models.BigIntegerField()
    ack_date = models.DateTimeField()
    signed_invoice = models.TextField()
    signed_qr_code = models.TextField()
    status = models.CharField(max_length=20, default='ACT')

    ewb_no = models.BigIntegerField(null=True, blank=True)
    ewb_date = models.DateTimeField(null=True, blank=True)
    ewb_valid_till = models.DateTimeField(null=True, blank=True)
    remarks = models.TextField(null=True, blank=True)
    cancelleddate =  models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('content_type', 'object_id')  # Prevent duplicates per document
      
    
class SalesOder(TrackingModel):
    #RevisonNumber =models.IntegerFieldverbose_name=_('Main category'))
    sorderdate = models.DateTimeField(verbose_name='Sales Order date',null = True)
    billno = models.IntegerField(verbose_name='Bill No')
    accountid = models.ForeignKey(to = account, on_delete=models.CASCADE,blank=True)
    latepaymentalert = models.BooleanField(verbose_name='Late Payment Alert',default = True,null = True)
    grno = models.CharField(max_length=50,verbose_name='GR No',null=True)
    terms = models.IntegerField(verbose_name='Terms')
    vehicle = models.CharField(max_length=50, null=True,verbose_name='Vehicle')
    taxtype = models.IntegerField(verbose_name='Tax Type')
    billcash = models.IntegerField(verbose_name='Bill/Cash')
    supply = models.IntegerField(verbose_name='Supply')
    state       = models.ForeignKey(to=State,on_delete=models.CASCADE,null=True)
    district    = models.ForeignKey(to=District,on_delete=models.CASCADE,null=True)
    city       = models.ForeignKey(to=City,on_delete=models.CASCADE,null=True)
    pincode = models.CharField(max_length=50,verbose_name='pincode',null=True)
    totalpieces = models.IntegerField(verbose_name='totalpieces',default=0,blank = True)
    totalquanity =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,blank = True,verbose_name= 'totalquanity')
    advance =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,blank = True,verbose_name= 'advance')
    shippedto =  models.ForeignKey(to = ShippingDetails, on_delete=models.CASCADE,null=True,related_name='soshippedto')
    remarks = models.CharField(max_length=500, null=True,verbose_name= 'Remarks')
    transport =  models.ForeignKey(account, on_delete=models.CASCADE,null=True,related_name='stransport')
    broker =  models.ForeignKey(account, on_delete=models.CASCADE,null=True,related_name='sbroker')
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
    subentity = models.ForeignKey(subentity,on_delete=models.CASCADE,verbose_name= 'subentity',null= True)
    entity = models.ForeignKey(Entity,on_delete=models.CASCADE,verbose_name= 'entity',null= True)
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.CASCADE,verbose_name= 'entity Financial year',null= True)
    createdby = models.ForeignKey(to= User, on_delete=models.CASCADE,null=True)

    class Meta:
        unique_together = ('billno', 'entity','entityfinid',)


    def __str__(self):
        return f'{self.billno} '

class salesOrderdetail(TrackingModel):
    salesorderheader = models.ForeignKey(to = SalesOder,related_name='salesOrderDetail', on_delete=models.CASCADE,verbose_name= 'Sale Order Number')
    product = models.ForeignKey(to = Product, on_delete=models.CASCADE,verbose_name= 'Product',null = True)
    productdesc = models.CharField(max_length=500, null=True,verbose_name='product Desc')
    orderqty =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Order Qty')
    pieces =  models.IntegerField(verbose_name='pieces')
    rate =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Rate')
    amount =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Amount')
   # account   = models.ForeignKey(to = account, on_delete=models.CASCADE,blank=True,null=True,verbose_name= 'Other account')
    othercharges =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'other charges',default=0,null=True)
    cgst =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'CGST')
    sgst =  models.DecimalField(max_digits=14,null = True, decimal_places=4,verbose_name= 'SGST')
    igst =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'IGST')
    # cgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'C.GST Cess',default=0)
    # sgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'S.GST Cess',default=0)
    cess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Cess',default=0)
    linetotal =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Line Total')
    subentity = models.ForeignKey(subentity,on_delete=models.CASCADE,verbose_name= 'subentity',null= True)
    entity = models.ForeignKey(Entity,on_delete=models.CASCADE,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete=models.CASCADE,null=True)


    def __str__(self):
        return f'{self.product} '
    
class saleothercharges(TrackingModel):
    salesorderdetail = models.ForeignKey(to = salesOrderdetails,related_name='otherchargesdetail', on_delete=models.CASCADE,verbose_name= 'Sale Order Number',null=True)
    account = models.ForeignKey(to = account, on_delete=models.CASCADE,null = True,)
    amount =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'amount')


    def __str__(self):
        return f'{self.salesorderdetail}'
    







    




class PurchaseReturn(TrackingModel):
    #RevisonNumber =models.IntegerFieldverbose_name=_('Main category'))
    sorderdate = models.DateTimeField(verbose_name='Sales Order date',null = True)
    billno = models.IntegerField(verbose_name='Bill No')
    invoicenumber = models.CharField(max_length=50, null=True,verbose_name='Invoice Number')
    accountid = models.ForeignKey(to = account, on_delete=models.CASCADE,blank=True)
    latepaymentalert = models.BooleanField(verbose_name='Late Payment Alert',default = True,null = True)
    grno = models.CharField(max_length=50,verbose_name='GR No',null=True)
    terms = models.IntegerField(verbose_name='Terms')
    vehicle = models.CharField(max_length=50, null=True,verbose_name='Vehicle')
    taxtype = models.IntegerField(verbose_name='Tax Type')
    billcash = models.IntegerField(verbose_name='Bill/Cash')
    supply = models.IntegerField(verbose_name='Supply')
    state       = models.ForeignKey(to=State,on_delete=models.CASCADE,null=True)
    district    = models.ForeignKey(to=District,on_delete=models.CASCADE,null=True)
    city       = models.ForeignKey(to=City,on_delete=models.CASCADE,null=True)
    pincode = models.CharField(max_length=50,verbose_name='pincode',null=True)
    totalpieces = models.IntegerField(verbose_name='totalpieces',default=0,blank = True)
    totalquanity =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,blank = True,verbose_name= 'totalquanity')
    advance =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,blank = True,verbose_name= 'advance')
    shippedto =  models.ForeignKey(to = ShippingDetails, on_delete=models.CASCADE,null=True,related_name='shippedto1')
    remarks = models.CharField(max_length=500, null=True,verbose_name= 'Remarks')
    transport =  models.ForeignKey(to = account, on_delete=models.CASCADE,null=True,related_name='transport1')
    broker =  models.ForeignKey(to = account, on_delete=models.CASCADE,null=True,related_name='broker1')
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
    invoicetype = models.ForeignKey(InvoiceType,on_delete=models.CASCADE,verbose_name= 'Invoice Type',null= True)
    reversecharge =   models.BooleanField(default=False,verbose_name= 'Reverse charge')
    ecom =  models.ForeignKey(to = 'financial.account', on_delete=models.CASCADE,null=True,related_name='ecommerce2')
    # cgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'C.GST Cess',default=0)
    # sgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'S.GST Cess',default=0)
    cess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Cess',default=0)
    expenses =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'EXpenses')
    gtotal =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'Grand Total')
    roundOff =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'Raw Grand Total')
    isammended =   models.BooleanField(default=False)
    originalinvoice = models.ForeignKey("self",null=True,on_delete=models.CASCADE,verbose_name='Orinial invoice',blank=True)
    subentity = models.ForeignKey(subentity,on_delete=models.CASCADE,verbose_name= 'subentity',null= True)
    entity = models.ForeignKey(Entity,on_delete=models.CASCADE,verbose_name= 'entity',null= True)
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.CASCADE,verbose_name= 'entity Financial year',null= True)
    createdby = models.ForeignKey(to= User, on_delete=models.CASCADE,null=True)

    # class Meta:
    #     #unique_together = ('billno', 'entity',)


    def __str__(self):
        return f'{self.billno} '

class Purchasereturndetails(TrackingModel):
    purchasereturn = models.ForeignKey(to = PurchaseReturn,related_name='purchasereturndetails', on_delete=models.CASCADE,verbose_name= 'Sale Order Number')
    product = models.ForeignKey(to = Product, on_delete=models.CASCADE,verbose_name= 'Product',null = True)
    productdesc = models.CharField(max_length=500, null=True,verbose_name='product Desc')
    orderqty =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Order Qty')
    pieces =  models.IntegerField(verbose_name='pieces')
    rate =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Rate')
    amount =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Amount')
    #account   = models.ForeignKey(to = account, on_delete=models.CASCADE,blank=True,null=True,verbose_name= 'Other account')
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
    subentity = models.ForeignKey(subentity,on_delete=models.CASCADE,verbose_name= 'subentity',null= True)
    entity = models.ForeignKey(Entity,on_delete=models.CASCADE,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete=models.CASCADE,null=True)


    def __str__(self):
        return f'{self.product} '
    

class Purchasereturnothercharges(TrackingModel):
    purchasereturnorderdetail = models.ForeignKey(to = Purchasereturndetails,related_name='otherchargesdetail', on_delete=models.CASCADE,verbose_name= 'Sale Order Number',null=True)
    account = models.ForeignKey(to = account, on_delete=models.CASCADE,null = True,)
    amount =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'amount')


    def __str__(self):
        return f'{self.purchasereturnorderdetail}'
    

class jobworkchalan(TrackingModel):
    voucherdate = models.DateField(verbose_name='Vocucher Date',auto_now_add=True)
    voucherno = models.IntegerField(verbose_name='Voucher No')
    account = models.ForeignKey(to = account, on_delete=models.CASCADE,null=True,blank=True)
    billno = models.IntegerField(verbose_name='Bill No')
    billdate = models.DateTimeField(verbose_name='Bill Date',null = True)
    terms = models.IntegerField(verbose_name='Terms')
    taxtype = models.IntegerField(verbose_name='TaxType')
    billcash = models.IntegerField(verbose_name='Bill/Cash')
    state       = models.ForeignKey(to=State,on_delete=models.CASCADE,null=True)
    district    = models.ForeignKey(to=District,on_delete=models.CASCADE,null=True)
    city       = models.ForeignKey(to=City,on_delete=models.CASCADE,null=True)
    pincode = models.CharField(max_length=50,verbose_name='pincode',null=True)
    totalpieces = models.IntegerField(verbose_name='totalpieces',default=0,blank = True)
    totalquanity =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,blank = True,verbose_name= 'totalquanity')
    advance =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,blank = True,verbose_name= 'advance')
    remarks = models.CharField(max_length=500, null=True,verbose_name= 'Remarks')
    transport =  models.ForeignKey(to = 'financial.account', on_delete=models.CASCADE,null=True,related_name='jwtransport')
    broker =  models.ForeignKey(to = 'financial.account', on_delete=models.CASCADE,null=True,related_name='jwbroker')
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
    entity = models.ForeignKey(Entity,on_delete=models.CASCADE,verbose_name= 'entity')
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.CASCADE,verbose_name= 'entity Financial year',null= True)
    createdby = models.ForeignKey(to= User, on_delete=models.CASCADE,null=True)


    class Meta:
        unique_together = ('voucherno', 'entity',)
        unique_together = ('billno', 'account','entity','ordertype','entityfinid',)
        

    def __str__(self):
        return f'{self.voucherno} '

class jobworkchalanDetails(models.Model):
    jobworkchalan = models.ForeignKey(to = jobworkchalan,related_name='jobworkchalanDetails', on_delete=models.CASCADE,verbose_name= 'Purchase Order Number')
    product = models.ForeignKey(to = Product, on_delete=models.CASCADE,verbose_name= 'Product',null = True)
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
    subentity = models.ForeignKey(subentity,on_delete=models.CASCADE,verbose_name= 'subentity',null= True)
    
    entity = models.ForeignKey(Entity,on_delete=models.CASCADE,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete=models.CASCADE,null=True)


class purchaseorderimport(TrackingModel):
    voucherdate = models.DateField(verbose_name='Vocucher Date',auto_now_add=True)
    voucherno = models.IntegerField(verbose_name='Voucher No')
    account = models.ForeignKey(to = account, on_delete=models.CASCADE,null=True,blank=True)
    billno = models.IntegerField(verbose_name='Bill No')
    billdate = models.DateTimeField(verbose_name='Bill Date',null = True)
    terms = models.IntegerField(verbose_name='Terms')
    taxtype = models.IntegerField(verbose_name='TaxType')
    billcash = models.IntegerField(verbose_name='Bill/Cash')
    state       = models.ForeignKey(to=State,on_delete=models.CASCADE,null=True)
    district    = models.ForeignKey(to=District,on_delete=models.CASCADE,null=True)
    city       = models.ForeignKey(to=City,on_delete=models.CASCADE,null=True)
    pincode = models.CharField(max_length=50,verbose_name='pincode',null=True)
    totalpieces = models.IntegerField(verbose_name='totalpieces',default=0,blank = True)
    totalquanity =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,blank = True,verbose_name= 'totalquanity')
    advance =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,blank = True,verbose_name= 'advance')
    remarks = models.CharField(max_length=500, null=True,verbose_name= 'Remarks')
    transport =  models.ForeignKey(to = 'financial.account', on_delete=models.CASCADE,null=True,related_name='sitransport')
    broker =  models.ForeignKey(to = 'financial.account', on_delete=models.CASCADE,null=True,related_name='sibroker')
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
    entity = models.ForeignKey(Entity,on_delete=models.CASCADE,verbose_name= 'entity')
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.CASCADE,verbose_name= 'entity Financial year',null= True)
    createdby = models.ForeignKey(to= User, on_delete=models.CASCADE,null=True)


    class Meta:
        unique_together = ('voucherno', 'entity',)
        unique_together = ('billno', 'account','entity','entityfinid',)
        

    def __str__(self):
        return f'{self.voucherno}'
    


class PurchaseOrderimportdetails(models.Model):
    purchaseorder = models.ForeignKey(to = purchaseorderimport,related_name='PurchaseOrderimportdetails', on_delete=models.CASCADE,verbose_name= 'Purchase Order Number')
    product = models.ForeignKey(to = Product, on_delete=models.CASCADE,verbose_name= 'Product',null = True)
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
    entity = models.ForeignKey(Entity,on_delete=models.CASCADE,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete=models.CASCADE,null=True)



class purchaseotherimportcharges(TrackingModel):
    purchaseorderdetail = models.ForeignKey(to = PurchaseOrderimportdetails,related_name='otherchargesdetail', on_delete=models.CASCADE,verbose_name= 'Purchase Order detail',null=True)
    account = models.ForeignKey(to = account, on_delete=models.CASCADE,null = True,)
    amount =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'amount')


    def __str__(self):
        return f'{self.purchaseorderdetail}'
    

class purchaseotherimporAttachment(models.Model):
    purchase_order_import = models.ForeignKey('purchaseorderimport', on_delete=models.CASCADE, related_name='piattachments')
    file = models.FileField(upload_to='purchase_order_import_attachments/', validators=[validate_file_size])
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Attachment for PO {self.purchase_order_import.voucherno}"
    





    



class purchaseorder(TrackingModel):  # keep name to avoid breaking references
    voucherdate   = models.DateField(verbose_name='Voucher Date', auto_now_add=True)
    voucherno     = models.IntegerField(verbose_name='Voucher No')
    account       = models.ForeignKey('financial.account', on_delete=models.CASCADE, null=True, blank=True)

    billno        = models.IntegerField(verbose_name='Bill No')
    billdate      = models.DateTimeField(verbose_name='Bill Date', null=True)
    terms         = models.IntegerField(verbose_name='Terms')
    taxtype       = models.IntegerField(verbose_name='TaxType')
    billcash      = models.IntegerField(verbose_name='Bill/Cash')  # 0/2=cash, others=credit (to match legacy)

    # Location
    state         = models.ForeignKey(State,    on_delete=models.CASCADE, null=True)
    district      = models.ForeignKey(District, on_delete=models.CASCADE, null=True)
    city          = models.ForeignKey(City,     on_delete=models.CASCADE, null=True)
    pincode       = models.CharField(max_length=50, verbose_name='pincode', null=True)

    # Totals helpers
    totalpieces   = models.IntegerField(verbose_name='totalpieces', default=0, blank=True)
    totalquanity  = models.DecimalField(max_digits=14, decimal_places=4, default=ZERO4, blank=True, verbose_name='totalquanity')
    advance       = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2, blank=True, verbose_name='advance')

    remarks       = models.CharField(max_length=500, null=True, verbose_name='Remarks')
    transport     = models.ForeignKey('financial.account', on_delete=models.CASCADE, null=True, related_name='potransport')
    broker        = models.ForeignKey('financial.account', on_delete=models.CASCADE, null=True, related_name='pobroker')

    taxid         = models.IntegerField(verbose_name='Terms', default=0)
    tds194q       = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2, verbose_name='TDS 194 @')
    tds194q1      = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2, verbose_name='TDS 194 @')
    tcs206c1ch1   = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2, verbose_name='Tcs 206C1cH1')
    tcs206c1ch2   = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2, verbose_name='Tcs 206C1cH2')
    tcs206c1ch3   = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2, verbose_name='Tcs tcs206c1ch3')
    tcs206C1      = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2, verbose_name='Tcs 206C1')
    tcs206C2      = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2, verbose_name='Tcs 206C2')

    duedate       = models.DateField(verbose_name='Due Date', null=True)  # align with sales
    inputdate     = models.DateTimeField(verbose_name='Input Date', null=True)
    vehicle       = models.CharField(max_length=50, null=True, verbose_name='Vehicle')
    invoicetype   = models.ForeignKey(InvoiceType, on_delete=models.CASCADE, verbose_name='Invoice Type', null=True)
    reversecharge = models.BooleanField(default=False, verbose_name='Reverse charge')
    grno          = models.CharField(max_length=50, null=True, verbose_name='GR No')

    gstr2astatus      = models.BooleanField(verbose_name='GstR 2A Status', default=True)
    showledgeraccount = models.BooleanField(verbose_name='Show Ledger Account', default=True)

    # ---- Computed & monetary (2dp) | quantities 4dp ----
    stbefdiscount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2, verbose_name='Sub Total before Discount')
    discount      = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2, verbose_name='Discount')

    subtotal      = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2, verbose_name='Sub Total')
    addless       = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2, verbose_name='Add/Less')

    cgst          = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2, null=True, verbose_name='C.GST')
    sgst          = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2, null=True, verbose_name='S.GST')
    igst          = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2, null=True, verbose_name='I.GST')
    cess          = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2, verbose_name='Cess')
    totalgst      = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2, null=True, verbose_name='totalgst')

    expenses      = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2, verbose_name='Expenses')
    gtotal        = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2, verbose_name='G Total')
    roundOff      = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2, verbose_name='round off')
    finalAmount   = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2, verbose_name='Final amount')

    subentity     = models.ForeignKey(subentity, on_delete=models.CASCADE, verbose_name='subentity', null=True)
    entity        = models.ForeignKey(Entity, on_delete=models.CASCADE, verbose_name='entity')
    entityfinid   = models.ForeignKey(entityfinancialyear, on_delete=models.CASCADE, verbose_name='entity Financial year', null=True)

    isactive      = models.BooleanField(default=True)
    createdby     = models.ForeignKey(User, on_delete=models.CASCADE, null=True)

    history       = HistoricalRecords()

    class Meta:
        db_table = "purchaseorder"
        constraints = [
            models.UniqueConstraint(fields=['voucherno', 'entity', 'entityfinid'], name='uq_po_voucherno_entity_fin'),
            models.UniqueConstraint(fields=['billno', 'account', 'entity', 'entityfinid'], name='uq_po_billno_party_entity_fin'),
            models.CheckConstraint(
                name='ck_po_nonneg',
                check=(
                    Q(subtotal__gte=0) & Q(cgst__gte=0) & Q(sgst__gte=0) & Q(igst__gte=0) &
                    Q(cess__gte=0) & Q(expenses__gte=0) & Q(gtotal__gte=0)
                )
            ),
        ]
        indexes = [
            models.Index(fields=['entity', 'voucherno'], name='ix_po_entity_vno'),
            models.Index(fields=['entity', 'billno'],    name='ix_po_entity_bno'),
            models.Index(fields=['entity', 'account'],   name='ix_po_entity_party'),
        ]

    def __str__(self):
        return f'PO {self.voucherno} · {self.entity_id}'


class PurchaseOrderDetails(TrackingModel):
    purchaseorder = models.ForeignKey(
        purchaseorder, related_name='purchaseInvoiceDetails',
        on_delete=models.CASCADE, verbose_name='Purchase Order Number'
    )
    product       = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name='Product', null=True)
    productdesc   = models.CharField(max_length=500, null=True, verbose_name='Product Desc')

    # Qty/price
    orderqty      = models.DecimalField(max_digits=14, decimal_places=4, verbose_name='Order Qty')
    pieces        = models.IntegerField(verbose_name='pieces', default=0)
    rate          = models.DecimalField(max_digits=14, decimal_places=2, verbose_name='Rate')    # 2dp like sales
    amount        = models.DecimalField(max_digits=14, decimal_places=2, verbose_name='Amount')

    # Optional “before-discount” fields for parity with sales (safe defaults)
    befDiscountProductAmount = models.DecimalField(max_digits=14, decimal_places=2, null=True, verbose_name='befDiscountProductAmount')
    ratebefdiscount          = models.DecimalField(max_digits=14, decimal_places=2, null=True, verbose_name='ratebefdiscount')
    orderDiscount            = models.DecimalField(max_digits=14, decimal_places=2, null=True, verbose_name='Discount')
    orderDiscountValue       = models.DecimalField(max_digits=14, decimal_places=2, null=True, verbose_name='Discount Value')

    # Taxes (2dp)
    cgst          = models.DecimalField(max_digits=14, decimal_places=2, null=True, verbose_name='CGST', default=ZERO2)
    sgst          = models.DecimalField(max_digits=14, decimal_places=2, null=True, verbose_name='SGST', default=ZERO2)
    igst          = models.DecimalField(max_digits=14, decimal_places=2, null=True, verbose_name='IGST', default=ZERO2)
    isigst        = models.BooleanField(default=False)

    cgstpercent   = models.DecimalField(max_digits=14, decimal_places=2, null=True, verbose_name='CGST percent')
    sgstpercent   = models.DecimalField(max_digits=14, decimal_places=2, null=True, verbose_name='SGST percent')
    igstpercent   = models.DecimalField(max_digits=14, decimal_places=2, null=True, verbose_name='IGST percent')

    othercharges  = models.DecimalField(max_digits=14, decimal_places=2, null=True, default=ZERO2, verbose_name='other charges')
    cess          = models.DecimalField(max_digits=14, decimal_places=2, verbose_name='Cess', default=ZERO2)

    linetotal     = models.DecimalField(max_digits=14, decimal_places=2, verbose_name='Line Total')

    subentity     = models.ForeignKey(subentity, on_delete=models.CASCADE, verbose_name='subentity', null=True)
    entity        = models.ForeignKey(Entity, on_delete=models.CASCADE, verbose_name='entity')
    createdby     = models.ForeignKey(User, on_delete=models.CASCADE, null=True)

    history       = HistoricalRecords()

    class Meta:
        db_table = "purchaseorderdetails"
        constraints = [
            # IGST vs CGST/SGST validity
            models.CheckConstraint(
                name="ck_po_line_tax_combo",
                check=(
                    Q(isigst=True,  cgst=0, sgst=0) |
                    Q(isigst=False, igst=0)
                ),
            ),
            # Non-negative guards
            models.CheckConstraint(
                name="ck_po_line_nonneg",
                check=(
                    Q(orderqty__gte=0) & Q(pieces__gte=0) &
                    Q(rate__gte=0) & Q(amount__gte=0) &
                    Q(cgst__gte=0) & Q(sgst__gte=0) & Q(igst__gte=0) &
                    Q(cess__gte=0) & Q(othercharges__gte=0) &
                    Q(linetotal__gte=0)
                ),
            ),
        ]
        indexes = [
            models.Index(fields=['purchaseorder'], name='ix_pod_hdr'),
            models.Index(fields=['entity', 'product'], name='ix_pod_entity_product'),
            models.Index(fields=['isigst'], name='ix_pod_isigst'),
        ]

    def __str__(self):
        return f'{self.product} · {self.purchaseorder_id}'



class purchaseothercharges(TrackingModel):
    purchaseorderdetail = models.ForeignKey(to = PurchaseOrderDetails,related_name='otherchargesdetail', on_delete=models.CASCADE,verbose_name= 'Purchase Order detail',null=True)
    account = models.ForeignKey(to = account, on_delete=models.CASCADE,null = True,)
    amount =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'amount')


    def __str__(self):
        return f'{self.purchaseorderdetail}'
    


class PurchaseOrderAttachment(models.Model):
    purchase_order = models.ForeignKey('purchaseorder', on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='purchase_order_attachments/', validators=[validate_file_size])
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Attachment for PO {self.purchase_order.voucherno}"


class newpurchaseorder(TrackingModel):
    voucherdate = models.DateField(verbose_name='Vocucher Date',auto_now_add=True)
    voucherno = models.IntegerField(verbose_name='Voucher No')
    account = models.ForeignKey(to = account, on_delete=models.CASCADE,null=True,blank=True)
    billno = models.IntegerField(verbose_name='Bill No')
    billdate = models.DateTimeField(verbose_name='Bill Date',null = True)
    terms = models.IntegerField(verbose_name='Terms')
    taxtype = models.IntegerField(verbose_name='TaxType')
    billcash = models.IntegerField(verbose_name='Bill/Cash')
    state       = models.ForeignKey(to=State,on_delete=models.CASCADE,null=True)
    district    = models.ForeignKey(to=District,on_delete=models.CASCADE,null=True)
    city       = models.ForeignKey(to=City,on_delete=models.CASCADE,null=True)
    pincode = models.CharField(max_length=50,verbose_name='pincode',null=True)
    totalpieces = models.IntegerField(verbose_name='totalpieces',default=0,blank = True)
    totalquanity =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,blank = True,verbose_name= 'totalquanity')
    advance =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,blank = True,verbose_name= 'advance')
    remarks = models.CharField(max_length=500, null=True,verbose_name= 'Remarks')
    transport =  models.IntegerField(verbose_name='transport',null = True)
    transport =  models.ForeignKey(to = 'financial.account', on_delete=models.CASCADE,null=True,related_name='nptransport')
    broker =  models.ForeignKey(to = 'financial.account', on_delete=models.CASCADE,null=True,related_name='npbroker')
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
    entity = models.ForeignKey(Entity,on_delete=models.CASCADE,verbose_name= 'entity')
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.CASCADE,verbose_name= 'entity Financial year',null= True)
    createdby = models.ForeignKey(to= User, on_delete=models.CASCADE,null=True)


    class Meta:
        unique_together = ('voucherno', 'entity',)
        unique_together = ('billno', 'account','entity','entityfinid',)
        

    def __str__(self):
        return f'{self.voucherno} '
    
class newPurchaseOrderDetails(models.Model):
    purchaseorder = models.ForeignKey(to = newpurchaseorder,related_name='purchaseorderdetails', on_delete=models.CASCADE,verbose_name= 'Purchase Order Number')
    product = models.ForeignKey(to = Product, on_delete=models.CASCADE,verbose_name= 'Product',null = True)
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
    subentity = models.ForeignKey(subentity,on_delete=models.CASCADE,verbose_name= 'subentity',null= True)
    entity = models.ForeignKey(Entity,on_delete=models.CASCADE,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete=models.CASCADE,null=True)


class salereturn(TrackingModel):
    voucherdate = models.DateField(verbose_name='Vocucher Date',auto_now_add=True)
    voucherno = models.IntegerField(verbose_name='Voucher No')
    invoicenumber = models.CharField(max_length=50, null=True,verbose_name='Invoice Number')
    account = models.ForeignKey(to = account, on_delete=models.CASCADE,null=True,blank=True)
    billno = models.IntegerField(verbose_name='Bill No')
    billdate = models.DateTimeField(verbose_name='Bill Date',null = True)
    terms = models.IntegerField(verbose_name='Terms')
    taxtype = models.IntegerField(verbose_name='TaxType')
    billcash = models.IntegerField(verbose_name='Bill/Cash')
    state       = models.ForeignKey(to=State,on_delete=models.CASCADE,null=True)
    district    = models.ForeignKey(to=District,on_delete=models.CASCADE,null=True)
    city       = models.ForeignKey(to=City,on_delete=models.CASCADE,null=True)
    pincode = models.CharField(max_length=50,verbose_name='pincode',null=True)
    totalpieces = models.IntegerField(verbose_name='totalpieces',default=0,blank = True)
    totalquanity =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,blank = True,verbose_name= 'totalquanity')
    advance =  models.DecimalField(max_digits=14, decimal_places=4,default=0 ,blank = True,verbose_name= 'advance')
    remarks = models.CharField(max_length=500, null=True,verbose_name= 'Remarks')
    transport =  models.ForeignKey(to = 'financial.account', on_delete=models.CASCADE,null=True,related_name='srtransport')
    broker =  models.ForeignKey(to = 'financial.account', on_delete=models.CASCADE,null=True,related_name='srbroker')
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
    invoicetype = models.ForeignKey(InvoiceType,on_delete=models.CASCADE,verbose_name= 'Invoice Type',null= True)
    ecom =  models.ForeignKey(to = 'financial.account', on_delete=models.CASCADE,null=True,related_name='ecommerce3')
    reversecharge =   models.BooleanField(default=False,verbose_name= 'Reverse charge')
    addless =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'Add/Less')
    # cgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'C.GST Cess',default=0)
    # sgstcess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'S.GST Cess',default=0)
    cess = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Cess',default=0)
    expenses = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Expenses',default=0)
    gtotal = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'G Total')
    roundOff = models.DecimalField(max_digits=14, decimal_places=4,default=0 , verbose_name= 'round off')
    finalAmount = models.DecimalField(max_digits=14, decimal_places=4,default=0 , verbose_name= 'Final amount')
    isammended =   models.BooleanField(default=False)
    originalinvoice = models.ForeignKey("self",null=True,on_delete=models.CASCADE,verbose_name='Orinial invoice',blank=True)
    subentity = models.ForeignKey(subentity,on_delete=models.CASCADE,verbose_name= 'subentity',null= True)
    entity = models.ForeignKey(Entity,on_delete=models.CASCADE,verbose_name= 'entity')
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.CASCADE,verbose_name= 'entity Financial year',null= True)
    createdby = models.ForeignKey(to= User, on_delete=models.CASCADE,null=True)

    class Meta:
        unique_together = ('voucherno', 'entity','entityfinid',)


    def __str__(self):
        return f'{self.voucherno} '

class salereturnDetails(models.Model):
    salereturn = models.ForeignKey(to = salereturn,related_name='salereturndetails', on_delete=models.CASCADE,verbose_name= 'Purchase Order Number')
    product = models.ForeignKey(to = Product, on_delete=models.CASCADE,verbose_name= 'Product',null = True)
    productdesc = models.CharField(max_length=500, null=True,verbose_name='Prduct Desc')
    orderqty =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Order Qty')
    pieces =  models.IntegerField(verbose_name='pieces')
    rate =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Rate')
    amount =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Amount')
   # account   = models.ForeignKey(to = account, on_delete=models.CASCADE,blank=True,null=True,verbose_name= 'Other account')
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
    subentity = models.ForeignKey(subentity,on_delete=models.CASCADE,verbose_name= 'subentity',null= True)
    entity = models.ForeignKey(Entity,on_delete=models.CASCADE,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete=models.CASCADE,null=True)




class salereturnothercharges(TrackingModel):
    salesreturnorderdetail = models.ForeignKey(to = salereturnDetails,related_name='otherchargesdetail', on_delete=models.CASCADE,verbose_name= 'Sale Order Number',null=True)
    account = models.ForeignKey(to = account, on_delete=models.CASCADE,null = True,)
    amount =  models.DecimalField(max_digits=14, decimal_places=4,default=0,verbose_name= 'amount')


    def __str__(self):
        return f'{self.salesreturnorderdetail}'




class journalmain(TrackingModel):
    voucherdate = models.DateField(verbose_name='Vocucher Date',auto_now_add=True)
    voucherno = models.IntegerField(verbose_name='Voucher No')
    vouchertype = models.CharField(max_length=50, null=True,verbose_name='Voucher Type',default='J')
    mainaccountid = models.IntegerField(verbose_name='Main account Id',null=True)
    entrydate = models.DateTimeField(verbose_name='Entry Date')
    entity = models.ForeignKey(Entity,on_delete=models.CASCADE,verbose_name= 'entity')
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.CASCADE,verbose_name= 'entity Financial year',null= True)
    createdby = models.ForeignKey(to= User, on_delete=models.CASCADE,null=True)


    class Meta:
        unique_together = ('voucherno','vouchertype','entity',)
        


    def __str__(self):
        return f'{self.voucherno}  '



class journaldetails(TrackingModel):
    Journalmain = models.ForeignKey(to = journalmain,related_name='journaldetails', on_delete=models.CASCADE,null=True,blank=True,verbose_name='Journal Main')
    account = models.ForeignKey(to = account, on_delete=models.CASCADE,null=True,blank=True,verbose_name='Account Name')
    desc = models.CharField(max_length=500, null=True,verbose_name='Description')
    drcr = models.BooleanField(verbose_name='Debit/Credit')
    debitamount =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Debit Amount',null=True)
    creditamount =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Credit Amount',null=True)
    discount =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Discount',null=True,default=0)
    bankcharges =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Bank Charges',null=True,default=0)
    tds =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'tds',null=True,default=0)
    chqbank = models.CharField(max_length=500, null=True,verbose_name='Chq.no + Bank')
    entity = models.ForeignKey(Entity,on_delete=models.CASCADE,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete=models.CASCADE,null=True)



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
    createdby = models.ForeignKey(to= User, on_delete=models.CASCADE,null=True)
    entity = models.ForeignKey(Entity,on_delete=models.CASCADE,null=True, verbose_name= 'entity')
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.CASCADE,verbose_name= 'entity Financial year',null= True)

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
    

class PaymentVoucher(TrackingModel):
    voucher_number = models.IntegerField()
    vouchernumber = models.CharField(max_length=50, null=True)
    voucherdate = models.DateTimeField(verbose_name='Voucher Date', null=True, blank=True)
    
    paid_from = models.ForeignKey(account, on_delete=models.CASCADE)  # Bank/Cash account
    paid_to = models.ForeignKey(account, related_name='payment_vouchers', on_delete=models.CASCADE)  # Vendor/Supplier account
    
    account_type = models.ForeignKey(accounttype, related_name='payment_account_type', null=True, blank=True, on_delete=models.CASCADE)
    payment_mode = models.ForeignKey(Paymentmodes, related_name='Payment_mode_paid', null=True, on_delete=models.CASCADE)
    
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    narration = models.TextField(blank=True, null=True)
    reference_number = models.CharField(max_length=100, blank=True, null=True)
    
    isledgerposting = models.BooleanField(default=False)
    payeebankname = models.CharField(max_length=100, null=True, blank=True)
    chqno = models.CharField(max_length=50, null=True, blank=True)
    chqdate = models.DateTimeField(verbose_name='Cheque Date', null=True, blank=True)
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_payment_vouchers')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_payment_vouchers')
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    createdby = models.ForeignKey(to=User, on_delete=models.CASCADE, null=True)
    
    entity = models.ForeignKey(Entity, on_delete=models.CASCADE, null=True, verbose_name='Entity')
    entityfinid = models.ForeignKey(entityfinancialyear, on_delete=models.CASCADE, verbose_name='Entity Financial Year', null=True)

    def __str__(self):
        return f"Payment Voucher #{self.voucher_number}"


class PaymentVoucherInvoiceAllocation(models.Model):
    payment_voucher = models.ForeignKey(PaymentVoucher, related_name='invoice_allocations', on_delete=models.CASCADE)
    invoice = models.ForeignKey('purchaseorder', on_delete=models.CASCADE)  # or 'ExpenseInvoiceHeader' based on use case
    
    trans_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, null=True, blank=True)
    otheraccount = models.ForeignKey(account, on_delete=models.CASCADE, null=True, blank=True)
    other_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, null=True, blank=True)
    
    allocated_amount = models.DecimalField(max_digits=12, decimal_places=2)
    isfullamtpaid = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.payment_voucher.voucher_number} - Invoice {self.invoice.invoicenumber}"

    









class stockmain(TrackingModel):
    voucherdate = models.DateField(verbose_name='Vocucher Date',auto_now_add=True)
    voucherno = models.IntegerField(verbose_name='Voucher No')
    vouchertype = models.CharField(max_length=50, null=True,verbose_name='Voucher Type',default='PC')
    entrydate = models.DateTimeField(verbose_name='Entry Date')
    entity = models.ForeignKey(Entity,on_delete=models.CASCADE,verbose_name= 'entity')
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.CASCADE,verbose_name= 'entity Financial year',null= True)
    createdby = models.ForeignKey(to= User, on_delete=models.CASCADE,null=True)


    class Meta:
        unique_together = ('voucherno','vouchertype','entity','entityfinid',)

    def __str__(self):
        return f'{self.voucherno} '



class stockdetails(TrackingModel):
    stockmain = models.ForeignKey(to = stockmain,related_name='stockdetails', on_delete=models.CASCADE,null=True,blank=True,verbose_name='Journal Main')
    stock = models.ForeignKey(to = Product, on_delete=models.CASCADE,null=True,blank=True,verbose_name='Product Name')
    desc = models.CharField(max_length=500, null=True,verbose_name='Description')
    issuereceived = models.BooleanField(verbose_name='Issue/Receipt')
    issuedquantity =  models.DecimalField(max_digits=14,null = True, decimal_places=4,verbose_name= 'Issued quantity')
    recivedquantity =  models.DecimalField(max_digits=14,null = True, decimal_places=4,verbose_name= 'Received quantity')
    entity = models.ForeignKey(Entity,on_delete=models.CASCADE,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete=models.CASCADE,null=True)




class productionmain(TrackingModel):
    voucherdate = models.DateField(verbose_name='Vocucher Date',auto_now_add=True)
    voucherno = models.IntegerField(verbose_name='Voucher No')
    vouchertype = models.CharField(max_length=50, null=True,verbose_name='Voucher Type',default='PV')
    entrydate = models.DateTimeField(verbose_name='Entry Date')
    entity = models.ForeignKey(Entity,on_delete=models.CASCADE,verbose_name= 'entity')
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.CASCADE,verbose_name= 'entity Financial year',null= True)
    createdby = models.ForeignKey(to= User, on_delete=models.CASCADE,null=True)


    class Meta:
        unique_together = ('voucherno','vouchertype','entity','entityfinid',)

    def __str__(self):
        return f'{self.voucherno} '



class productiondetails(TrackingModel):
    stockmain = models.ForeignKey(to = productionmain,related_name='stockdetails', on_delete=models.CASCADE,null=True,blank=True,verbose_name='Journal Main')
    stock = models.ForeignKey(to = Product, on_delete=models.CASCADE,null=True,blank=True,verbose_name='Product Name')
    desc = models.CharField(max_length=500, null=True,verbose_name='Description')
    issuereceived = models.BooleanField(verbose_name='Issue/Receipt')
    quantity =  models.DecimalField(max_digits=14,null = True, decimal_places=4,verbose_name= 'Issued quantity')
    rate =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Rate',null = True)
    entity = models.ForeignKey(Entity,on_delete=models.CASCADE,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete=models.CASCADE,null=True)









class journal(TrackingModel):
    voucherdate = models.DateField(verbose_name='Vocucher Date',auto_now_add=True)
    voucherno = models.IntegerField(verbose_name='Voucher No')
    vouchertype = models.CharField(max_length=50, null=True,verbose_name='Voucher Type',default='J')
    account = models.ForeignKey(to = account, on_delete=models.CASCADE,null=True,blank=True,verbose_name='Account Name')
    desc = models.CharField(max_length=500, null=True,verbose_name='Description')
    drcr = models.BooleanField(verbose_name='Debit/Credit')
    amount =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Amount')
    entrydate = models.DateField(verbose_name='Entry Date',auto_now_add=True)
    entity = models.ForeignKey(Entity,on_delete=models.CASCADE,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete=models.CASCADE,null=True)

    
    class Meta:
        verbose_name = 'journal'
        verbose_name_plural = 'journal'
        




class Transactions(TrackingModel):
    account = models.ForeignKey(to = account, on_delete=models.CASCADE,null=True,blank=True,verbose_name='Account Name')
    transactiontype = models.CharField(max_length=50, null=True,verbose_name='TransactionType')
    transactionid = models.IntegerField(verbose_name='Transaction id')
    desc = models.CharField(max_length=500, null=True,verbose_name='Description')
    drcr = models.BooleanField(verbose_name='Debit/Credit')
    amount =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Amount')
    entrydate = models.DateField(verbose_name='Entry Date',auto_now_add=True)
    entity = models.ForeignKey(Entity,on_delete=models.CASCADE,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete=models.CASCADE,null=True)

class entry(TrackingModel):
    entrydate1 = models.DateField(verbose_name='entrydate1')
    account = models.ForeignKey(to = account, on_delete=models.CASCADE,null=True,blank=True,verbose_name='Account Name',related_name='accountentryrans')
    openingbalance =  models.DecimalField(max_digits=14,null = True,decimal_places=4,verbose_name= 'Opening Amount')
    closingbalance =  models.DecimalField(max_digits=14,null = True,decimal_places=4,verbose_name= 'closing Amount')
    entity = models.ForeignKey(Entity,null=True,on_delete=models.CASCADE,verbose_name= 'entity')
 

class accountentry(TrackingModel):
    entrydate2 = models.DateField()
    account = models.ForeignKey(to = account, on_delete=models.CASCADE,null=True,blank=True,verbose_name='Account Name',related_name='accountentryrans1')
    openingbalance =  models.DecimalField(max_digits=14,null = True,decimal_places=4,verbose_name= 'Opening Amount')
    closingbalance =  models.DecimalField(max_digits=14,null = True,decimal_places=4,verbose_name= 'closing Amount')
    entity = models.ForeignKey(Entity,null=True,on_delete=models.CASCADE,verbose_name= 'entity')

class ExtractDate(Func):
    function = 'DATE'
    output_field = DateField()

class StockTransactions(TrackingModel):
    accounthead = models.ForeignKey(to = accountHead, on_delete=models.CASCADE,null=True,blank=True,verbose_name='Account Head',related_name='headtrans')
    account = models.ForeignKey(to = account, on_delete=models.CASCADE,null=True,blank=True,verbose_name='Account Name',related_name='accounttrans')
    stock = models.ForeignKey(to = Product, on_delete=models.CASCADE,null=True,blank=True,verbose_name='Product Name',related_name='stocktrans')
    transactiontype = models.CharField(max_length=50, null=True,verbose_name='TransactionType')
    transactionid = models.IntegerField(verbose_name='Transaction id')
    detailid = models.IntegerField(verbose_name='Detail id',null=True)
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
    entity = models.ForeignKey(Entity,on_delete=models.CASCADE,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete=models.CASCADE,null=True)

    



class goodstransaction(TrackingModel):
    account = models.ForeignKey(to = account, on_delete=models.CASCADE,null=True,blank=True,verbose_name='Account Name',related_name='Goodaccount')
    stock = models.ForeignKey(to = Product, on_delete=models.CASCADE,null=True,blank=True,verbose_name='Product Name', related_name='goods')
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
    entity = models.ForeignKey(Entity,on_delete=models.CASCADE,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete=models.CASCADE,null=True)





class tdsreturns(TrackingModel):
    tdsreturnname = models.CharField(max_length= 255,verbose_name= 'Tds return')
    tdsreturndesc = models.CharField(max_length= 255,verbose_name= 'Tds return desc')
    # entity = models.ForeignKey(entity,null=True,on_delete=models.CASCADE)
    # createdby = models.ForeignKey(to= User, on_delete=models.CASCADE)


    def __str__(self):
        return f'{self.tdsreturnname}'






class tdstype(TrackingModel):
    tdstypename = models.CharField(max_length= 255,verbose_name= 'Tds Type')
    tdssection = models.CharField(max_length= 255,verbose_name= 'Tds Type Code')
    tdsreturn = models.ForeignKey(tdsreturns,on_delete=models.CASCADE,verbose_name= 'Tds Return',null = True)
    # entity = models.ForeignKey(entity,null=True,on_delete=models.CASCADE)
    # createdby = models.ForeignKey(to= User, on_delete=models.CASCADE)


    def __str__(self):
        return f'{self.tdstypename}'



class tdsmain(TrackingModel):
    voucherdate = models.DateField(verbose_name='Vocucher Date',default=datetime.date.today)
    voucherno = models.IntegerField(verbose_name='Voucher No')
    creditaccountid = models.ForeignKey(to = account, on_delete=models.CASCADE,null=True,blank=True,verbose_name='Credit Account Name',related_name='tdscreditaccount')
    creditdesc = models.CharField(max_length= 255,verbose_name= 'Credit Acc desc',null=True)
    debitaccountid = models.ForeignKey(to = account, on_delete=models.CASCADE,null=True,blank=True,verbose_name='debit Account Name',related_name='tdsdebitaccount')
    debitdesc = models.CharField(max_length= 255,verbose_name= 'Debit Acc desc',null=True)
    tdsaccountid = models.ForeignKey(to = account, on_delete=models.CASCADE,null=True,blank=True,verbose_name='Tds Account Name',related_name='tdsaccount1')
    tdsdesc = models.CharField(max_length= 255,verbose_name= 'Tds Acc desc',null=True)
    tdsreturnccountid = models.ForeignKey(to = tdsreturns, on_delete=models.CASCADE,null=True,blank=True,verbose_name='Tds Account Name',related_name='tdsreturnaccount1')
    tdsreturndesc = models.CharField(max_length= 255,verbose_name= 'tds return Acc desc',null=True)
    tdstype = models.ForeignKey(to = tdstype, on_delete=models.CASCADE,null=True,blank=True,verbose_name='Tds Type',related_name='tdstype')
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
    entityid = models.ForeignKey(Entity,null=True,on_delete=models.CASCADE)
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.CASCADE,verbose_name= 'entity Financial year',null= True)
    createdby = models.ForeignKey(to= User, on_delete=models.CASCADE,null = True)


    class Meta:
        unique_together = ('voucherno', 'entityid','entityfinid',)


    def __str__(self):
        return f'{self.voucherno}'


class debitcreditnote(TrackingModel):
    voucherdate = models.DateTimeField(verbose_name='Vocucher Date',null=True)
    voucherno = models.IntegerField(verbose_name='Voucher No')
    debitaccount = models.ForeignKey(to = account, on_delete=models.CASCADE,null=True,blank=True,verbose_name='deditaccount',related_name='dcdebitaccount')
    creditaccount = models.ForeignKey(to = account, on_delete=models.CASCADE,null=True,blank=True,verbose_name='credit account',related_name='dccreditaccount')
    detail = models.CharField(max_length=500, null=True,verbose_name='detail')
    ledgereffect = models.BooleanField(verbose_name='Effect on Ledger')
    product = models.ForeignKey(to = Product, on_delete=models.CASCADE,verbose_name= 'Product',null = True)
    quantity =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'quantity')
    rate =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Rate')
    basicvalue =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Amount')
    cndnamount =  models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Credit/Debit Note')
    tdssection = models.ForeignKey(to = tdstype, on_delete=models.CASCADE,null=True,blank=True,verbose_name='Tds section')
    vouchertype = models.CharField(max_length=50, null=True,verbose_name='Voucher Type',default='D')
    entity = models.ForeignKey(Entity,on_delete=models.CASCADE,verbose_name= 'entity')
    entityfinid = models.ForeignKey(entityfinancialyear,on_delete=models.CASCADE,verbose_name= 'entity Financial year',null= True)
    createdby = models.ForeignKey(to= User, on_delete=models.CASCADE,null=True)


    #class Meta:
        #unique_together = ('voucherno','vouchertype','entity',)

    def __str__(self):
         return f'{self.voucherno} '
    

class closingstock(TrackingModel):
    stockdate = models.DateTimeField(verbose_name='Stock Date',null=True)
    stock = models.ForeignKey(to = Product, on_delete=models.CASCADE,verbose_name= 'stock Name',null = True)
    closingrate = models.DecimalField(max_digits=14, decimal_places=4,verbose_name= 'Closing Rate')
    entity = models.ForeignKey(Entity,on_delete=models.CASCADE,verbose_name= 'entity')
    createdby = models.ForeignKey(to= User, on_delete=models.CASCADE,null=True)


    #class Meta:
        #unique_together = ('voucherno','vouchertype','entity',)

    def __str__(self):
         return f'{self.stock} '
    



    

class supplytype(TrackingModel):
    supplytypecode = models.CharField(max_length=10, null=True,verbose_name='supplytypecode')
    supplytypename = models.CharField(max_length=100, null=True,verbose_name='supplytypename')

    def __str__(self):
         return f'{self.supplytypecode}'
    

class PayDtls(models.Model):
    invoice = models.OneToOneField('SalesOderHeader', on_delete=models.CASCADE,null=True, blank=True, related_name='paydtls')
    sales_return = models.OneToOneField('salereturn', on_delete=models.CASCADE, null=True, blank=True, related_name='paydtls')
    purchase_return = models.OneToOneField('PurchaseReturn', on_delete=models.CASCADE, null=True, blank=True, related_name='paydtls')
    Nm = models.CharField(max_length=100, null=True, blank=True)
    Mode = models.CharField(max_length=100, null=True, blank=True)  # Mode of Payment (e.g., Cash, Credit)
    FinInsBr = models.CharField(max_length=100, null=True, blank=True)
    PayTerm = models.CharField(max_length=100, null=True, blank=True)
    PayInstr = models.CharField(max_length=100, null=True, blank=True)
    CrTrn = models.CharField(max_length=100, null=True, blank=True)
    DirDr = models.CharField(max_length=100, null=True, blank=True)
    CrDay = models.IntegerField(null=True, blank=True)
    PaidAmt = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    PamtDue = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    PayRefNo = models.CharField(max_length=100, null=True, blank=True)

class RefDtls(models.Model):
    invoice = models.OneToOneField('SalesOderHeader', on_delete=models.CASCADE,null=True, blank=True, related_name='refdtls')
    sales_return = models.OneToOneField('salereturn', on_delete=models.CASCADE, null=True, blank=True, related_name='refdtls')
    purchase_return = models.OneToOneField('PurchaseReturn', on_delete=models.CASCADE, null=True, blank=True, related_name='refdtls')
    InvRm = models.TextField(null=True, blank=True)
    PrecDocNo = models.CharField(max_length=100, null=True, blank=True)
    PrecDocDt = models.DateTimeField(verbose_name='PrecDocDt',null = True)
    ContrRefr = models.CharField(max_length=100, null=True, blank=True)

class AddlDocDtls(models.Model):
    invoice = models.ForeignKey('SalesOderHeader', on_delete=models.CASCADE,null=True, blank=True, related_name='addldocdtls')
    sales_return = models.ForeignKey('salereturn', on_delete=models.CASCADE, null=True, blank=True, related_name='addldocdtls')
    purchase_return = models.ForeignKey('PurchaseReturn', on_delete=models.CASCADE, null=True, blank=True, related_name='addldocdtls')
    Url = models.URLField(null=True, blank=True)
    Docs = models.CharField(max_length=255,null=True, blank=True)
    Info = models.CharField(max_length=255, null=True, blank=True)

class EwbDtls(models.Model):
    invoice = models.OneToOneField('SalesOderHeader', on_delete=models.CASCADE,null=True, blank=True, related_name='ewbdtls')
    sales_return = models.OneToOneField('salereturn', on_delete=models.CASCADE, null=True, blank=True, related_name='ewbdtls1')
    purchase_return = models.OneToOneField('PurchaseReturn', on_delete=models.CASCADE, null=True, blank=True, related_name='ewbdtls2')
    TransId = models.CharField(max_length=20,null=True, blank=True)
    TransName = models.CharField(max_length=100,null=True, blank=True)
    Distance = models.DecimalField(max_digits=8, decimal_places=2,null=True, blank=True)
    TransDocNo = models.CharField(max_length=50,null=True, blank=True)
    TransMode = models.CharField(max_length=1,null=True, blank=True)  # e.g., R - Road, A - Air
    TransDocDt = models.DateTimeField(verbose_name='TransDocDt',null = True)
    VehNo = models.CharField(max_length=20,null = True)
    VehType = models.CharField(max_length=1,null = True)  # e.g., R - Regular, O - ODC

class ExpDtls(models.Model):
    invoice = models.OneToOneField('SalesOderHeader', on_delete=models.CASCADE,null=True, blank=True, related_name='expdtls')
    sales_return = models.OneToOneField('salereturn', on_delete=models.CASCADE, null=True, blank=True, related_name='expdtls')
    purchase_return = models.OneToOneField('PurchaseReturn', on_delete=models.CASCADE, null=True, blank=True, related_name='expdtls')
    ShipBNo = models.CharField(max_length=100, null=True, blank=True)
    ShipBDt = models.DateTimeField(verbose_name='SShipBDt',null = True)
    Port = models.CharField(max_length=50,null = True)
    RefClm = models.CharField(max_length=3, null=True, blank=True)
    ForCur = models.CharField(max_length=3,null = True)
    CntryCd = models.CharField(max_length=3,null = True)
    ExpDuty = models.BooleanField(default=False)

    


    

class paymentdetails(TrackingModel):
      salesorderheader = models.ForeignKey(to = SalesOderHeader,on_delete=models.CASCADE,verbose_name= 'Sale Order Number')
      account = models.ForeignKey(to = account, on_delete=models.CASCADE,blank=True)
      payeename = models.CharField(max_length=50, null=True,verbose_name='PayeeName')
      bankname = models.CharField(max_length=50, null=True,verbose_name='Ifsccode')
      Ifsccode = models.CharField(max_length=50, null=True,verbose_name='bankname')
      accountnumber = models.CharField(max_length=50, null=True,verbose_name='Account Number')
      modeofpayment = models.ForeignKey(to = modeofpayment, on_delete=models.CASCADE,blank=True)
      paymentterms = models.CharField(max_length=50, null=True,verbose_name='paymentterms')
      paymentinstructions = models.CharField(max_length=50, null=True,verbose_name='paymentinstructions')
      creditdays = models.IntegerField(verbose_name='Credit Days')
      paidamount = models.IntegerField(verbose_name='Paid Amount')
      paymentDue = models.IntegerField(verbose_name='Payment Due')


class ewbdetails(TrackingModel):
      salesorderheader = models.ForeignKey(to = SalesOderHeader,on_delete=models.CASCADE,verbose_name= 'Sale Order Number')
      account = models.ForeignKey(to = account, on_delete=models.CASCADE,blank=True)
      gstno   = models.CharField(max_length=50, null=True,verbose_name= ('Gst No'),blank = True)
      transportname = models.CharField(max_length=50, null=True,verbose_name='Transport Name')
      transportmode = models.ForeignKey(to = transportmode, on_delete=models.CASCADE,blank=True)
      distance = models.IntegerField(verbose_name='Distance')
      transportdocno = models.CharField(max_length=50, null=True,verbose_name='Transport doc no')
      transdocdate = models.DateTimeField(verbose_name='Transport document date',null = True)
      vehicalno = models.CharField(max_length=50, null=True,verbose_name='vehicalno')
      vehicaltype = models.ForeignKey(to = vehicalType, on_delete=models.CASCADE,blank=True)


class TxnType(models.TextChoices):
    SALES = "sales", "Sales"
    PURCHASE = "purchase", "Purchase"
    JOURNAL = "journal", "Journal"
    SALES_RETURN = "salesreturn", "Sales Return"
    PURCHASE_RETURN = "purchasereturn", "Purchase Return"


class JournalLine(models.Model):
    # Money ledger (GL). One row = one debit OR one credit.
    entry = models.ForeignKey(entry, on_delete=models.CASCADE, related_name='journal_lines')
    entity = models.ForeignKey(Entity, on_delete=models.CASCADE)

    transactiontype = models.CharField(max_length=20, choices=TxnType.choices, db_index=True)
    transactionid = models.IntegerField(db_index=True)      # header id
    detailid = models.IntegerField(null=True, blank=True)   # line id (optional)
    voucherno = models.CharField(max_length=50, null=True, blank=True, db_index=True)

    accounthead = models.ForeignKey(accountHead, on_delete=models.CASCADE,
                                    null=True, blank=True, related_name='jl_head')
    account = models.ForeignKey(account, on_delete=models.CASCADE,
                                null=True, blank=True, related_name='jl_account')

    drcr = models.BooleanField()  # True=Debit, False=Credit
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)

    desc = models.CharField(max_length=500, null=True, blank=True)
    entrydate = models.DateField(db_index=True)
    entrydatetime = models.DateTimeField(null=True, blank=True)
    createdby = models.ForeignKey(User, on_delete=models.CASCADE, null=True)

    class Meta:
        constraints = [
            CheckConstraint(name="ck_amount_gt_zero", check=Q(amount__gt=0)),
        ]
        indexes = [
            Index(fields=['entity', 'transactiontype', 'transactionid'], name='ix_jl_txn_locator'),
            Index(fields=['account'], name='ix_jl_account'),
            Index(fields=['entry'], name='ix_jl_entry'),
            Index(fields=['entrydate'], name='ix_jl_entrydate'),
        ]

    def __str__(self):
        side = "Dr" if self.drcr else "Cr"
        return f"{side} {self.amount} · {self.account or self.accounthead} · {self.transactiontype}#{self.transactionid}"


class InventoryMove(models.Model):
    # Inventory movement (quantities/costing).
    entry = models.ForeignKey(entry, on_delete=models.CASCADE, related_name='inventory_moves')
    entity = models.ForeignKey(Entity, on_delete=models.CASCADE)

    transactiontype = models.CharField(max_length=20, choices=TxnType.choices, db_index=True)
    transactionid = models.IntegerField(db_index=True)      # header id
    detailid = models.IntegerField(null=True, blank=True)   # line id
    voucherno = models.CharField(max_length=50, null=True, blank=True, db_index=True)

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='inv_moves')
    location = models.IntegerField(null=True, blank=True)
    uom = models.IntegerField(null=True, blank=True)

    qty = models.DecimalField(max_digits=14, decimal_places=4)         # +in / -out
    unit_cost = models.DecimalField(max_digits=14, decimal_places=4, default=ZERO4)  # valuation cost
    ext_cost = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)   # qty*unit_cost (abs)

    move_type = models.CharField(max_length=10)  # "OUT"/"IN"/"REV" etc. (free text if you like)
    entrydate = models.DateField(db_index=True)
    entrydatetime = models.DateTimeField(null=True, blank=True)
    createdby = models.ForeignKey(User, on_delete=models.CASCADE, null=True)

    class Meta:
        constraints = [
            CheckConstraint(name="ck_qty_nonzero", check=~Q(qty=0)),
            CheckConstraint(name="ck_cost_nonneg", check=Q(unit_cost__gte=0) & Q(ext_cost__gte=0)),
        ]
        indexes = [
            Index(fields=['entity', 'product', 'entrydate'], name='ix_im_entity_product_date'),
            Index(fields=['transactiontype', 'transactionid'], name='ix_im_txn_locator'),
        ]

    def __str__(self):
        direction = "IN" if self.qty > 0 else "OUT"
        return f"{direction} {self.qty} · {self.product} · {self.transactiontype}#{self.transactionid}"



class SalesQuotationHeader(TrackingModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SENT = "sent", "Sent"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"
        EXPIRED = "expired", "Expired"

    quote_date = models.DateTimeField("Quotation Date", auto_now_add=False, null=True)
    quote_no = models.CharField("Quotation No", max_length=50, null=True, blank=True)
    version = models.IntegerField(default=1)
    taxtype = models.IntegerField(default=1)
    Terms = models.IntegerField(default=1)  # (kept name as provided)
    invoicetype = models.IntegerField(default=1)

    account = models.ForeignKey(account, on_delete=models.CASCADE, null=True, blank=True)
    contact_name = models.CharField(max_length=120, null=True, blank=True)
    contact_email = models.EmailField(null=True, blank=True)
    # Optional shipping snapshot for clarity; keep it lightweight
    shippedto = models.ForeignKey(
        ShippingDetails,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quote_shipto",
    )

    # Validity & state
    valid_until = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)

    # Commercial terms
    price_list = models.CharField(max_length=60, null=True, blank=True)
    currency = models.CharField(max_length=10, null=True, blank=True)  # if needed
    remarks = models.CharField(max_length=500, null=True, blank=True)

    # Totals (estimates allowed; keep taxes optional)
    tds194q = models.DecimalField("TDS 194 @", max_digits=5, decimal_places=2, default=ZERO2)
    tds194q1 = models.DecimalField("TDS 194 @", max_digits=5, decimal_places=2, default=ZERO2)
    tcs206c1ch1 = models.DecimalField("Tcs 206C1cH1", max_digits=5, decimal_places=2, default=ZERO2)
    tcs206c1ch2 = models.DecimalField("Tcs 206C1cH2", max_digits=5, decimal_places=2, default=ZERO2)
    tcs206c1ch3 = models.DecimalField("Tcs tcs206c1ch3", max_digits=5, decimal_places=2, default=ZERO2)
    tcs206C1 = models.DecimalField("Tcs 206C1", max_digits=5, decimal_places=2, default=ZERO2)
    tcs206C2 = models.DecimalField("Tcs 206C2", max_digits=5, decimal_places=2, default=ZERO2)

    totalgst = models.DecimalField("totalgst", max_digits=14, decimal_places=2, default=ZERO2)
    cess = models.DecimalField("Cess", max_digits=14, decimal_places=2, default=ZERO2)
    stbefdiscount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)  # sum(ratebefdiscount)
    discount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    addless = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    cgst          = models.DecimalField("C.GST", max_digits=14, decimal_places=2, default=ZERO2)
    sgst          = models.DecimalField("S.GST", max_digits=14, decimal_places=2, default=ZERO2)
    igst          = models.DecimalField("I.GST", max_digits=14, decimal_places=2, default=ZERO2)
    isigst        = models.BooleanField("IsIgst", default=False)
    gtotal = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)



    # Org scoping like invoices
    subentity = models.ForeignKey(subentity, on_delete=models.CASCADE, null=True, blank=True)
    entity = models.ForeignKey(Entity, on_delete=models.CASCADE, null=True, blank=True)
    entityfinid = models.ForeignKey(entityfinancialyear, on_delete=models.CASCADE, null=True, blank=True)

    createdby = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        constraints = [
            UniqueConstraint(fields=("quote_no", "entity", "entityfinid"), name="uq_quote_no_entity_fin"),
            CheckConstraint(
                name="ck_quote_amounts_nonneg",
                check=(
                    Q(stbefdiscount__gte=0)
                    & Q(discount__gte=0)
                    & Q(subtotal__gte=0)
                    & Q(addless__gte=0)
                    & Q(cess__gte=0)
                    & Q(cgst__gte=0)
                    & Q(sgst__gte=0)
                    & Q(igst__gte=0)
                    & Q(totalgst__gte=0)
                    & Q(gtotal__gte=0)
                ),
            ),
            # Ensure tax-mode consistency:
            # - If IGST mode (isigst=True) => CGST/SGST must be 0
            # - If intra-state (isigst=False) => IGST must be 0
            CheckConstraint(
                name="ck_quote_tax_mode_consistency",
                check=(Q(isigst=True, cgst=0, sgst=0) | Q(isigst=False, igst=0)),
            ),
            # Optional (strict): totalgst must equal cgst+sgst+igst.
            # Comment out if rounding differences are expected.
            CheckConstraint(
                name="ck_quote_totalgst_sum",
                check=Q(totalgst=F("cgst") + F("sgst") + F("igst")),
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "entityfinid", "quote_no"], name="ix_quote_entity_fin_no"),
            models.Index(fields=["quote_date"], name="ix_quote_date"),
            models.Index(fields=["account"], name="ix_quote_customer"),
            models.Index(fields=["status", "valid_until"], name="ix_quote_status_valid"),
        ]

    def __str__(self) -> str:
        return f"Q{self.quote_no or '-'} v{self.version}"


class SalesQuotationDetail(TrackingModel):
    header        = models.ForeignKey(SalesQuotationHeader, related_name="lines", on_delete=models.CASCADE)
    product       = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    productdesc   = models.CharField(max_length=500, null=True, blank=True)

    qty           = models.DecimalField("Qty", max_digits=14, decimal_places=4, default=ZERO4)
    pieces        = models.IntegerField(default=0)

    ratebefdiscount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    line_discount   = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    rate            = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    amount          = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)

    # Optional tax snapshot (not enforced); keep percentages bounded if provided
    cgstpercent   = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    sgstpercent   = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    igstpercent   = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    cgst          = models.DecimalField("C.GST", max_digits=14, decimal_places=2, default=ZERO2)
    sgst          = models.DecimalField("S.GST", max_digits=14, decimal_places=2, default=ZERO2)
    igst          = models.DecimalField("I.GST", max_digits=14, decimal_places=2, default=ZERO2)
    linetotal     = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)

    is_service    = models.BooleanField(default=False)

    subentity     = models.ForeignKey(subentity, on_delete=models.CASCADE, null=True, blank=True)
    entity        = models.ForeignKey(Entity, on_delete=models.CASCADE, null=True, blank=True)
    createdby     = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        constraints = [
            models.CheckConstraint(
                name="ck_quote_detail_amounts_nonneg",
                check=(Q(amount__gte=0) & Q(linetotal__gte=0) & Q(qty__gte=0) & Q(pieces__gte=0))
            ),
            models.CheckConstraint(
                name="ck_quote_detail_percent_bounds",
                check=((Q(cgstpercent__isnull=True) | (Q(cgstpercent__gte=0) & Q(cgstpercent__lte=100))) &
                       (Q(sgstpercent__isnull=True) | (Q(sgstpercent__gte=0) & Q(sgstpercent__lte=100))) &
                       (Q(igstpercent__isnull=True) | (Q(igstpercent__gte=0) & Q(igstpercent__lte=100))))
            ),
            
        ]
        indexes = [
            models.Index(fields=["header"], name="ix_quote_detail_header"),
            models.Index(fields=["product"], name="ix_quote_detail_product"),
        ]

    def __str__(self):
        return f"{self.product or self.productdesc or '#'}"








    





    







