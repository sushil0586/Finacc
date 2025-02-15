
from django.db import models
from django.db.models.deletion import CASCADE
from helpers.models import TrackingModel
from Authentication.models import User
from django.utils.translation import gettext as _
from entity.models import Entity
from financial.models import account
import barcode                      # additional imports
from barcode.writer import ImageWriter
from io import BytesIO
from django.core.files import File
import os



class HsnCode(TrackingModel):
    hsnCode = models.CharField(max_length= 255,verbose_name=_('Hsn code'))
    Hsndescription = models.CharField(max_length= 2000,verbose_name=_('Hsn Description'))
    


    def __str__(self):
        return f'{self.hsnCode} '



class GstRate(TrackingModel):
    CSGT = models.DecimalField(max_digits=14, decimal_places=2,default=True,blank=True)
    SGST = models.DecimalField(max_digits=14, decimal_places=2,default=True,blank=True)
    IGST = models.DecimalField(max_digits=14, decimal_places=2,default=True,blank=True)
    entity = models.ForeignKey(Entity,null=True,on_delete=models.PROTECT)
    createdby = models.ForeignKey(to= User, on_delete=models.PROTECT)


    def __str__(self):
        return f'{self.CSGT} '



class Ratecalculate(TrackingModel):
    rname = models.CharField(max_length= 255,verbose_name=_('Rate calc Name'))
    rcode = models.CharField(max_length= 255,verbose_name=_('Rate Calc Code'))
    entity = models.ForeignKey(Entity,null=True,on_delete=models.PROTECT)
    createdby = models.ForeignKey(to= User, on_delete=models.PROTECT)


    def __str__(self):
        return f'{self.rname} '

class UnitofMeasurement(TrackingModel):
    unitname = models.CharField(max_length= 255,verbose_name=_('UOM calculate'))
    unitcode = models.CharField(max_length= 255,verbose_name=_('UOM calculate'))
    entity = models.ForeignKey(Entity,null=True,on_delete=models.PROTECT)
    createdby = models.ForeignKey(to= User, on_delete=models.PROTECT)


    def __str__(self):
        return f'{self.unitname} '

class stkcalculateby(TrackingModel):
    unitname = models.CharField(max_length= 255,verbose_name=_('UOM calculate'))
    unitcode = models.CharField(max_length= 255,verbose_name=_('UOM calculate'))
    entity = models.ForeignKey(Entity,null=True,on_delete=models.PROTECT)
    createdby = models.ForeignKey(to= User, on_delete=models.PROTECT)


    def __str__(self):
        return f'{self.unitname} '

class typeofgoods(TrackingModel):
    goodstype = models.CharField(max_length= 255,null=True,verbose_name=_('Goods Type'))
    goodscode = models.CharField(max_length= 255,null=True,verbose_name=_('Goods Code'))
    entity = models.ForeignKey(Entity,null=True,on_delete=models.PROTECT)
    createdby = models.ForeignKey(to= User, on_delete=models.PROTECT)


    def __str__(self):
        return f'{self.goodstype} '

class stkvaluationby(TrackingModel):
    valuationby = models.CharField(max_length= 255,verbose_name=_('Valuation By'))
    valuationcode = models.CharField(max_length= 255,verbose_name=_('valuation code'))
    entity = models.ForeignKey(Entity,null=True,on_delete=models.PROTECT)
    createdby = models.ForeignKey(to= User, on_delete=models.PROTECT)


    def __str__(self):
        return f'{self.valuationby} '

class gsttype(TrackingModel):
    gsttypename = models.CharField(max_length= 255,verbose_name=_('Gst type Name'))
    gsttypecode = models.CharField(max_length= 255,verbose_name=_('Gst Type Code'))
    entity = models.ForeignKey(Entity,null=True,on_delete=models.PROTECT)
    createdby = models.ForeignKey(to= User, on_delete=models.PROTECT)


    def __str__(self):
        return f'{self.gsttypename} '


class ProductCategory(TrackingModel):
    pcategoryname = models.CharField(max_length= 50,verbose_name=_('Product Category'))
    maincategory = models.ForeignKey("self",null=True,on_delete=models.PROTECT,verbose_name=_('Main category'),blank=True)
    entity = models.ForeignKey(Entity,null=True,on_delete=models.PROTECT)
    createdby = models.ForeignKey(to= User, on_delete=models.PROTECT)


    def __str__(self):
        return f'{self.pcategoryname} '


def get_image_path(instance, filename):
    return os.path.join(str(instance.entity),'photos',filename)

