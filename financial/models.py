from re import T
from django.db import models


from helpers.models import TrackingModel
from django.utils.translation import gettext as _
from Authentication.models import User 
from geography.models import Country,State,District,City
from entity.models import Entity

# Create your models here.



class accounttype(TrackingModel):
    accounttypename = models.CharField(max_length= 255,verbose_name=_('Acc type Name'))
    accounttypecode = models.CharField(max_length= 255,verbose_name=_('Acc Type Code'))
    entity = models.ForeignKey(Entity,null=True,on_delete=models.CASCADE)
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE)


    def __str__(self):
        return f'{self.accounttypename} '


Debit = 'Debit'
Credit = 'Credit'

class accountHead(TrackingModel):
    BALANCE_TYPE = [
        (Credit, _('Credit')),
        (Debit, _('Debit'))
    ]

    Details_in_BS = [
        ('Yes', _('Yes')),
        ('No', _('No'))
    ]

    Group = [
        ('Balance_sheet', _('Balance Sheet')),
        ('P/l', _('Profit Loss'))
    ]

    

    name = models.CharField(max_length=200,verbose_name=_('Account Name'))
    code = models.IntegerField(verbose_name=_('Account Head Code'))
    balanceType =  models.CharField(max_length=50,null=True,verbose_name=_('Balance Type'))
    drcreffect =   models.CharField(max_length=20,verbose_name=_('Debit/credit Effect'))
    description =   models.CharField(max_length=200,verbose_name=_('Description'),null=True)
    accountheadsr = models.ForeignKey("self",null=True,on_delete=models.CASCADE,verbose_name=_('Account head Sr'),blank=True)
    detailsingroup =  models.IntegerField(null=True,blank = True)
    entity = models.ForeignKey(Entity,related_name='entity_accountheads',null=True,on_delete=models.CASCADE)
    canbedeleted      = models.BooleanField(verbose_name=_('Can be deleted'),default = True)
    createdby = models.ForeignKey(to= User,  on_delete= models.CASCADE,null= True)

    class Meta:
        verbose_name = _('Account head')
        verbose_name_plural = _('Account Heads')
        


    
    def __str__(self):
        return f'{self.name} , {self.code}'



