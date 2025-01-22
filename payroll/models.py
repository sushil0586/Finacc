from django.db import models
#import imp
#from sre_parse import Verbose
from django.db import models
from django.forms import DateField
from helpers.models import TrackingModel
from Authentication.models import User
from financial.models import account,accountHead
from inventory.models import Product
from entity.models import Entity
from inventory.models import Product
from django.db.models import Sum 
import datetime
from geography.models import Country,State,District,City




class department(TrackingModel):

    departmentname = models.CharField(max_length= 200,verbose_name= 'department name')
    departmentcode = models.CharField(max_length= 200,verbose_name= 'department code')
    entity = models.ForeignKey(Entity,on_delete=models.CASCADE,verbose_name= 'entity',null= True)
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True)


    def __str__(self):
        return f'{self.departmentname}'
    

class designation(TrackingModel):

    designationname = models.CharField(max_length= 200,verbose_name= 'designation name')
    designationcode = models.CharField(max_length= 200,verbose_name= 'designation code')
    entity = models.ForeignKey(Entity,on_delete=models.CASCADE,verbose_name= 'entity',null= True)
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True)


    def __str__(self):
        return f'{self.designationname}'








    

class salarycomponent(TrackingModel):

    salarycomponentname = models.CharField(max_length= 200,verbose_name= 'Component name')
    salarycomponentcode = models.CharField(max_length= 200,verbose_name= 'Component code')
    componentperiod = models.IntegerField(verbose_name='period',default = 0)
    componenttype = models.IntegerField(verbose_name='Component type',default = 0)
    calculationtype = models.IntegerField(verbose_name='calculation type',default = 0)
    defaultpercentage =  models.DecimalField(max_digits=10, decimal_places=2,default=0,verbose_name= 'default percentage')
    entity = models.ForeignKey(Entity,on_delete=models.CASCADE,verbose_name= 'entity',null= True)
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True)


    def __str__(self):
        return f'{self.salarycomponentname}'
    

class employee(TrackingModel):

    employee = models.OneToOneField(to= User, on_delete= models.CASCADE,primary_key=True)
    employeeid = models.CharField(max_length= 200,verbose_name= 'employee id')
    dateofjoining = models.DateTimeField(verbose_name='Date Of Joining',auto_now_add=True, blank=True)
    department = models.ForeignKey(department,on_delete=models.CASCADE,verbose_name= 'department',null= True)
    designation = models.ForeignKey(designation,on_delete=models.CASCADE,verbose_name= 'designation',null= True)
    reportingmanager = models.ForeignKey("self", on_delete= models.CASCADE,null=True,verbose_name='Reporting Manager',related_name='rmanager')
    bankname = models.CharField(max_length= 50,verbose_name= 'Bank Name',blank = True,null=True)
    bankaccountno = models.CharField(max_length= 20,verbose_name= 'Bank Account No',blank = True,null=True)
    pan = models.CharField(max_length= 20,verbose_name= 'Pan Card details',blank = True,null=True)
    address1       = models.CharField(max_length=50, null=True,verbose_name='Address Line 1',blank = True)
    address2       = models.CharField(max_length=50, null=True,verbose_name='Address Line 2',blank = True)
    country       = models.ForeignKey(Country,on_delete=models.CASCADE,null=True)
    state       = models.ForeignKey(to=State,on_delete=models.CASCADE,null=True)
    district    = models.ForeignKey(to=District,on_delete=models.CASCADE,null=True)
    city       = models.ForeignKey(to=City,on_delete=models.CASCADE,null=True)
    entity = models.ForeignKey(Entity,on_delete=models.CASCADE,verbose_name= 'entity',null= True)
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True,related_name='employeeuser')


    
class employeesalary(TrackingModel):

    employee = models.ForeignKey(to= employee, on_delete= models.CASCADE,null=True)
    scomponent = models.ForeignKey(to= salarycomponent, on_delete= models.CASCADE,null=True)
    percentageofctc =  models.DecimalField(max_digits=10, decimal_places=2,default=0,verbose_name= 'percentage of ctc')
    salaryvalue=  models.DecimalField(max_digits=10, decimal_places=2,default=0,verbose_name= 'Component value')
    monthlysalaryvalue=  models.DecimalField(max_digits=10, decimal_places=2,default=0,verbose_name= 'Monthly Component value')
    entity = models.ForeignKey(Entity,on_delete=models.CASCADE,verbose_name= 'entity',null= True)
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
    entity = models.ForeignKey(Entity,on_delete=models.CASCADE,verbose_name= 'entity',null= True)
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True,related_name='salaryuser')

class salarytransdetails(TrackingModel):
    salarytrans = models.ForeignKey(to= salarytrans, on_delete= models.CASCADE,null=True)
    scomponent = models.ForeignKey(to= salarycomponent, on_delete= models.CASCADE,null=True)
    salaryamountexpected =  models.DecimalField(max_digits=10, decimal_places=2,default=0,verbose_name= 'Salary amount Expected')
    salaryamountactual =  models.DecimalField(max_digits=10, decimal_places=2,default=0,verbose_name= 'Salary amount Actual')
    arrear =  models.DecimalField(max_digits=10, decimal_places=2,default=0,verbose_name= 'arrear')
    totalamount =  models.DecimalField(max_digits=10, decimal_places=2,default=0,verbose_name= 'Salary amount Total')
    entity = models.ForeignKey(Entity,on_delete=models.CASCADE,verbose_name= 'entity',null= True)
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True)

    



    



