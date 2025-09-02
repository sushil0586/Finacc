from django.db import models
#import imp
#from sre_parse import Verbose
from django.db import models
from django.forms import DateField
from helpers.models import TrackingModel
from Authentication.models import User
from financial.models import account,accountHead
from inventory.models import Product
from entity.models import Entity,Role
from inventory.models import Product
from django.db.models import Sum 
import datetime
from geography.models import Country,State,District,City
from .base import TimeStampedModel, EffectiveDatedModel

#from __future__ import annotations

from decimal import Decimal,InvalidOperation
from typing import Optional

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator,RegexValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.apps import apps
from simple_history.models import HistoricalRecords



class BusinessUnit(TimeStampedModel):
    entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="business_units")
    name = models.CharField(max_length=128)
    class Meta: unique_together = [("entity", "name")]
    def __str__(self): return f"{self.entity.entityname}:{self.name}"

class Department(TimeStampedModel):
    entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="departments", null=True)
    name   = models.CharField(max_length=128, null=True, blank=True)

    class Meta:
        # temporarily remove unique_together to break the bad op chain
        # unique_together = [("entity", "name")]
        pass

    def __str__(self):
        return f"{self.entity.entityname}:{self.name}"


class Location(TimeStampedModel):
    entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="locations")
    name = models.CharField(max_length=128)
    city = models.CharField(max_length=128, blank=True, default="")
    state = models.CharField(max_length=128, blank=True, default="")
    country = models.CharField(max_length=128, blank=True, default="India")
    class Meta: unique_together = [("entity", "name")]
    def __str__(self): return f"{self.entity.entityname}:{self.name}"

class CostCenter(TimeStampedModel):
    entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="cost_centers")
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=128)
    class Meta: unique_together = [("entity", "code")]
    def __str__(self): return f"{self.entity.entityname}:{self.code} — {self.name}"



class OptionSet(TimeStampedModel):
    """
    A named bucket of options, e.g. 'gender', 'employment_type'.
    Global if entity is NULL; can be overridden per entity.
    """
    key = models.CharField(max_length=64, db_index=True)
    entity = models.ForeignKey(Entity, null=True, blank=True, on_delete=models.CASCADE)
    class Meta: unique_together = [("entity", "key")]
    def __str__(self): return f"{self.entity_id or 'GLOBAL'}:{self.key}"

class Option(TimeStampedModel):
    set = models.ForeignKey(OptionSet, on_delete=models.CASCADE, related_name="options")
    code = models.CharField(max_length=64)        # e.g. 'female'
    label = models.CharField(max_length=128)      # e.g. 'Female'
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    extra = models.JSONField(default=dict, blank=True)
    class Meta:
        unique_together = [("set", "code")]
        indexes = [models.Index(fields=["set", "is_active", "sort_order"])]
    def __str__(self): return f"{self.set.key}:{self.code}"







    

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
    name = models.CharField(max_length=50)  # e.g., Fixed, Percentage, x1x

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
    component = models.ForeignKey(PayrollComponent, related_name='configs', on_delete=models.CASCADE)
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
    username = models.CharField(
    ('username'),
        max_length=150,null=True,
       # unique=True,
        help_text=('Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.'),
        #validators=[username_validator],
        error_messages={
            'unique': ("A user with that username already exists."),
        },
    )
    firstname = models.CharField(max_length= 200,verbose_name= 'firstname',null=True)
    lastname = models.CharField(max_length= 200,verbose_name= 'lastname',null=True)
    middlename = models.CharField(max_length= 200,verbose_name= 'middlename',null=True)
    email = models.CharField(max_length= 200,verbose_name= 'email',null=True)
    password = models.CharField(max_length= 200,verbose_name= 'password',null=True)
    employeeid = models.CharField(max_length= 200,verbose_name= 'employee id',null = True)
    dateofjoining = models.DateTimeField(verbose_name='Date Of Joining',auto_now_add=True, blank=True)
   # department = models.ForeignKey(Department,on_delete=models.CASCADE,verbose_name= 'department',null= True)
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
    is_active = models.BooleanField(default=True)
    role =     models.ForeignKey(Role,null= True,on_delete= models.CASCADE)
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






class ComponentTypeGlobal(models.TextChoices):
    EARNING = "earning", "Earning"
    DEDUCTION = "deduction", "Deduction"
    COMPANY_CONTRIB = "company_contribution", "Company Contribution"





class CalcMethod(models.TextChoices):
    FLAT = "flat", "Flat Amount"
    PERCENT = "percent", "Percent of Basis"
    SLAB = "slab", "Slab (banded)"
    FORMULA = "formula", "Formula (DSL)"


class RoundingRule(models.TextChoices):
    NONE = "none", "None"
    NEAREST = "nearest", "Nearest"
    UP = "up", "Ceil"
    DOWN = "down", "Floor"
    BANKERS = "bankers", "Bankers"


class Frequency(models.TextChoices):
    MONTHLY = "monthly", "Monthly"
    QUARTERLY = "quarterly", "Quarterly"
    YEARLY = "yearly", "Yearly"
    ONCE = "once", "One-time"


class Taxability(models.TextChoices):
    TAXABLE = "taxable", "Taxable"
    EXEMPT = "exempt", "Exempt"
    PARTIAL = "partial", "Partially Exempt"


class PayslipGroup(models.TextChoices):
    EARNINGS = "earnings", "Earnings"
    DEDUCTIONS = "deductions", "Deductions"
    EMPLOYER = "employer_contrib", "Employer Contributions"


class CapType(models.TextChoices):
    AMOUNT_MAX = "amount_max", "Amount Max"
    PERCENT_MAX = "percent_max", "% of Basis Max"
    AMOUNT_MIN = "amount_min", "Amount Min"          # NEW
    PERCENT_MIN = "percent_min", "% of Basis Min"    # NEW


class Periodicity(models.TextChoices):
    MONTHLY = "monthly", "Monthly"
    QUARTERLY = "quarterly", "Quarterly"
    YEARLY = "yearly", "Yearly"


class ConditionOp(models.TextChoices):
    EQ = "=", "="
    NE = "!=", "!="
    GT = ">", ">"
    GTE = ">=", ">="
    LT = "<", "<"
    LTE = "<=", "<="
    IN = "in", "in"
    NOT_IN = "not_in", "not_in"


class SlabGroupType(models.TextChoices):
    PT = "PT", "Professional Tax"
    LWF = "LWF", "Labour Welfare Fund"
    BONUS = "BONUS", "Bonus"
    CUSTOM = "CUSTOM", "Custom"