class account(TrackingModel):
    accountdate = models.DateTimeField(verbose_name='Account date',null = True)
    accounthead = models.ForeignKey(to = accountHead,related_name='accounthead_accounts', on_delete= models.CASCADE,null = True)
    creditaccounthead = models.ForeignKey(to = accountHead,related_name='accounthead_creditaccounts', on_delete= models.CASCADE,null = True)
    accountcode = models.IntegerField(verbose_name=_('Account Code'),null=True,blank=True,default=1000)
    gstno       = models.CharField(max_length=50, null=True,verbose_name=_('Gst No'),blank = True)
    accountname       = models.CharField(max_length=50, null=True,verbose_name=_('Account Name'))
    legalname =  models.CharField(max_length= 255,null=True)
    address1       = models.CharField(max_length=50, null=True,verbose_name=_('Address Line 1'),blank = True)
    address2       = models.CharField(max_length=50, null=True,verbose_name=_('Address Line 2'),blank = True)
    addressfloorno =     models.CharField(max_length= 255,null= True,blank = True)
    addressstreet =     models.CharField(max_length= 255,null= True,blank = True)
    gstintype =        models.CharField(max_length= 255,null= True)
    blockstatus = models.CharField(max_length= 10,null= True,verbose_name='Block Status')
    dateofreg = models.DateTimeField(verbose_name='Date of Registration',null = True)
    dateofdreg = models.DateTimeField(verbose_name='Date of De Regitration',null = True)
    country       = models.ForeignKey(Country,null=True,on_delete=models.CASCADE)
    state       = models.ForeignKey(to=State,on_delete=models.CASCADE,null=True)
    district    = models.ForeignKey(to=District,on_delete=models.CASCADE,null=True)
    city       = models.ForeignKey(to=City,on_delete=models.CASCADE,null=True)
    openingbcr = models.DecimalField(max_digits=14, decimal_places=2,null=True,blank=True,verbose_name=_('Opening Balance Cr'))
    openingbdr = models.DecimalField(max_digits=14, decimal_places=2,null=True,blank=True,verbose_name=_('Opening Balance Dr'))
    contactno       =models.CharField(max_length=50, null=True,blank=True,verbose_name=_('Contact no'))
    contactno2       =models.CharField(max_length=50, null=True,blank=True,verbose_name=_('Contact no2'))
    pincode       =models.CharField(max_length=50, null=True,verbose_name=_('Pincode'))
    emailid       = models.CharField(max_length=50, null=True,blank=True,verbose_name=_('Email id'))
    agent       = models.CharField(max_length=50, null=True,blank=True,verbose_name=_('Agent/Group'))
    pan       = models.CharField(max_length=50, null=True,verbose_name=_('PAN'),blank = True)
    tobel10cr       = models.BooleanField(verbose_name=_('Turnover below 10 lac'),null=True)
    approved       = models.BooleanField(verbose_name=_('Wheather aproved'),null=True)
    tdsno       = models.CharField(max_length=50, null=True,blank=True,verbose_name=_('Tds A/c No'))
    entity = models.ForeignKey(Entity,null=True,on_delete=models.CASCADE,)
    rtgsno          = models.CharField(max_length=50, null=True,blank=True,verbose_name=_('Rtgs no'))
    bankname          = models.CharField(max_length=50, null=True,blank=True,verbose_name=_('Bank Name'))
    Adhaarno          = models.CharField(max_length=50, null=True,blank=True,verbose_name=_('Adhaar No'))
    saccode          = models.CharField(max_length=50, null=True,blank=True,verbose_name=_('SAC Code'))
    contactperson       = models.CharField(max_length=50, null=True,blank=True,verbose_name=_('Contact Person'))
    deprate             = models.DecimalField(max_digits=14, decimal_places=2,null=True,blank=True,verbose_name=_('Depreciaion Rate'))
    tdsrate             = models.DecimalField(max_digits=14, decimal_places=2,null=True,blank=True,verbose_name=_('TDS Rate'))
    gstshare            = models.DecimalField(max_digits=14, decimal_places=2,null=True,blank=True,verbose_name=_('Adhaar No'))
    quanity1            = models.IntegerField(verbose_name=_('Quanity 1'),null=True,blank=True)
    quanity2            = models.IntegerField(verbose_name=_('Quanity 2'),null=True,blank=True)
    BanKAcno            = models.IntegerField(verbose_name=_('Bank A/c No'),null=True,blank=True)
    composition         = models.BooleanField(verbose_name=_('Bank A/c No'),null=True,blank=True)
    canbedeleted        = models.BooleanField(verbose_name=_('Can be deleted'),default = True)
    accounttype         =     models.ForeignKey(to = accounttype, on_delete= models.SET_NULL,null = True)
    sharepercentage             = models.DecimalField(max_digits=14, decimal_places=2,null=True,blank=True,verbose_name=_('Share Percentage'))
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True,)

    def __str__(self):
        return f'{self.accountname} , {self.gstno}'

    class Meta:
        verbose_name = _('Account')
        verbose_name_plural = _('Accounts')


# class account_detials1(TrackingModel):
#     account = models.OneToOneField(account,on_delete=models.CASCADE,primary_key=True)
#     accountno       = models.CharField(max_length=50, null=True,verbose_name=_('Account no'))
#     rtgsno          = models.CharField(max_length=50, null=True,verbose_name=_('Rtgs no'))
#     bankname          = models.CharField(max_length=50, null=True,verbose_name=_('Bank Name'))
#     Adhaarno          = models.CharField(max_length=50, null=True,verbose_name=_('Adhaar No'))
#     saccode          = models.CharField(max_length=50, null=True,verbose_name=_('SAC Code'))
#     owner = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True,default=1,blank=True)
#     class Meta:
#         verbose_name = _('Account Detail1')
#         verbose_name_plural = _('Account Details1')

# class account_detials2(TrackingModel):
#     account = models.OneToOneField(account,on_delete=models.CASCADE,primary_key=True)
#     contactperson       = models.CharField(max_length=50, null=True,verbose_name=_('Contact Person'))
#     deprate             = models.DecimalField(max_digits=14, decimal_places=2,default=True,blank=True,verbose_name=_('Depreciaion Rate'))
#     tdsrate             = models.DecimalField(max_digits=14, decimal_places=2,default=True,blank=True,verbose_name=_('TDS Rate'))
#     gstshare            = models.DecimalField(max_digits=14, decimal_places=2,default=True,blank=True,verbose_name=_('Adhaar No'))
#     quanity1            = models.IntegerField(verbose_name=_('Quanity 1'))
#     quanity1            = models.IntegerField(verbose_name=_('Quanity 2'))
#     BanKAcno            = models.IntegerField(verbose_name=_('Bank A/c No'))
#     composition         = models.BooleanField(verbose_name=_('Bank A/c No'))
#     owner = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True,default=1,blank=True)

#     class Meta:
#         verbose_name = _('Account Detail2')
#         verbose_name_plural = _('Account Details2')


    





