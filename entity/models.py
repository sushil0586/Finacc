from django.db import models
from django.db.models.fields import NullBooleanField
from helpers.models import TrackingModel
from Authentication.models import User,MainMenu,Submenu
from geography.models import Country,State,District,City
from django.utils.dateformat import DateFormat
#from Authentication.models import User 

# Create your models here.

class unitType(models.Model):
    UnitName =    models.CharField(max_length= 100)
    UnitDesc =    models.CharField(max_length= 255)
    #createdby = models.ForeignKey(to= 'Authentication.User', on_delete= models.CASCADE,null=True,default=1,blank=True)


    def __str__(self):
        return f'{self.UnitName}'
    

class GstRegitrationTypes(models.Model):
    Name =           models.CharField(max_length= 100)
    Description =    models.CharField(max_length= 255)
    #createdby = models.ForeignKey(to= 'Authentication.User', on_delete= models.CASCADE,null=True,default=1,blank=True)


    def __str__(self):
        return f'{self.Name}'
    
class OwnerShipTypes(models.Model):
    Name =           models.CharField(max_length= 100)
    Description =    models.CharField(max_length= 255)
    #createdby = models.ForeignKey(to= 'Authentication.User', on_delete= models.CASCADE,null=True,default=1,blank=True)


    def __str__(self):
        return f'{self.Name}'
    

    


class Constitution(models.Model):
    constitutionname =    models.CharField(max_length= 255)
    constitutiondesc =    models.TextField()
    constcode =    models.CharField(max_length= 255)
    createdby = models.ForeignKey(to= 'Authentication.User', on_delete= models.CASCADE,null=True,default=1,blank=True)


    def __str__(self):
        return f'{self.constitutionname}'
    

class Bankdetails(TrackingModel):
    bankname =  models.CharField(max_length= 100)
    bankcode =  models.CharField(max_length= 100,null=True)
    ifsccode =  models.CharField(max_length= 100,null=True)

    def __str__(self):
        return f'{self.bankname}'





        


class Entity(TrackingModel):
    entityname =  models.CharField(max_length= 100)
    entitydesc =  models.CharField(max_length= 255,null=True)
    legalname =  models.CharField(max_length= 100,null=True)
    unitType =        models.ForeignKey(unitType, on_delete=models.CASCADE,null= True)
    GstRegitrationType =        models.ForeignKey(GstRegitrationTypes, on_delete=models.CASCADE,null= True)
    website = models.URLField(blank=True, null=True)
    address =     models.CharField(max_length= 100)
    address2 =     models.CharField(max_length= 100,null= True,blank = True)
    addressfloorno =     models.CharField(max_length= 50,null= True,blank = True)
    addressstreet =     models.CharField(max_length= 100,null= True,blank = True)
    ownername =   models.CharField(max_length= 100,null= True)
    country =     models.ForeignKey(Country, on_delete=models.CASCADE,null= True)
    state =       models.ForeignKey(State, on_delete=models.CASCADE,null= True)
    district =    models.ForeignKey(District, on_delete=models.CASCADE,null= True)
    city =        models.ForeignKey(City, on_delete=models.CASCADE,null= True)
    bank =        models.ForeignKey(Bankdetails, on_delete=models.CASCADE,null= True)
    bankacno =    models.CharField(max_length= 50,null= True)
    ifsccode     =    models.CharField(max_length= 50,null= True)
    pincode =    models.CharField(max_length= 50,null= True)
    phoneoffice = models.CharField(max_length= 20)
    phoneresidence = models.CharField(max_length= 20)
    panno =        models.CharField(max_length= 20,null= True)
    tds =           models.CharField(max_length= 20,null= True)
    tdscircle =        models.CharField(max_length= 20,null= True)
    email =    models.CharField(max_length= 50,null= True)
    tcs206c1honsale  = models.BooleanField(blank =True,null = True)
   # tds194qonsale  = models.BooleanField(blank =True,null = True)
    gstno =        models.CharField(max_length= 20,null= True)
    gstintype =        models.CharField(max_length= 20,null= True)
    blockstatus = models.CharField(max_length= 10,null= True,verbose_name='Block Status')
    dateofreg = models.DateTimeField(verbose_name='Date of Registration',null = True)
    dateofdreg = models.DateTimeField(verbose_name='Date of De Regitration',null = True)
    const =    models.ForeignKey(to= Constitution, on_delete= models.CASCADE,null=True)
    createdby =  models.ForeignKey(User, on_delete=models.CASCADE,null= True)
    #createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True,default=1,blank=True)
    

    
    def __str__(self):
        return f'{self.entityname}'
    


    