class RateType(models.TextChoices):
    AMOUNT = "amount", "Amount"
    PERCENT = "percent", "Percent"


class SlabCycle(models.TextChoices):
    MONTHLY = "monthly", "Monthly"
    HALF_YEARLY = "half-yearly", "Half-yearly"
    YEARLY = "yearly", "Yearly"


class CityCategoryChoice(models.TextChoices):
    METRO = "metro", "Metro"
    NON_METRO = "non_metro", "Non-metro"


# ---------- Global Masters ----------

class SlabGroup(TimeStampedModel, EffectiveDatedModel):
    group_key = models.CharField(max_length=64)
    name = models.CharField(max_length=128)
    type = models.CharField(max_length=12, choices=SlabGroupType.choices)
    notes = models.CharField(max_length=255, blank=True, default="")
    history = HistoricalRecords()

    class Meta:
        indexes = [models.Index(fields=["group_key", "effective_from"])]
        constraints = [
            # optional: ensure group_key is case-insensitive unique within time, enforced via clean()
        ]
        ordering = ["group_key", "effective_from"]

    def __str__(self):
        return f"{self.group_key} [{self.effective_from} → {self.effective_to or '—'}]"

    def clean(self):
        super().clean()
        # No overlapping effective windows for same group_key
        qs = SlabGroup.objects.exclude(pk=self.pk).filter(group_key__iexact=self.group_key)
        if overlaps := qs.filter(
            Q(effective_to__isnull=True, effective_from__lte=self.effective_to or self.effective_from)
            | Q(effective_to__isnull=False, effective_to__gte=self.effective_from)
        ).exists():
            raise ValidationError("Overlapping effective dates for the same SlabGroup.group_key.")

ALLOW_SPECIFIC_VS_ALL = True  # allow overlap between a specific scope and a catch-all ({})
MONTH_NAMES = {"Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"}


class Slab(TimeStampedModel, EffectiveDatedModel):  # ← restore these bases
    group = models.ForeignKey("payroll.SlabGroup", related_name="slabs", on_delete=models.CASCADE)

    # optional convenience; blank = ALL
    state_scope = models.CharField(max_length=16, blank=True, default="")

    from_amount = models.DecimalField(max_digits=12, decimal_places=2)
    to_amount   = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    rate_type = models.CharField(max_length=8, choices=RateType.choices)
    value     = models.DecimalField(max_digits=10, decimal_places=4)

    cycle  = models.CharField(max_length=12, choices=SlabCycle.choices, default=SlabCycle.MONTHLY)
    months = models.CharField(max_length=64, blank=True, default="")  # e.g., "Jun, Dec"

    percent_of = models.CharField(max_length=64, blank=True, default="")
    scope_json = models.JSONField(blank=True, default=dict)

    history = HistoricalRecords()

    class Meta:
        indexes = [
            models.Index(fields=["group", "effective_from"]),              # uses EffectiveDatedModel
            models.Index(fields=["group", "from_amount", "to_amount"]),
            models.Index(fields=["group", "state_scope", "effective_from"]),
        ]
        ordering = ["group", "from_amount", "effective_from", "id"]

    def __str__(self):
        state = self.state_scope or "ALL"
        to = self.to_amount if self.to_amount is not None else "∞"
        return f"{self.group.group_key}:{state} {self.from_amount}–{to} {self.rate_type}={self.value}"

    # ---------- helpers (same as last message) ----------
    @staticmethod
    def _to_dec(x):
        if x is None:
            return None
        try:
            return Decimal(str(x))
        except (InvalidOperation, TypeError):
            return None

    @staticmethod
    def _date_overlap(a1, a2, b1, b2):
        a2 = a2 if a2 is not None else a1
        b2 = b2 if b2 is not None else b1
        return (a1 <= b2) and (b1 <= a2)

    @staticmethod
    def _amount_overlap(a1, a2, b1, b2):
        a2 = a2 if a2 is not None else a1
        b2 = b2 if b2 is not None else b1
        return not (a2 < b1 or b2 < a1)

    @staticmethod
    def _is_all(scope: dict | None) -> bool:
        return not bool(scope or {})

    @staticmethod
    def _as_set(v):
        if v is None:
            return None
        if isinstance(v, (list, tuple, set)):
            return set(map(str, v))
        return {str(v)}

    @classmethod
    def _collect_range(cls, scope, base):
        if not scope:
            return (None, None)
        mn = mx = None
        nested = scope.get(base)
        if isinstance(nested, dict):
            mn = cls._to_dec(nested.get("min"))
            mx = cls._to_dec(nested.get("max"))
        if mn is None:
            mn = cls._to_dec(scope.get(f"{base}_min"))
        if mx is None:
            mx = cls._to_dec(scope.get(f"{base}_max"))
        return (mn, mx)

    @staticmethod
    def _intervals_disjoint(a_min, a_max, b_min, b_max):
        lo1 = a_min if a_min is not None else Decimal("-Infinity")
        hi1 = a_max if a_max is not None else Decimal("Infinity")
        lo2 = b_min if b_min is not None else Decimal("-Infinity")
        hi2 = b_max if b_max is not None else Decimal("Infinity")
        return hi1 < lo2 or hi2 < lo1

    @staticmethod
    def _bases_with_ranges(scope: dict):
        bases = set()
        for k, v in (scope or {}).items():
            if k.endswith("_min") or k.endswith("_max"):
                bases.add(k.rsplit("_", 1)[0])
            elif isinstance(v, dict) and ({"min", "max"} & set(v.keys())):
                bases.add(k)
        return bases

    @classmethod
    def _scopes_definitely_disjoint(cls, s1: dict | None, s2: dict | None) -> bool:
        s1 = s1 or {}
        s2 = s2 or {}
        if cls._is_all(s1) or cls._is_all(s2):
            return False

        eq_keys = {
            k for k in (s1.keys() & s2.keys())
            if not k.endswith("_in") and not k.endswith("_not_in")
            and not k.endswith("_min") and not k.endswith("_max")
            and not isinstance(s1.get(k), dict) and not isinstance(s2.get(k), dict)
        }
        for k in eq_keys:
            if str(s1[k]) != str(s2[k]):
                return True

        for base in set(s1.keys()) | set(s2.keys()):
            if base.endswith(("_in", "_not_in")):
                base = base.rsplit("_", 1)[0]
            s1_in  = cls._as_set(s1.get(f"{base}_in"))
            s2_in  = cls._as_set(s2.get(f"{base}_in"))
            s1_not = cls._as_set(s1.get(f"{base}_not_in"))
            s2_not = cls._as_set(s2.get(f"{base}_not_in"))
            if s1_in is not None and s2_in is not None and s1_in.isdisjoint(s2_in):
                return True
            if s1_in is not None and s2_not is not None and s1_in.issubset(s2_not):
                return True
            if s2_in is not None and s1_not is not None and s2_in.issubset(s1_not):
                return True
            v1 = s1.get(base, None)
            v2 = s2.get(base, None)
            if v1 is not None and s2_not is not None and str(v1) in s2_not:
                return True
            if v2 is not None and s1_not is not None and str(v2) in s1_not:
                return True

        range_bases = cls._bases_with_ranges(s1) | cls._bases_with_ranges(s2)
        for base in range_bases:
            a_min, a_max = cls._collect_range(s1, base)
            b_min, b_max = cls._collect_range(s2, base)
            if (a_min, a_max) == (None, None) or (b_min, b_max) == (None, None):
                continue
            if cls._intervals_disjoint(a_min, a_max, b_min, b_max):
                return True
        return False

    def clean(self):
        super().clean()

        # normalize and mirror state into scope_json
        self.state_scope = (self.state_scope or "").upper()
        s = dict(self.scope_json or {})
        if self.state_scope and not s.get("state_in"):
            s["state_in"] = [self.state_scope]
            self.scope_json = s

        if self.to_amount is not None and self.from_amount > self.to_amount:
            raise ValidationError("Slab.from_amount must be <= Slab.to_amount.")

        if self.rate_type == RateType.PERCENT:
            if not (Decimal("0") <= self.value <= Decimal("100")):
                raise ValidationError("Percent slabs must have value between 0 and 100.")
            if not self.percent_of:
                raise ValidationError("percent_of is required when rate_type = PERCENT.")
        else:
            if self.percent_of:
                self.percent_of = ""

        if self.cycle != SlabCycle.MONTHLY and self.months:
            bad = [m.strip() for m in self.months.split(",") if m.strip() not in MONTH_NAMES]
            if bad:
                raise ValidationError(f"Invalid month name(s): {', '.join(bad)}")

        # overlap guard (same group, effective window, numeric band, scope not provably disjoint)
        qs = (Slab.objects
              .exclude(pk=self.pk)
              .filter(group=self.group)
              .filter(
                  Q(effective_to__isnull=True, effective_from__lte=self.effective_to or self.effective_from)
                  | Q(effective_to__isnull=False, effective_to__gte=self.effective_from)
              ))

        for other in qs:
            if not self._date_overlap(self.effective_from, self.effective_to,
                                      other.effective_from, other.effective_to):
                continue
            if not self._amount_overlap(self.from_amount, self.to_amount,
                                        other.from_amount, other.to_amount):
                continue

            s_self  = dict(self.scope_json or {})
            s_other = dict(other.scope_json or {})

            if ALLOW_SPECIFIC_VS_ALL and (self._is_all(s_self) ^ self._is_all(s_other)):
                continue
            if self._scopes_definitely_disjoint(s_self, s_other):
                continue

            raise ValidationError("Overlapping slab ranges for same group and effective period.")



