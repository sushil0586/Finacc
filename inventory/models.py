
from django.db import models
from django.db.models.deletion import CASCADE
from helpers.models import TrackingModel
from Authentication.models import User
from django.utils.translation import gettext as _
from entity.models import entity
from financial.models import account



class GstRate(TrackingModel):
    CSGT = models.DecimalField(max_digits=10, decimal_places=2,default=True,blank=True)
    SGST = models.DecimalField(max_digits=10, decimal_places=2,default=True,blank=True)
    IGST = models.DecimalField(max_digits=10, decimal_places=2,default=True,blank=True)
    entity = models.ForeignKey(entity,null=True,on_delete=models.CASCADE)
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE)


    def __str__(self):
        return f'{self.CSGT} '



class Ratecalculate(TrackingModel):
    rname = models.CharField(max_length= 255,verbose_name=_('Rate calc Name'))
    rcode = models.CharField(max_length= 255,verbose_name=_('Rate Calc Code'))
    entity = models.ForeignKey(entity,null=True,on_delete=models.CASCADE)
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE)


    def __str__(self):
        return f'{self.rname} '

class UnitofMeasurement(TrackingModel):
    unitname = models.CharField(max_length= 255,verbose_name=_('UOM calculate'))
    unitcode = models.CharField(max_length= 255,verbose_name=_('UOM calculate'))
    entity = models.ForeignKey(entity,null=True,on_delete=models.CASCADE)
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE)


    def __str__(self):
        return f'{self.unitname} '

class stkcalculateby(TrackingModel):
    unitname = models.CharField(max_length= 255,verbose_name=_('UOM calculate'))
    unitcode = models.CharField(max_length= 255,verbose_name=_('UOM calculate'))
    entity = models.ForeignKey(entity,null=True,on_delete=models.CASCADE)
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE)


    def __str__(self):
        return f'{self.unitname} '

class typeofgoods(TrackingModel):
    goodstype = models.CharField(max_length= 255,verbose_name=_('Goods Type'))
    goodscode = models.CharField(max_length= 255,verbose_name=_('Goods Code'))
    entity = models.ForeignKey(entity,null=True,on_delete=models.CASCADE)
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE)


    def __str__(self):
        return f'{self.goodstype} '

class stkvaluationby(TrackingModel):
    valuationby = models.CharField(max_length= 255,verbose_name=_('Valuation By'))
    valuationcode = models.CharField(max_length= 255,verbose_name=_('valuation code'))
    entity = models.ForeignKey(entity,null=True,on_delete=models.CASCADE)
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE)


    def __str__(self):
        return f'{self.valuationby} '

class gsttype(TrackingModel):
    gsttypename = models.CharField(max_length= 255,verbose_name=_('Gst type Name'))
    gsttypecode = models.CharField(max_length= 255,verbose_name=_('Gst Type Code'))
    entity = models.ForeignKey(entity,null=True,on_delete=models.CASCADE)
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE)


    def __str__(self):
        return f'{self.gsttypename} '


class ProductCategory(TrackingModel):
    pcategoryname = models.CharField(max_length= 255,verbose_name=_('Product Category'))
    maincategory = models.ForeignKey("self",null=True,on_delete=models.CASCADE,verbose_name=_('Main category'),default=True,blank=True)
    entity = models.ForeignKey(entity,null=True,on_delete=models.CASCADE)
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE)


    def __str__(self):
        return f'{self.pcategoryname} '

class Product(TrackingModel):
    productname = models.CharField(max_length= 255,verbose_name=_('Product Name'))
    productcode = models.IntegerField(default=1001,blank=True,verbose_name=_('Product Code'))
    productdesc = models.CharField(max_length= 255,verbose_name=_('product desc'))
    is_pieces = models.BooleanField(default=True)
    openingstockqty = models.DecimalField(max_digits=10, decimal_places=2,default=True,blank=True,null=True)
    openingstockboxqty = models.IntegerField(default=True,blank=True,verbose_name=_('Box/Pcs'),null=True)
    openingstockvalue = models.DecimalField(max_digits=10, decimal_places=2,null=True)
    productcategory = models.ForeignKey(to= ProductCategory,default=True,blank=True, on_delete= models.CASCADE,verbose_name=_('Product Category'))
    purchaserate = models.DecimalField(max_digits=10, decimal_places=2,default=True,blank=True,verbose_name=_('Purchase Rate'))
    prlesspercentage = models.DecimalField(max_digits=10, decimal_places=2,null=True)
    mrp = models.DecimalField(max_digits=10, decimal_places=2,blank=True,null=True)
    mrpless = models.DecimalField(max_digits=10, decimal_places=2,blank=True,null=True)
    salesprice = models.DecimalField(max_digits=10, decimal_places=2,blank=True,null=True)
    totalgst = models.DecimalField(max_digits=10, decimal_places=2,blank=True,null=True)
    cgst = models.DecimalField(max_digits=10, decimal_places=2,blank=True,null=True)
    cgstcess = models.DecimalField(max_digits=10, decimal_places=2,blank=True,null=True)
    sgst = models.DecimalField(max_digits=10, decimal_places=2,blank=True,null=True)
    sgstcess = models.DecimalField(max_digits=10, decimal_places=2,blank=True,null=True)
    igst = models.DecimalField(max_digits=10, decimal_places=2,blank=True,null=True)
    igstcess = models.DecimalField(max_digits=10, decimal_places=2,blank=True,null=True)
    is_stockable = models.BooleanField(default=True)
    purchaseaccount = models.ForeignKey(account,related_name = 'purchaseaccount',on_delete=models.CASCADE,null=True,blank=True)
    saleaccount = models.ForeignKey(account,on_delete=models.CASCADE,null=True,blank=True)
    hsn = models.IntegerField(default=1001,blank=True,verbose_name=_('Hsn Code'))
    Ratecalculate = models.ForeignKey(to= Ratecalculate,null=True,on_delete= models.CASCADE,verbose_name=_('Rate calculate'))
    UnitofMeasurement = models.ForeignKey(to= UnitofMeasurement,null=True,blank=True, on_delete= models.CASCADE,verbose_name=_('Unit of Measurement'))
    stkcalculateby = models.ForeignKey(to= stkcalculateby,null=True,blank=True, on_delete= models.CASCADE,verbose_name=_('Stock Calculated By'))
    typeofgoods = models.ForeignKey(to= typeofgoods,null=True,blank=True, on_delete= models.CASCADE,verbose_name=_('Type of goods'))
    stkvaluationby = models.ForeignKey(to= stkvaluationby,null=True,blank=True, on_delete= models.CASCADE,verbose_name=_('Stock valuation by'))
    gsttype = models.ForeignKey(to= gsttype,null=True,blank=True, on_delete= models.CASCADE,verbose_name=_('Gst Type'))
    entity = models.ForeignKey(entity,on_delete=models.CASCADE)
    createdby = models.ForeignKey(to= User,null=True, on_delete= models.CASCADE)

    def __str__(self):
        return f'{self.productname} '

class Album(models.Model):
    album_name = models.CharField(max_length=100)
    artist = models.CharField(max_length=100)
    owner = models.ForeignKey(to= User, on_delete= models.CASCADE)

class Track(models.Model):
    album = models.ForeignKey(Album, related_name='tracks', on_delete=models.CASCADE)
    order = models.IntegerField()
    title = models.CharField(max_length=100)
    duration = models.IntegerField()
   

    class Meta:
       ordering = ['order']

    def __str__(self):
        return '%d: %s' % (self.order, self.title)
            