class BankAccount(models.Model):
    entity = models.ForeignKey(to= 'Entity', on_delete=models.CASCADE, related_name='bank_accounts')
    bank_name = models.CharField(max_length=100)
    branch = models.CharField(max_length=100)
    account_number = models.CharField(max_length=20)
    ifsc_code = models.CharField(max_length=11)
    account_type = models.CharField(max_length=20, choices=[('current', 'Current'), ('savings', 'Savings')])
    is_primary = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.bank_name} - {self.account_number}"
    

class GstAccountsdetails(TrackingModel):
    gstin = models.CharField(max_length= 25,null= True)
    tradeName = models.CharField(max_length= 255,null= True)
    legalName = models.CharField(max_length= 255,null= True)
    addrBnm = models.CharField(max_length= 255,null= True)
    addrBno = models.CharField(max_length= 255,null= True)
    addrFlno = models.CharField(max_length= 255,null= True)
    addrSt = models.CharField(max_length= 255,null= True)
    addrLoc =  models.ForeignKey(City, on_delete=models.CASCADE,null= True)
    stateCode = models.ForeignKey(State, on_delete=models.CASCADE,null= True)
    district =    models.ForeignKey(District, on_delete=models.CASCADE,null= True)
    country =     models.ForeignKey(Country, on_delete=models.CASCADE,null= True)
    addrPncd = models.CharField(max_length= 10,null= True)
    txpType = models.CharField(max_length= 25,null= True)
    status = models.CharField(max_length= 25,null= True)
    blkStatus = models.CharField(max_length= 10,null= True)
    dtReg = models.DateTimeField(verbose_name='Date of registration',null = True)
    dtDReg = models.DateTimeField(verbose_name='Date of De registration',null = True)

    

class subentity(TrackingModel):
    subentityname =  models.CharField(max_length= 255)
    address =     models.CharField(max_length= 255)
    country =     models.ForeignKey(Country, on_delete=models.CASCADE,null= True)
    state =       models.ForeignKey(State, on_delete=models.CASCADE,null= True)
    district =    models.ForeignKey(District, on_delete=models.CASCADE,null= True)
    city =        models.ForeignKey(City, on_delete=models.CASCADE,null= True)
    pincode =    models.CharField(max_length= 255,null= True)
    phoneoffice = models.CharField(max_length= 255,null= True)
    phoneresidence = models.CharField(max_length= 255,null= True)
    email =    models.CharField(max_length= 255,null= True)
    ismainentity  = models.BooleanField(blank =True,null = True)
    entity =    models.ForeignKey(to= Entity, on_delete= models.CASCADE,null=True,related_name='subentity',)

    

    
    def __str__(self):
        return f'{self.subentityname}'
    


class entityfinancialyear(TrackingModel):
    entity =    models.ForeignKey(to= Entity, on_delete= models.CASCADE,null=True,related_name='fy',)
    desc =      models.CharField(max_length= 255,null= True,verbose_name='description')
    finstartyear =      models.DateTimeField(verbose_name='Fin Start Date',null = True)
    finendyear =        models.DateTimeField(verbose_name='Fin End Date',null = True)
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True,)


    def __str__(self):
        entity_str = str(self.entity) if self.entity else 'No Entity'
        if self.finstartyear and self.finendyear:
            
            start_str = DateFormat(self.finstartyear).format('m-Y')
            end_str = DateFormat(self.finendyear).format('m-Y')
            return f'{entity_str} | {start_str} - {end_str}'
        return f'{entity_str} | Financial Year'
    

class entityconstitution(TrackingModel):
    entity =    models.ForeignKey(to= Entity, on_delete=models.CASCADE,null=True,related_name='constitution',)
    shareholder =      models.CharField(max_length= 255,null= True,verbose_name='shareholder')
    pan =      models.CharField(max_length= 25,null= True,verbose_name='pan')
    sharepercentage = models.DecimalField(max_digits=10, decimal_places=2,null=True,blank=True,verbose_name='Share Percentage')
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True,)


    def __str__(self):
        return f'{self.entity}'
    