class CityCategory(TimeStampedModel, EffectiveDatedModel):
    city_code = models.CharField(max_length=32)   # e.g., "DELHI"
    city_name = models.CharField(max_length=64)
    category = models.CharField(max_length=16, choices=CityCategoryChoice.choices)
    notes = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        indexes = [models.Index(fields=["city_code", "effective_from"])]
        ordering = ["city_code", "effective_from"]

    def __str__(self):
        return f"{self.city_code} → {self.category}"

    def clean(self):
        super().clean()
        # No overlapping windows for same city_code
        qs = CityCategory.objects.exclude(pk=self.pk).filter(city_code__iexact=self.city_code)
        if qs.filter(
            Q(effective_to__isnull=True, effective_from__lte=self.effective_to or self.effective_from)
            | Q(effective_to__isnull=False, effective_to__gte=self.effective_from)
        ).exists():
            raise ValidationError("Overlapping effective dates for the same city_code.")


# ---------- Global Payroll Component & Caps ----------


class ComponentFamily(TimeStampedModel):
    """
    One row per global 'code' family, e.g. BASIC, HRA, PF_EMP.
    All versioned PayrollComponent rows attach here.
    """
    code = models.CharField(max_length=64, unique=True)     # UPPERCASE code
    display_name = models.CharField(max_length=128, blank=True, default="")

    class Meta:
        ordering = ["code"]

    def __str__(self):
        # Prefer display_name if provided, otherwise fallback to code
        return f"{self.display_name or self.code} ({self.code})"


