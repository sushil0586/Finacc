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
        return f'{self.departmentname}'  # department
    

class designation(TrackingModel):

    designationname = models.CharField(max_length= 200,verbose_name= 'designation name')
    designationcode = models.CharField(max_length= 200,verbose_name= 'designation code')
    entity = models.ForeignKey(Entity,on_delete=models.CASCADE,verbose_name= 'entity',null= True)
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True)


    def __str__(self):
        return f'{self.designationname}'


class TaxRegime(models.Model):
    name = models.CharField(max_length=50)  # e.g., 'Old', 'New'
    assessment_year = models.CharField(max_length=9)  # e.g., '2025-26'
    rebate_limit = models.FloatField()
    standard_deduction = models.FloatField(default=50000)

    def __str__(self):
            return f'{self.name} - {self.assessment_year}'

class InvestmentSection(models.Model):
    section_code = models.CharField(max_length=10)  # e.g., '80C'
    section_name = models.CharField(max_length=255)
    max_limit = models.FloatField(null=True, blank=True)
    parent_section = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL)
    is_tax_exempt = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f'{self.section_code} - {self.section_name}'


class CalculationType(models.Model):
    name = models.CharField(max_length=50)  # e.g., Fixed, Percentage, Formula

    def __str__(self):
        return self.name

class BonusFrequency(models.Model):
    name = models.CharField(max_length=50)  # e.g., Monthly, Quarterly, Yearly, Adhoc

  
    def __str__(self):
        return self.name

class CalculationValue(models.Model):
    value = models.FloatField()
    description = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return f'{self.value} - {self.description}'
    



class ComponentType(models.Model):
    code = models.CharField(max_length=20, unique=True)  # e.g., earning, deduction
    name = models.CharField(max_length=50)  # e.g., Earning, Deduction, Bonus

    def __str__(self):
        return f'{self.name}'


class PayrollComponent(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50)
    component_type = models.ForeignKey(ComponentType, on_delete=models.SET_NULL, null=True)
    calculation_type = models.ForeignKey(CalculationType, on_delete=models.SET_NULL, null=True)
   # calculation_value = models.ForeignKey(CalculationValue, on_delete=models.SET_NULL, null=True, blank=True)
    is_taxable = models.BooleanField(default=True)
    is_mandatory = models.BooleanField(default=True)
    is_basic = models.BooleanField(default=True)
    entity = models.ForeignKey(Entity, on_delete=models.CASCADE)
    bonus_frequency = models.ForeignKey(BonusFrequency, on_delete=models.SET_NULL, null=True, blank=True)
    formula_expression = models.TextField(null=True, blank=True)


    def __str__(self):
        return f'{self.name}'


class EntityPayrollComponentConfig(models.Model):
    entity = models.ForeignKey(Entity, on_delete=models.CASCADE)
    component = models.ForeignKey(PayrollComponent, on_delete=models.CASCADE)
    default_value = models.FloatField()
    selected_amount = models.FloatField(null=True, blank=True)
    min_value = models.FloatField(null=True, blank=True)
    max_value = models.FloatField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f'{self.entity} - {self.component}'









    

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
    

# class employee(TrackingModel):

#     employee = models.OneToOneField(to= User, on_delete= models.CASCADE,primary_key=True)
   
   
#     tax_regime = models.ForeignKey(TaxRegime, on_delete=models.SET_NULL, null=True)
#     firstname = models.CharField(max_length= 200,verbose_name= 'firstname',null=True)
#     lastname = models.CharField(max_length= 200,verbose_name= 'lastname',null=True)
#     middlename = models.CharField(max_length= 200,verbose_name= 'middlename',null=True)
#     email = models.CharField(max_length= 200,verbose_name= 'email',null=True)
#     password = models.CharField(max_length= 200,verbose_name= 'email',null=True)
#     employeeid = models.CharField(max_length= 200,verbose_name= 'employee id')
#     dateofjoining = models.DateTimeField(verbose_name='Date Of Joining',auto_now_add=True, blank=True)
#     department = models.ForeignKey(department,on_delete=models.CASCADE,verbose_name= 'department',null= True)
#     designation = models.ForeignKey(designation,on_delete=models.CASCADE,verbose_name= 'designation',null= True)
#     reportingmanager = models.ForeignKey("self", on_delete= models.CASCADE,null=True,blank = True,verbose_name='Reporting Manager',related_name='rmanager')
#     bankname = models.CharField(max_length= 50,verbose_name= 'Bank Name',blank = True,null=True)
#     bankaccountno = models.CharField(max_length= 20,verbose_name= 'Bank Account No',blank = True,null=True)
#     pan = models.CharField(max_length= 20,verbose_name= 'Pan Card details',blank = True,null=True)
#     address1       = models.CharField(max_length=50, null=True,verbose_name='Address Line 1',blank = True)
#     address2       = models.CharField(max_length=50, null=True,verbose_name='Address Line 2',blank = True)
#     country       = models.ForeignKey(Country,on_delete=models.CASCADE,null=True)
#     state       = models.ForeignKey(to=State,on_delete=models.CASCADE,null=True)
#     district    = models.ForeignKey(to=District,on_delete=models.CASCADE,null=True)
#     city       = models.ForeignKey(to=City,on_delete=models.CASCADE,null=True)
#     entity = models.ForeignKey(Entity,on_delete=models.CASCADE,verbose_name= 'entity',null= True)
#     createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True,related_name='employeeuser')