class EntityOwnership(models.Model):
    # OWNERSHIP_TYPE_CHOICES = [
    #     ('owner', 'Owner'),
    #     ('partner', 'Partner'),
    #     ('shareholder', 'Shareholder'),
    #     ('trustee', 'Trustee'),
    #     ('board_member', 'Board Member'),
    #     ('official', 'Government Official'),
    # ]
    OwnerShipType = models.ForeignKey(OwnerShipTypes, on_delete=models.CASCADE, related_name='ownerships')
    entity = models.ForeignKey(Entity, on_delete=models.CASCADE, related_name='ownerships')
    name = models.CharField(max_length=100)
    email = models.EmailField(blank=True, null=True)
    mobile = models.CharField(max_length=15, blank=True, null=True)
    pan_number = models.CharField(max_length=10, blank=True, null=True)
    aadhaar_number = models.CharField(max_length=12, blank=True, null=True)
    share_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    capital_contribution = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    is_primary = models.BooleanField(default=False)
    designation = models.CharField(max_length=100, blank=True, null=True)
    remarks = models.TextField(blank=True)

    def __str__(self):
        return f"{self.name} - {self.ownership_type}"
    








class entity_details(models.Model): 
    entity = models.OneToOneField(Entity,
        on_delete=models.CASCADE,
        primary_key=True,)
    style =        models.CharField(max_length= 255,null= True)
    commodity =        models.CharField(max_length= 255,null= True)
    weightDecimal =        models.CharField(max_length= 255,null= True)
    email =        models.EmailField(max_length= 24,null= True)
    registrationno =        models.CharField(max_length= 255,null= True)
    division =        models.CharField(max_length= 255,null= True)
    collectorate =        models.CharField(max_length= 255,null= True)
    range =        models.CharField(max_length= 255,null= True)
    adhaarudyog =        models.CharField(max_length= 255,null= True)
    cinno =        models.CharField(max_length= 255,null= True)
    jobwork =        models.CharField(max_length= 255,null= True)
    gstno =        models.CharField(max_length= 255,null= True)
    gstintype =        models.CharField(max_length= 255,null= True)
    esino =        models.CharField(max_length= 255,null= True)

# class entity_user(TrackingModel):
#     entity = models.ForeignKey(entity,related_name='entityUser',
#         on_delete=models.CASCADE)
#     user = models.ForeignKey(to= User,related_name='userentity', on_delete= models.CASCADE)
#     createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,related_name='%(class)s_requests_created',default=1)

#     class Meta:
#         constraints = [
#         models.UniqueConstraint(fields=['entity', 'user'], name='unique entity_user')
#     ]
    

class Role(TrackingModel):
    rolename = models.CharField(max_length=150)
    roledesc = models.CharField(max_length=150)
    rolelevel = models.IntegerField()
    entity =    models.ForeignKey(to= Entity, on_delete= models.CASCADE,null=True)

    def __str__(self):
        return f'{self.rolename} - {self.entity}'

    

class Rolepriv(TrackingModel):
    role =     models.ForeignKey(Role,null= True,on_delete= models.CASCADE,related_name='submenudetails')
    submenu =     models.ForeignKey(Submenu,null= True,on_delete= models.CASCADE)
    entity =    models.ForeignKey(to= Entity, on_delete= models.CASCADE,null=True)
 


    class Meta:
        verbose_name = ('Role Priveledge')
        verbose_name_plural = ('Role Priveledges')


    
    def __str__(self):
        return f'{self.submenu} - {self.role} - {self.entity}'
    


class Userrole(TrackingModel):
    role =     models.ForeignKey(Role,null= True,on_delete= models.CASCADE,related_name='userrole')
    user =     models.ForeignKey(User,null= True,on_delete= models.CASCADE)
    entity =    models.ForeignKey(to= Entity, on_delete= models.CASCADE,null=True)

    def __str__(self):
        return f'{self.role}'
    


class Mastergstdetails(TrackingModel):
    email = models.CharField(max_length=100, null=True,verbose_name='email')
    username = models.CharField(max_length=100, null=True,verbose_name='username')
    password = models.CharField(max_length=100, null=True,verbose_name='password')
    client_id = models.CharField(max_length=200, null=True,verbose_name='clientid')
    client_secret = models.CharField(max_length=200, null=True,verbose_name='client_secret')
    gstin = models.CharField(max_length=20, null=True,verbose_name='gstin')
    entity =    models.ForeignKey(to= Entity, on_delete= models.CASCADE,null=True)

    def __str__(self):
         return f'{self.username}'
    

class Godown(models.Model):
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=50, unique=True)
    address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    pincode = models.CharField(max_length=10)
    capacity = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = "Godown"
        verbose_name_plural = "Godowns"

    def __str__(self):
        return f"{self.name} ({self.code})"