class PayrollComponentGlobal(TimeStampedModel, EffectiveDatedModel):
    family = models.ForeignKey("ComponentFamily", related_name="versions",
                               on_delete=models.PROTECT,null = True,blank = True)  
    
    entity = models.ForeignKey(
        Entity, null=True, blank=True, on_delete=models.PROTECT,
        related_name="payroll_component_versions"
    )
    code = models.CharField(max_length=64)   # API-stable; keep uppercase in save()
    name = models.CharField(max_length=128)
    type = models.CharField(max_length=24, choices=ComponentTypeGlobal.choices)
    calc_method = models.CharField(max_length=12, choices=CalcMethod.choices)

    # Behavior
    frequency = models.CharField(max_length=12, choices=Frequency.choices, default=Frequency.MONTHLY)
    rounding = models.CharField(max_length=12, choices=RoundingRule.choices, default=RoundingRule.NEAREST)
    priority = models.PositiveIntegerField(default=0)
    is_proratable = models.BooleanField(default=True)

    # Flags (inclusion & tax)
    taxability = models.CharField(max_length=12, choices=Taxability.choices, default=Taxability.TAXABLE)
    pf_include = models.BooleanField(default=False)
    esi_include = models.BooleanField(default=False)
    pt_include = models.BooleanField(default=False)
    lwf_include = models.BooleanField(default=False)

    # Method-specific fields (kept on the model for simplicity)
    # percent
    percent_basis = models.CharField(max_length=64, blank=True, default="")  # e.g., CTC_MONTHLY, BASIC, GROSS
    basis_cap_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    basis_cap_periodicity = models.CharField(max_length=12, choices=Periodicity.choices, null=True, blank=True)

    # slab
    slab_group = models.ForeignKey(SlabGroup, null=True, blank=True, on_delete=models.PROTECT, related_name="components")
    slab_base = models.CharField(max_length=64, blank=True, default="")           # value used to select band
    slab_percent_basis = models.CharField(max_length=64, blank=True, default="")  # if percent rows, % of what? (default = slab_base)
    slab_scope_field = models.CharField(max_length=64, blank=True, default="entity.state_code")

    # formula
    formula_text = models.TextField(blank=True, default="")
    default_params = models.JSONField(blank=True, default=dict)  # {param: number}

    # governance (bands)
    policy_band_min_percent = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True,
                                                  validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))])
    policy_band_max_percent = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True,
                                                  validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))])

    # eligibility rules (optional)
    eligibility = models.JSONField(blank=True, default=list)  # [{field, op, value}, ...]

    # payslip metadata (presentation)
    payslip_group = models.CharField(max_length=20, choices=PayslipGroup.choices, default=PayslipGroup.EARNINGS)
    display_order = models.PositiveIntegerField(default=10)
    show_on_payslip = models.BooleanField(default=True)
     # NEW: proration method (affects partial months)
    PRORATION_CHOICES = (
        ("calendar_days", "Calendar Days"),
        ("working_days", "Working Days"),
        ("hours", "Hours"),
    )
    proration_method = models.CharField(max_length=16, choices=PRORATION_CHOICES,
                                        default="calendar_days")  # NEW

    # NEW: payout timing for non-monthly items (bonus/LWF)
    PAYOUT_POLICY_CHOICES = (
        ("book_in_months", "Book Only In Listed Months"),
        ("accrue_and_pay_on_months", "Accrue Monthly, Pay On Listed Months"),
    )
    payout_policy = models.CharField(max_length=32, choices=PAYOUT_POLICY_CHOICES,
                                     null=True, blank=True)       # NEW
    payout_months = models.CharField(max_length=64, blank=True, default="")  # e.g., "Jun, Dec"  # NEW

    # NEW: allow negative outcomes (for recoveries/adjustments)
    allow_negative = models.BooleanField(default=False)            # NEW

    # NEW: declare external vars formulas need (engine will validate presence)
    required_vars = models.JSONField(blank=True, default=list)     # ["RENT","SALES"]  # NEW
    history = HistoricalRecords()

    class Meta:
        indexes = [
            models.Index(fields=["code","entity", "effective_from"]),
            models.Index(fields=["calc_method", "priority"]),
        ]
        ordering = ["code", "entity", "effective_from", "priority"]

    def __str__(self):
        return f"{self.code} ({self.calc_method}) [{self.effective_from} → {self.effective_to or '—'}]"

    def save(self, *args, **kwargs):
        if self.code:
            self.code = self.code.upper()
        if self.family and self.family.code.upper() != self.code:
            self.code = self.family.code.upper()
        super().save(*args, **kwargs)

    # -------- Validation --------
    def clean(self):
        super().clean()
        # keep code == family.code if family present
        if self.family and self.code.upper() != self.family.code.upper():
            raise ValidationError("PayrollComponent.code must match family.code.")

        # overlap check (same code)
        overlap_qs = (PayrollComponentGlobal.objects
                      .exclude(pk=self.pk)
                      .filter(code__iexact=self.code, entity=self.entity))
        a1 = self.effective_from
        a2 = self.effective_to or self.effective_from
        if overlap_qs.filter(
            Q(effective_to__isnull=True, effective_from__lte=a2) |
            Q(effective_to__isnull=False, effective_to__gte=self.effective_from)
        ).exists():
            raise ValidationError("Overlapping effective dates for same code & entity scope.")

        # method-specific requireds...
        if self.calc_method == CalcMethod.PERCENT:
            if not self.percent_basis:
                raise ValidationError("percent_basis is required when calc_method = 'percent'.")
            if (self.basis_cap_amount is not None) ^ bool(self.basis_cap_periodicity):
                raise ValidationError("basis_cap_amount and basis_cap_periodicity must be set together.")
        elif self.calc_method == CalcMethod.SLAB:
            if not self.slab_group_id:
                raise ValidationError("slab_group is required when calc_method = 'slab'.")
            if not self.slab_base:
                raise ValidationError("slab_base is required when calc_method = 'slab'.")
        elif self.calc_method == CalcMethod.FORMULA:
            if not self.formula_text.strip():
                raise ValidationError("formula_text is required when calc_method = 'formula'.")

        if (self.policy_band_min_percent is not None) and (self.policy_band_max_percent is not None):
            if self.policy_band_min_percent > self.policy_band_max_percent:
                raise ValidationError("policy_band_min_percent cannot be greater than policy_band_max_percent.")

        if self.code in {"PF_EMP", "PF_EMPR"} and self.pf_include:
            raise ValidationError("PF components should not include themselves in PF base (pf_include must be False).")
        
    @classmethod
    def resolve_for(cls, family, as_of, entity=None):
        base = (cls.objects
                  .filter(family=family, effective_from__lte=as_of)
                  .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=as_of)))
        if entity:
            scoped = base.filter(entity=entity).order_by("-effective_from", "-priority").first()
            if scoped:
                return scoped
        return base.filter(entity__isnull=True).order_by("-effective_from", "-priority").first()

class PayrollComponentCap(TimeStampedModel):
    component = models.ForeignKey(PayrollComponentGlobal, related_name="caps", on_delete=models.CASCADE)
    cap_type = models.CharField(max_length=16, choices=CapType.choices)
    cap_basis = models.CharField(max_length=64, blank=True, default="")  # <-- change: blank OK
    cap_value = models.DecimalField(max_digits=12, decimal_places=4, validators=[MinValueValidator(Decimal("0"))])
    periodicity = models.CharField(max_length=12, choices=Periodicity.choices, default=Periodicity.MONTHLY)
    conditions = models.JSONField(blank=True, default=list)
    notes = models.CharField(max_length=255, blank=True, default="")
    sort_order = models.PositiveIntegerField(default=0)
    history = HistoricalRecords()

    class Meta:
        ordering = ["component", "sort_order", "id"]
        indexes  = [models.Index(fields=["component", "cap_type"])]

    def clean(self):
        super().clean()
        percent_types = {CapType.PERCENT_MAX, CapType.PERCENT_MIN}
        if self.cap_type in percent_types:
            if not self.cap_basis:
                raise ValidationError("cap_basis is required for percent caps.")
            # 0..100 for percent caps
            if not (Decimal("0") <= self.cap_value <= Decimal("100")):
                raise ValidationError("Percent cap_value must be between 0 and 100.")
        else:
            # amount caps: normalize basis to empty
            if self.cap_basis:
                self.cap_basis = ""

        # optional: validate condition ops if you have an enum
        for c in self.conditions or []:
            op = c.get("op")
            if op not in dict(ConditionOp.choices):
                raise ValidationError(f"Invalid condition op: {op}.")

            

