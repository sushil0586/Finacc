from django.db import models
import imp
#from sre_parse import Verbose
from django.db import models
from django.forms import DateField
from helpers.models import TrackingModel
from Authentication.models import User
from financial.models import account,accountHead
from inventory.models import Product
from entity.models import entity
from inventory.models import Product
from django.db.models import Sum 
import datetime








    

class salarycomponent(TrackingModel):

    salarycomponentname = models.CharField(max_length= 200,verbose_name= 'Component name')
    salarycomponentcode = models.CharField(max_length= 200,verbose_name= 'Component code')
    componentperiod = models.IntegerField(verbose_name='period',default = 0)
    componenttype = models.IntegerField(verbose_name='Component type',default = 0)
    defaultpercentage =  models.DecimalField(max_digits=10, decimal_places=2,default=0,verbose_name= 'default percentage')
    entity = models.ForeignKey(entity,on_delete=models.CASCADE,verbose_name= 'entity',null= True)
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True)


    def __str__(self):
        return f'{self.salarycomponentname}'
    

class employee(TrackingModel):

    employee = models.OneToOneField(to= User, on_delete= models.CASCADE,primary_key=True)

    entity = models.ForeignKey(entity,on_delete=models.CASCADE,verbose_name= 'entity',null= True)
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True,related_name='employeeuser')


    
class employeesalary(TrackingModel):

    employee = models.ForeignKey(to= employee, on_delete= models.CASCADE,null=True)
    scomponent = models.ForeignKey(to= salarycomponent, on_delete= models.CASCADE,null=True)
    percentageofctc =  models.DecimalField(max_digits=10, decimal_places=2,default=0,verbose_name= 'percentage of ctc')
    salaryvalue=  models.DecimalField(max_digits=10, decimal_places=2,default=0,verbose_name= 'Component value')
    entity = models.ForeignKey(entity,on_delete=models.CASCADE,verbose_name= 'entity',null= True)
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True,related_name='salaryuser1')


class salarytrans(TrackingModel):
    employee = models.ForeignKey(to= employee, on_delete= models.CASCADE,null=True)
    salaryamountexpected =  models.DecimalField(max_digits=10, decimal_places=2,default=0,verbose_name= 'Salary amount Expected')
    salaryamountactual =  models.DecimalField(max_digits=10, decimal_places=2,default=0,verbose_name= 'Salary amount Actual')
    grossearnings =  models.DecimalField(max_digits=10, decimal_places=2,default=0,verbose_name= 'Gross earnings')
    grossdeductions =  models.DecimalField(max_digits=10, decimal_places=2,default=0,verbose_name= 'Gross Deductions')
    netpayable =  models.DecimalField(max_digits=10, decimal_places=2,default=0,verbose_name= 'Net Payabale')
    paiddays =  models.DecimalField(max_digits=10, decimal_places=2,default=0,verbose_name= 'Paid days')
    month =  models.IntegerField(verbose_name='period')
    entity = models.ForeignKey(entity,on_delete=models.CASCADE,verbose_name= 'entity',null= True)
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True,related_name='salaryuser')

class salarytransdetails(TrackingModel):
    salarytrans = models.ForeignKey(to= salarytrans, on_delete= models.CASCADE,null=True)
    scomponent = models.ForeignKey(to= salarycomponent, on_delete= models.CASCADE,null=True)
    salaryamountexpected =  models.DecimalField(max_digits=10, decimal_places=2,default=0,verbose_name= 'Salary amount Expected')
    salaryamountactual =  models.DecimalField(max_digits=10, decimal_places=2,default=0,verbose_name= 'Salary amount Actual')
    arrear =  models.DecimalField(max_digits=10, decimal_places=2,default=0,verbose_name= 'arrear')
    tottalamount =  models.DecimalField(max_digits=10, decimal_places=2,default=0,verbose_name= 'Salary amount Total')
    entity = models.ForeignKey(entity,on_delete=models.CASCADE,verbose_name= 'entity',null= True)
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True)

    



    