class Product(TrackingModel):
    productname = models.CharField(max_length= 50,verbose_name=_('Product Name'))
    productcode = models.IntegerField(null = True,blank=True,verbose_name=_('Product Code'))
    productdesc = models.CharField(max_length= 100,null = True,verbose_name=_('product desc'))
    is_pieces = models.BooleanField(default=True)
    openingstockqty = models.DecimalField(max_digits=14, decimal_places=2,blank=True,null=True)
    openingstockboxqty = models.IntegerField(blank=True,verbose_name=_('Box/Pcs'),null=True)
    openingstockvalue = models.DecimalField(max_digits=14, decimal_places=2,null=True,blank=True)
    productcategory = models.ForeignKey(to= ProductCategory,blank=True, on_delete=models.PROTECT,verbose_name=_('Product Category'))
    purchaserate = models.DecimalField(max_digits=14, decimal_places=2,blank=True,verbose_name=_('Purchase Rate'),null=True)
    prlesspercentage = models.DecimalField(max_digits=14, decimal_places=2,null=True,blank=True)
    mrp = models.DecimalField(max_digits=14, decimal_places=2,blank=True,null=True)
    mrpless = models.DecimalField(max_digits=14, decimal_places=2,blank=True,null=True)
    salesprice = models.DecimalField(max_digits=14, decimal_places=2,blank=True,null=True)
    totalgst = models.DecimalField(max_digits=14, decimal_places=2,blank=True,null=True)
    cgst = models.DecimalField(max_digits=14, decimal_places=2,blank=True,null=True)
    #cgstcess = models.DecimalField(max_digits=14, decimal_places=2,blank=True,null=True)
    sgst = models.DecimalField(max_digits=14, decimal_places=2,blank=True,null=True)
    #sgstcess = models.DecimalField(max_digits=14, decimal_places=2,blank=True,null=True)
    igst = models.DecimalField(max_digits=14, decimal_places=2,blank=True,null=True)
    cesstype = models.BooleanField(default=True)
    cess = models.DecimalField(max_digits=14, decimal_places=2,default = 0,null=True)
    is_product = models.BooleanField(default=True)
    purchaseaccount = models.ForeignKey(account,related_name = 'purchaseaccount',on_delete=models.PROTECT)
    saleaccount = models.ForeignKey(account,on_delete=models.PROTECT)
    hsn = models.ForeignKey(HsnCode,on_delete=models.PROTECT, blank=True,verbose_name=_('Hsn Code'),null = True)
    ratecalculate = models.ForeignKey(to= Ratecalculate,null=True,on_delete=models.PROTECT,verbose_name=_('Rate calculate'))
    unitofmeasurement = models.ForeignKey(to= UnitofMeasurement,null=True,blank=True, on_delete=models.PROTECT,verbose_name=_('Unit of Measurement'))
    stkcalculateby = models.ForeignKey(to= stkcalculateby,null=True,blank=True, on_delete=models.PROTECT,verbose_name=_('Stock Calculated By'))
    typeofgoods = models.ForeignKey(to= typeofgoods,null=True,blank=True, on_delete=models.PROTECT,verbose_name=_('Type of goods'))
    stkvaluationby = models.ForeignKey(to= stkvaluationby,null=True,blank=True, on_delete=models.PROTECT,verbose_name=_('Stock valuation by'))
    gsttype = models.ForeignKey(to= gsttype,null=True,blank=True, on_delete=models.PROTECT,verbose_name=_('Gst Type'))
    entity = models.ForeignKey(Entity,on_delete=models.PROTECT)
    createdby = models.ForeignKey(to= User,null=True, on_delete=models.PROTECT)
    barcode = models.ImageField(upload_to=get_image_path, blank=True)

    def __str__(self):
        return f'{self.productname}'

    def save(self, *args, **kwargs):          # overriding save() 
        COD128 = barcode.get_barcode_class('code128')
        rv = BytesIO()
        code = COD128(f'Mrp: {self.mrp} Our Prrice: {self.salesprice}', writer=ImageWriter()).write(rv)
        self.barcode.save(f'{self.productname}.png', File(rv), save=False)
        return super().save(*args, **kwargs)

class Album(models.Model):
    album_name = models.CharField(max_length=100)
    artist = models.CharField(max_length=100)
    createdby = models.ForeignKey(to= User, on_delete=models.PROTECT)

class Track(models.Model):
    album = models.ForeignKey(Album, related_name='tracks', on_delete=models.PROTECT)
    order = models.IntegerField()
    title = models.CharField(max_length=100)
    duration = models.IntegerField()
   

    class Meta:
       ordering = ['order']

    def __str__(self):
        return '%d: %s' % (self.order, self.title)
            