class EntityPayrollComponent(TimeStampedModel, EffectiveDatedModel):
    # Required: every row belongs to an Entity
    entity = models.ForeignKey(Entity, on_delete=models.CASCADE, verbose_name="entity",null = True)

    # Optional: pin to a specific global version (usually leave NULL and let family resolve by date)
    component = models.ForeignKey(
        PayrollComponentGlobal, related_name="payroll_configs", on_delete=models.PROTECT,
        null=True, blank=True
    )

    # Always link to the family (code group)
    family = models.ForeignKey(ComponentFamily, related_name="entity_configs", on_delete=models.PROTECT)

    enabled = models.BooleanField(default=True)

    # Method-aware defaults
    default_percent = models.DecimalField(
        max_digits=6, decimal_places=3, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))]
    )
    default_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0"))]
    )
    param_overrides = models.JSONField(blank=True, default=dict)
    slab_scope_value = models.CharField(max_length=32, blank=True, default="")

    # Employee override policy
    allow_emp_override = models.BooleanField(default=False)
    emp_min_percent = models.DecimalField(
        max_digits=6, decimal_places=3, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))]
    )
    emp_max_percent = models.DecimalField(
        max_digits=6, decimal_places=3, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))]
    )

    notes = models.CharField(max_length=255, blank=True, default="")
    history = HistoricalRecords()

    class Meta:
        indexes = [
            models.Index(fields=["entity", "family", "effective_from"]),
        ]
        ordering = ["entity", "family", "effective_from"]

    def __str__(self):
        return f"{self.entity} · {self.family.code} [{self.effective_from} → {self.effective_to or '—'}]"

    # Resolve the active Global version for a date (or pin to `component` if provided)
    def resolve_global_version(self, as_of_date=None):
        d = as_of_date or self.effective_from
        if self.component_id:
            return self.component
        PCG = apps.get_model(self._meta.app_label, "PayrollComponentGlobal")
        return PCG.resolve_for(self.family, as_of=d, entity=self.entity)

    def clean(self):
        super().clean()

        if self.slab_scope_value:
            self.slab_scope_value = self.slab_scope_value.upper()

        # --- overlap: per (entity, family) only ---
        overlap_qs = (EntityPayrollComponent.objects
                      .exclude(pk=self.pk)
                      .filter(entity=self.entity, family=self.family))

        # two windows [a1, a2], [b1, b2] overlap if:
        # (a2 is null or b1 <= a2) and (b2 is null or a1 <= b2)
        a1, a2 = self.effective_from, self.effective_to
        if overlap_qs.filter(
            Q(effective_to__isnull=True, effective_from__lte=a2 or a1) |
            Q(effective_to__isnull=False, effective_from__lte=a2 or a1, effective_to__gte=a1)
        ).exists():
            raise ValidationError("Overlapping effective dates for the same Entity + Component family.")

        # --- resolve a global version to validate against ---
        g = self.resolve_global_version(self.effective_from)
        if not g:
            raise ValidationError(f"No Global component version for '{self.family.code}' on {self.effective_from}.")

        # If pinned to a specific component, ensure it belongs to this family and covers the date
        if self.component_id:
            if self.component.family_id != self.family_id:
                raise ValidationError("Pinned component does not belong to the selected family.")
            if not self.component.effective_from <= self.effective_from <= (self.component.effective_to or self.effective_from):
                raise ValidationError("Pinned component version is not active on the entity's effective_from date.")

        if not self.enabled:
            return

        method = g.calc_method

        # --- Percent ---
        if method == CalcMethod.PERCENT:
            if self.default_percent is None:
                raise ValidationError("default_percent is required for percent method.")
            if self.default_amount is not None:
                raise ValidationError("default_amount must be empty for percent method.")
            if self.param_overrides:
                raise ValidationError("param_overrides must be empty for percent method.")
            if g.policy_band_min_percent is not None and self.default_percent < g.policy_band_min_percent:
                raise ValidationError(f"default_percent {self.default_percent}% is below Global min {g.policy_band_min_percent}%.")
            if g.policy_band_max_percent is not None and self.default_percent > g.policy_band_max_percent:
                raise ValidationError(f"default_percent {self.default_percent}% exceeds Global max {g.policy_band_max_percent}%.")

        # --- Flat ---
        elif method == CalcMethod.FLAT:
            if self.default_amount is None:
                raise ValidationError("default_amount is required for flat method.")
            if self.default_percent is not None:
                raise ValidationError("default_percent must be empty for flat method.")
            if self.param_overrides:
                raise ValidationError("param_overrides must be empty for flat method.")

        # --- Formula ---
        elif method == CalcMethod.FORMULA:
            if not isinstance(self.param_overrides, dict):
                raise ValidationError("param_overrides must be a JSON object.")
            global_keys = set((g.default_params or {}).keys())
            bad = [k for k in self.param_overrides.keys() if k not in global_keys]
            if bad:
                allowed = ", ".join(sorted(global_keys)) or "(none)"
                raise ValidationError(f"Unknown formula param(s): {', '.join(bad)}. Allowed: {allowed}")
            for k, v in (self.param_overrides or {}).items():
                try:
                    Decimal(str(v))
                except Exception:
                    raise ValidationError(f"Formula param '{k}' must be numeric.")
            # Apply global band to percent-like params (heuristic: *_PCT as fraction)
            if g.policy_band_min_percent is not None or g.policy_band_max_percent is not None:
                for k, v in (self.param_overrides or {}).items():
                    if "PCT" in k.upper():
                        frac = Decimal(str(v))
                        if g.policy_band_min_percent is not None and frac < Decimal(g.policy_band_min_percent) / 100:
                            raise ValidationError(f"{k}={v} below global min {g.policy_band_min_percent}% (use 0.xx).")
                        if g.policy_band_max_percent is not None and frac > Decimal(g.policy_band_max_percent) / 100:
                            raise ValidationError(f"{k}={v} exceeds global max {g.policy_band_max_percent}% (use 0.xx).")
            if self.default_percent is not None or self.default_amount is not None:
                raise ValidationError("default_percent/default_amount must be empty for formula method.")

        # --- Slab ---
        elif method == CalcMethod.SLAB:
            if self.default_percent is not None or self.default_amount is not None:
                raise ValidationError("default_percent/default_amount must be empty for slab method.")
            if self.param_overrides:
                raise ValidationError("param_overrides must be empty for slab method.")
            if self.slab_scope_value:
                group = g.slab_group
                if not group:
                    raise ValidationError("Global slab group missing; cannot validate slab_scope_value.")
                scope = self.slab_scope_value
                if scope != "ALL" and not Slab.objects.filter(group=group, state_scope__iexact=scope).exists():
                    raise ValidationError(f"Scope '{scope}' not found in slabs for group '{group.group_key}'.")
        else:
            raise ValidationError(f"Unsupported global calc method: {method}")

        # --- Employee override tightening ---
        if self.allow_emp_override or self.emp_min_percent is not None or self.emp_max_percent is not None:
            if (self.emp_min_percent is not None and self.emp_max_percent is not None
                    and self.emp_min_percent > self.emp_max_percent):
                raise ValidationError("emp_min_percent cannot be greater than emp_max_percent.")
            if g.policy_band_min_percent is not None and self.emp_min_percent is not None:
                if self.emp_min_percent < g.policy_band_min_percent:
                    raise ValidationError(f"emp_min_percent {self.emp_min_percent}% is below Global min {g.policy_band_min_percent}%.")
            if g.policy_band_max_percent is not None and self.emp_max_percent is not None:
                if self.emp_max_percent > g.policy_band_max_percent:
                    raise ValidationError(f"emp_max_percent {self.emp_max_percent}% exceeds Global max {g.policy_band_max_percent}%.")
                