#     def __str__(self):
#         return f'{self.employeeid}'
    

class employeenew(TrackingModel):

    # # employee = models.OneToOneField(to= User, on_delete= models.CASCADE,primary_key=True)
    # id = models.BigAutoField(primary_key=True)  # Django default
    # employee = models.OneToOneField(to=User, on_delete=models.CASCADE)
    tax_regime = models.ForeignKey(TaxRegime, on_delete=models.SET_NULL, null=True)
    firstname = models.CharField(max_length= 200,verbose_name= 'firstname',null=True)
    lastname = models.CharField(max_length= 200,verbose_name= 'lastname',null=True)
    middlename = models.CharField(max_length= 200,verbose_name= 'middlename',null=True)
    email = models.CharField(max_length= 200,verbose_name= 'email',null=True)
    password = models.CharField(max_length= 200,verbose_name= 'email',null=True)
    employeeid = models.CharField(max_length= 200,verbose_name= 'employee id')
    dateofjoining = models.DateTimeField(verbose_name='Date Of Joining',auto_now_add=True, blank=True)
    department = models.ForeignKey(department,on_delete=models.CASCADE,verbose_name= 'department',null= True)
    designation = models.ForeignKey(designation,on_delete=models.CASCADE,verbose_name= 'designation',null= True)
    reportingmanager = models.ForeignKey("self", on_delete= models.CASCADE,null=True,blank = True,verbose_name='Reporting Manager',related_name='rmanager')
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

    def __str__(self):
        return f'{self.employeeid}'


class EmployeePayrollComponent(models.Model):
    employee = models.ForeignKey(employeenew, on_delete=models.CASCADE)
    component = models.ForeignKey(PayrollComponent, on_delete=models.CASCADE)
    default_value = models.FloatField()
    is_opted_in = models.BooleanField(default=True)
    overridden_value = models.FloatField(null=True, blank=True)
    final_value = models.FloatField()
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)


    
class employeesalary(TrackingModel):

    employee = models.ForeignKey(to= employeenew, on_delete= models.CASCADE,null=True)
    
    scomponent = models.ForeignKey(to= salarycomponent, on_delete= models.CASCADE,null=True)
    percentageofctc =  models.DecimalField(max_digits=10, decimal_places=2,default=0,verbose_name= 'percentage of ctc')
    salaryvalue=  models.DecimalField(max_digits=10, decimal_places=2,default=0,verbose_name= 'Component value')
    monthlysalaryvalue=  models.DecimalField(max_digits=10, decimal_places=2,default=0,verbose_name= 'Monthly Component value')
    entity = models.ForeignKey(Entity,on_delete=models.CASCADE,verbose_name= 'entity',null= True)
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True,related_name='salaryuser1')


class salarytrans(TrackingModel):
    employee = models.ForeignKey(to= employeenew, on_delete= models.CASCADE,null=True)
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


class EmployeeInvestment(models.Model):
    employee = models.ForeignKey(employeenew, on_delete=models.CASCADE)
    section = models.ForeignKey(InvestmentSection, on_delete=models.CASCADE)
    sub_category = models.CharField(max_length=100, null=True, blank=True)
    amount = models.FloatField()
    declared_on = models.DateField(auto_now_add=True)
    document = models.FileField(upload_to='investment_proofs/', null=True, blank=True)
    proof_status = models.CharField(
        max_length=20,
        choices=[('submitted', 'Submitted'), ('approved', 'Approved'), ('rejected', 'Rejected'), ('pending', 'Pending')],
        default='pending'
    )
    remarks = models.TextField(null=True, blank=True)
    is_locked = models.BooleanField(default=False)

class EmployeeInvestmentSummary(models.Model):
    employee = models.ForeignKey(employeenew, on_delete=models.CASCADE)
    total_declared = models.FloatField()
    total_approved = models.FloatField()
    effective_taxable_income = models.FloatField()
    assessment_year = models.CharField(max_length=10)

class EmployeeLoan(models.Model):
    employee = models.ForeignKey(employeenew, on_delete=models.CASCADE)
    loan_type = models.CharField(max_length=50)  # e.g., 'Advance', 'Salary'
    amount = models.FloatField()
    balance = models.FloatField()
    emi_amount = models.FloatField()

    



    



