from django.db import models
from django.db.models.fields import NullBooleanField
from helpers.models import TrackingModel
from Authentication.models import User
from geography.models import country,state,district,city
#from Authentication.models import User 

# Create your models here.

class unitType(models.Model):
    UnitName =    models.CharField(max_length= 255)
    UnitDesc =    models.TextField()
    createdby = models.ForeignKey(to= 'Authentication.User', on_delete= models.CASCADE,null=True,default=1,blank=True)


    def __str__(self):
        return f'{self.UnitName}'
    


class Constitution(models.Model):
    constitutionname =    models.CharField(max_length= 255)
    constitutiondesc =    models.TextField()
    createdby = models.ForeignKey(to= 'Authentication.User', on_delete= models.CASCADE,null=True,default=1,blank=True)


    def __str__(self):
        return f'{self.constitutionname}'




        


class entity(TrackingModel):
    entityname =  models.CharField(max_length= 255)
    address =     models.CharField(max_length= 255)
    ownername =   models.CharField(max_length= 255)
    country =     models.ForeignKey(country, on_delete=models.CASCADE,null= True)
    state =       models.ForeignKey(state, on_delete=models.CASCADE,null= True)
    district =    models.ForeignKey(district, on_delete=models.CASCADE,null= True)
    city =        models.ForeignKey(city, on_delete=models.CASCADE,null= True)
    pincode =    models.CharField(max_length= 255,null= True)
    phoneoffice = models.CharField(max_length= 255)
    phoneresidence = models.CharField(max_length= 255)
    panno =        models.CharField(max_length= 255,null= True)
    tds =           models.CharField(max_length= 255,null= True)
    tdscircle =        models.CharField(max_length= 255,null= True)
    email =    models.CharField(max_length= 255,null= True)
    tcs206c1honsale  = models.BooleanField(blank =True,null = True)
   # tds194qonsale  = models.BooleanField(blank =True,null = True)
    gstno =        models.CharField(max_length= 255,null= True)
    gstintype =        models.CharField(max_length= 255,null= True)
    user = models.ManyToManyField(to = 'Authentication.User',related_name='uentity',null=True,default=[1])
    #createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True,default=1,blank=True)
    

    
    def __str__(self):
        return f'{self.entityname}'
    

class subentity(TrackingModel):
    subentityname =  models.CharField(max_length= 255)
    address =     models.CharField(max_length= 255)
   # ownername =   models.CharField(max_length= 255)
    country =     models.ForeignKey(country, on_delete=models.CASCADE,null= True)
    state =       models.ForeignKey(state, on_delete=models.CASCADE,null= True)
    district =    models.ForeignKey(district, on_delete=models.CASCADE,null= True)
    city =        models.ForeignKey(city, on_delete=models.CASCADE,null= True)
    pincode =    models.CharField(max_length= 255,null= True)
    phoneoffice = models.CharField(max_length= 255,null= True)
    phoneresidence = models.CharField(max_length= 255,null= True)
    email =    models.CharField(max_length= 255,null= True)
    entity =    models.ForeignKey(to= entity, on_delete= models.CASCADE,null=True,related_name='subentity',)

    

    
    def __str__(self):
        return f'{self.subentityname}'
    


class entityfinancialyear(TrackingModel):
    entity =    models.ForeignKey(to= entity, on_delete= models.CASCADE,null=True,related_name='fy',)
    desc =      models.CharField(max_length= 255,null= True,verbose_name='description')
    finstartyear =      models.DateTimeField(verbose_name='Fin Start Date',null = True)
    finendyear =        models.DateTimeField(verbose_name='Fin End Date',null = True)
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True,)


    def __str__(self):
        return f'{self.entity}'
    

class entityconstitution(TrackingModel):
    entity =    models.ForeignKey(to= entity, on_delete= models.CASCADE,null=True,related_name='constitution',)
    constitution =    models.ForeignKey(to= Constitution, on_delete= models.CASCADE,null=True,)
    shareholder =      models.CharField(max_length= 255,null= True,verbose_name='shareholder')
    pan =      models.CharField(max_length= 25,null= True,verbose_name='pan')
    sharepercentage = models.DecimalField(max_digits=10, decimal_places=2,null=True,blank=True,verbose_name='Share Percentage')
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True,)


    def __str__(self):
        return f'{self.entity}'






class entity_details(models.Model): 
    entity = models.OneToOneField(entity,
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