class PayStructure(TimeStampedModel, EffectiveDatedModel):
    """
    Template header. Null entity = Global template.
    Versioning via EffectiveDatedModel (effective_from / effective_to).
    """
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        RETIRED = "retired", "Retired"

    class RoundingRule(models.TextChoices):
        NONE = "none", "No Rounding"
        NEAREST = "nearest", "Nearest"
        UP = "up", "Ceil"
        DOWN = "down", "Floor"
        BANKERS = "bankers", "Banker’s"

    class ProrationMethod(models.TextChoices):
        CALENDAR_DAYS = "calendar_days", "Calendar Days"
        WORKING_DAYS = "working_days", "Working Days"
        HOURS = "hours", "Hours"

    code = models.CharField(max_length=64)
    name = models.CharField(max_length=128)

    # Null = global template
    entity = models.ForeignKey(
        Entity, on_delete=models.PROTECT, null=True, blank=True,
        related_name="pay_structures"
    )

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    rounding = models.CharField(max_length=12, choices=RoundingRule.choices, default=RoundingRule.NEAREST)
    proration_method = models.CharField(max_length=16, choices=ProrationMethod.choices, default=ProrationMethod.CALENDAR_DAYS)

    notes = models.CharField(max_length=255, blank=True, default="")
    history = HistoricalRecords()

    class Meta:
        indexes = [
            models.Index(fields=["code", "entity", "effective_from"]),
            models.Index(fields=["status"]),
        ]
        ordering = ["code", "entity", "effective_from"]

    def save(self, *args, **kwargs):
        if self.code:
            self.code = self.code.upper()
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        # Overlap guard for same (code, entity)
        overlap_qs = (PayStructure.objects
                      .exclude(pk=self.pk)
                      .filter(code__iexact=self.code, entity=self.entity))
        a1, a2 = self.effective_from, self.effective_to
        if overlap_qs.filter(
            Q(effective_to__isnull=True, effective_from__lte=a2 or a1) |
            Q(effective_to__isnull=False, effective_from__lte=a2 or a1, effective_to__gte=a1)
        ).exists():
            raise ValidationError("Overlapping effective dates for the same PayStructure code & entity.")

        # Only one ACTIVE window may overlap at a time (same code+entity)
        if self.status == PayStructure.Status.ACTIVE:
            active_overlap = overlap_qs.filter(status=PayStructure.Status.ACTIVE).filter(
                Q(effective_to__isnull=True, effective_from__lte=a2 or a1) |
                Q(effective_to__isnull=False, effective_from__lte=a2 or a1, effective_to__gte=a1)
            )
            if active_overlap.exists():
                raise ValidationError("Another ACTIVE PayStructure overlaps this window.")

    def __str__(self):
        scope = self.entity_id or "GLOBAL"
        to = self.effective_to.isoformat() if self.effective_to else "—"
        return f"{self.code} [{scope}] {self.effective_from} → {to}"


class PayStructureComponent(TimeStampedModel):
    """
    A single line item inside a PayStructure. Points to a ComponentFamily (e.g., BASIC/HRA/PF_EMP).
    You can optionally pin a specific PayrollComponentGlobal version; otherwise the active version
    for (family, template.effective_from) will be used at runtime / materialization.

    Template-level defaults/overrides here must match the method of the resolved global component:
    - FLAT:     default_amount required; percent/params empty
    - PERCENT:  default_percent required; amount/params empty
    - SLAB:     no amount/percent/params; optional slab_scope_value
    - FORMULA:  param_overrides (subset & numeric) required; amount/percent empty
    """
    template = models.ForeignKey(PayStructure, on_delete=models.CASCADE, related_name="items")
    family = models.ForeignKey("ComponentFamily", on_delete=models.PROTECT, related_name="structure_items")

    # Optional: pin a particular global version
    pinned_global_component = models.ForeignKey(
        "PayrollComponentGlobal", on_delete=models.PROTECT,
        null=True, blank=True, related_name="pinned_in_structures"
    )

    enabled = models.BooleanField(default=True)
    required = models.BooleanField(default=False)
    priority = models.PositiveIntegerField(default=100)

    # Method-aware defaults/overrides
    default_percent = models.DecimalField(
        max_digits=6, decimal_places=3, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))]
    )
    default_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0"))]
    )
    param_overrides = models.JSONField(blank=True, default=dict)  # for FORMULA only
    slab_scope_value = models.CharField(max_length=32, blank=True, default="")  # e.g., "ALL", "KA", "MH"

    # Employee self-service bounds (for PERCENT or formula params mapped to percent)
    allow_emp_override = models.BooleanField(default=False)
    emp_min_percent = models.DecimalField(
        max_digits=6, decimal_places=3, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))]
    )
    emp_max_percent = models.DecimalField(
        max_digits=6, decimal_places=3, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))]
    )

    # Payslip presentation overrides (optional; None = inherit global)
    show_on_payslip = models.BooleanField(null=True, blank=True)
    display_order = models.PositiveIntegerField(null=True, blank=True)

    notes = models.CharField(max_length=255, blank=True, default="")
    history = HistoricalRecords()

    class Meta:
        unique_together = [("template", "family")]
        ordering = ["template", "priority", "id"]
        indexes = [
            models.Index(fields=["template", "priority"]),
            models.Index(fields=["family"]),
        ]

    def __str__(self):
        return f"{self.template.code} · {self.family.code}"

    # -------- Helpers --------
    def _global_qs(self):
        """Base queryset to resolve the active global component definition by date."""
        return apps.get_model(self._meta.app_label, "PayrollComponentGlobal").objects

    def resolve_global(self, target_entity=None):
        if self.pinned_global_component_id:
            return self.pinned_global_component
        PCG = apps.get_model(self._meta.app_label, "PayrollComponentGlobal")
        return PCG.resolve_for(self.family, as_of=self.template.effective_from, entity=target_entity or self.template.entity)

    # -------- Validation --------
    def clean(self):
        super().clean()

        if self.slab_scope_value:
            self.slab_scope_value = self.slab_scope_value.upper()

        # Pin must match family and be active on template.effective_from
        if self.pinned_global_component_id:
            g = self.pinned_global_component
            if g.family_id != self.family_id:
                raise ValidationError("Pinned global component does not belong to the selected family.")
            d = self.template.effective_from
            if not (g.effective_from <= d <= (g.effective_to or d)):
                raise ValidationError("Pinned global component is not active on the template's effective_from.")

        # Resolve the applicable global definition
        g = self.resolve_global()
        if not g:
            raise ValidationError(
                f"No Global component version for '{self.family.code}' on {self.template.effective_from}."
            )

        if not self.enabled:
            return  # disabled rows can be loosely specified

        method = (g.calc_method or "").lower()

        # ---- Method-specific rules ----
        if method == "percent":
            if self.default_percent is None:
                raise ValidationError({"default_percent": "Required for percent method."})
            if self.default_amount is not None:
                raise ValidationError({"default_amount": "Must be empty for percent method."})
            if self.param_overrides:
                raise ValidationError({"param_overrides": "Must be empty for percent method."})
            # Apply global bands if present
            if g.policy_band_min_percent is not None and self.default_percent < g.policy_band_min_percent:
                raise ValidationError({"default_percent": f"Below Global min {g.policy_band_min_percent}%."})
            if g.policy_band_max_percent is not None and self.default_percent > g.policy_band_max_percent:
                raise ValidationError({"default_percent": f"Exceeds Global max {g.policy_band_max_percent}%."})

        elif method == "flat":
            if self.default_amount is None:
                raise ValidationError({"default_amount": "Required for flat method."})
            if self.default_percent is not None:
                raise ValidationError({"default_percent": "Must be empty for flat method."})
            if self.param_overrides:
                raise ValidationError({"param_overrides": "Must be empty for flat method."})

        elif method == "formula":
            if not isinstance(self.param_overrides, dict):
                raise ValidationError({"param_overrides": "Must be a JSON object for formula method."})
            global_keys = set((g.default_params or {}).keys())
            bad = [k for k in self.param_overrides.keys() if k not in global_keys]
            if bad:
                allowed = ", ".join(sorted(global_keys)) or "(none)"
                raise ValidationError({"param_overrides": f"Unknown param(s): {', '.join(bad)}. Allowed: {allowed}"})
            # numeric check
            for k, v in (self.param_overrides or {}).items():
                try:
                    Decimal(str(v))
                except Exception:
                    raise ValidationError({f"param_overrides.{k}": "Must be numeric."})
            if self.default_percent is not None or self.default_amount is not None:
                raise ValidationError("default_percent/default_amount must be empty for formula method.")

        elif method == "slab":
            if self.default_percent is not None or self.default_amount is not None:
                raise ValidationError("default_percent/default_amount must be empty for slab method.")
            if self.param_overrides:
                raise ValidationError("param_overrides must be empty for slab method.")
            # (Optional) Validate slab_scope_value exists in slabs for the group's state scope.
            # You can do this here if you expose Slab/SlabGroup via apps.get_model.

        else:
            raise ValidationError(f"Unsupported global calc method: {g.calc_method}")

        # ---- Employee override bounds (if enabled) ----
        if self.allow_emp_override or self.emp_min_percent is not None or self.emp_max_percent is not None:
            if (self.emp_min_percent is not None and self.emp_max_percent is not None
                    and self.emp_min_percent > self.emp_max_percent):
                raise ValidationError("emp_min_percent cannot be greater than emp_max_percent.")
            if g.policy_band_min_percent is not None and self.emp_min_percent is not None:
                if self.emp_min_percent < g.policy_band_min_percent:
                    raise ValidationError(
                        f"emp_min_percent {self.emp_min_percent}% is below Global min {g.policy_band_min_percent}%."
                    )
            if g.policy_band_max_percent is not None and self.emp_max_percent is not None:
                if self.emp_max_percent > g.policy_band_max_percent:
                    raise ValidationError(
                        f"emp_max_percent {self.emp_max_percent}% exceeds Global max {g.policy_band_max_percent}%."
                    )
                

# Very-stable global choices can stay as TextChoices
class EmployeeStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"

class PayCycle(models.TextChoices):
    MONTHLY = "monthly", "Monthly"
    WEEKLY = "weekly", "Weekly"

MOBILE_RE = RegexValidator(r"^\d{10}$", "Enter a 10-digit mobile number")
IFSC_RE = RegexValidator(r"^[A-Z]{4}0[A-Z0-9]{6}$", "Enter a valid IFSC")

def limit_to(set_key):
    """Use in ForeignKey(limit_choices_to=...) to scope Option FKs by set key."""
    return {"set__key": set_key}

# -------------------------
# Basics
# -------------------------
class Employee(TimeStampedModel):
    entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="employees")
    code = models.CharField(max_length=32, db_index=True)
    full_name = models.CharField(max_length=200)
    display_name = models.CharField(max_length=200, blank=True, default="")
    status = models.CharField(max_length=16, choices=EmployeeStatus.choices, default=EmployeeStatus.ACTIVE)

    work_email = models.EmailField(blank=True, default="", db_index=True)
    personal_email = models.EmailField(blank=True, default="")
    mobile = models.CharField(max_length=10, validators=[MOBILE_RE], blank=True, default="")

    # Option-driven dropdowns for flexibility (gender/marital_status can be per-entity & localized)
    gender = models.ForeignKey(
        Option, on_delete=models.PROTECT, null=True, blank=True,
        related_name="gender_employees", limit_choices_to=limit_to("gender")
    )
    marital_status = models.ForeignKey(
        Option, on_delete=models.PROTECT, null=True, blank=True,
        related_name="marital_status_employees", limit_choices_to=limit_to("marital_status")
    )

    dob = models.DateField(null=True, blank=True)
    blood_group = models.CharField(max_length=8, blank=True, default="")
    addr_current = models.TextField(blank=True, default="")
    addr_permanent = models.TextField(blank=True, default="")
    emergency_contact = models.CharField(max_length=200, blank=True, default="")  # "Name - Phone"

    photo = models.ImageField(upload_to="employee_photos/", null=True, blank=True)
    notes = models.TextField(blank=True, default="")

    class Meta:
        unique_together = [("entity", "code")]
        indexes = [models.Index(fields=["entity", "status"])]

    def __str__(self): return f"{self.entity.entityname}:{self.code} — {self.display_name or self.full_name}"

# -------------------------
# Employment (effective-dated)
# -------------------------
class EmploymentAssignment(TimeStampedModel, EffectiveDatedModel):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="assignments")
    business_unit = models.ForeignKey(BusinessUnit, on_delete=models.PROTECT, null=True, blank=True)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, null=True, blank=True)
    location = models.ForeignKey(Location, on_delete=models.PROTECT, null=True, blank=True)
    cost_center = models.ForeignKey(CostCenter, on_delete=models.PROTECT, null=True, blank=True)

   # grade_band = models.CharField(max_length=64, blank=True, default="")
   # designation = models.CharField(max_length=128, blank=True, default="")

    # Reporting (kept on the dated slice to preserve history)
    manager_employee = models.ForeignKey(
        Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name="direct_reports"
    )
    hrbp = models.CharField(max_length=128, blank=True, default="")

    # Option-driven types (tenant-extensible)
    employment_type = models.ForeignKey(
        Option, on_delete=models.PROTECT, null=True, blank=True,
        related_name="employment_type_assignments", limit_choices_to=limit_to("employment_type")
    )
    work_type = models.ForeignKey(
        Option, on_delete=models.PROTECT, null=True, blank=True,
        related_name="work_type_assignments", limit_choices_to=limit_to("work_type")
    )

    date_of_joining = models.DateField(null=True, blank=True)
    probation_end = models.DateField(null=True, blank=True)
    confirmation_date = models.DateField(null=True, blank=True)

    # Separation captured on the slice it applies to
    last_working_day = models.DateField(null=True, blank=True)
    separation_reason = models.CharField(max_length=200, blank=True, default="")
    exit_status = models.ForeignKey(
        Option, on_delete=models.PROTECT, null=True, blank=True,
        related_name="exit_status_assignments", limit_choices_to=limit_to("exit_status")
    )

    class Meta:
        indexes = [
            models.Index(fields=["employee", "effective_from"]),
            models.Index(fields=["department", "effective_from"]),
        ]
        ordering = ["employee", "-effective_from"]

    def __str__(self):
        scope = self.department or self.business_unit or self.location or "—"
        return f"{self.employee} @ {scope} ({self.effective_from}→{self.effective_to or '∞'})"

# -------------------------
# Compensation (effective-dated envelope)
# -------------------------
class EmployeeCompensation(TimeStampedModel, EffectiveDatedModel):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="compensations")
    ctc_annual = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    pay_structure_code = models.CharField(max_length=64, blank=True, default="")
    pay_cycle = models.CharField(max_length=16, choices=PayCycle.choices, default=PayCycle.MONTHLY)
    pay_group = models.CharField(max_length=64, blank=True, default="")
    work_calendar = models.CharField(max_length=64, blank=True, default="")
    weekly_off_pattern = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        indexes = [models.Index(fields=["employee", "effective_from"])]
        ordering = ["employee", "-effective_from"]

    def __str__(self): return f"{self.employee} — CTC ₹{self.ctc_annual} ({self.effective_from}→{self.effective_to or '∞'})"

# -------------------------
# Statutory (India)
# -------------------------
class EmployeeStatutoryIN(TimeStampedModel):
    employee = models.OneToOneField(Employee, on_delete=models.CASCADE, related_name="statutory_in")
    pan = models.CharField(max_length=16, blank=True, default="")
    aadhaar_masked = models.CharField(max_length=20, blank=True, default="")  # store masked/hashed, not raw
    uan = models.CharField(max_length=20, blank=True, default="")
    pf_number = models.CharField(max_length=32, blank=True, default="")
    esic_number = models.CharField(max_length=32, blank=True, default="")
    pt_state = models.CharField(max_length=64, blank=True, default="")
    lwf_state = models.CharField(max_length=64, blank=True, default="")
    tax_regime = models.ForeignKey(
        Option, on_delete=models.PROTECT, null=True, blank=True,
        related_name="tax_regime_employees", limit_choices_to=limit_to("tax_regime")
    )
    regime_effective = models.DateField(null=True, blank=True)
    def __str__(self): return f"StatutoryIN<{self.employee}>"

# -------------------------
# Bank / Payments
# -------------------------
class EmployeeBankAccount(TimeStampedModel):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="bank_accounts")
    bank_name = models.CharField(max_length=128)
    ifsc = models.CharField(max_length=11, validators=[IFSC_RE])
    account_masked = models.CharField(max_length=34, help_text="Store masked only (e.g., XXXXXX1234)")
    account_type = models.ForeignKey(
        Option, on_delete=models.PROTECT, null=True, blank=True,
        related_name="account_type_employees", limit_choices_to=limit_to("account_type")
    )
    upi_id = models.CharField(max_length=80, blank=True, default="")
    is_primary = models.BooleanField(default=True)
    payment_preference = models.ForeignKey(
        Option, on_delete=models.PROTECT, null=True, blank=True,
        related_name="payment_pref_employees", limit_choices_to=limit_to("payment_preference")
    )

    class Meta:
        indexes = [models.Index(fields=["employee", "is_primary"])]
        constraints = [
            models.UniqueConstraint(
                fields=["employee"], condition=models.Q(is_primary=True),
                name="uniq_primary_bank_per_employee"
            )
        ]

    def __str__(self): return f"{self.employee} — {self.bank_name} ({'primary' if self.is_primary else 'alt'})"

# -------------------------
# Documents
# -------------------------
def employee_doc_path(instance, filename):
    return f"employee_docs/{instance.employee.entity.entityname}/{instance.employee.code}/{filename}"

class EmployeeDocument(TimeStampedModel):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="documents")
    title = models.CharField(max_length=128)
    file = models.FileField(upload_to=employee_doc_path)
    category = models.ForeignKey(
        Option, on_delete=models.PROTECT, null=True, blank=True,
        related_name="document_category_employees", limit_choices_to=limit_to("document_category")
    )
    note = models.CharField(max_length=200, blank=True, default="")
    def __str__(self): return f"{self.employee} — {self.title}"

    



    



