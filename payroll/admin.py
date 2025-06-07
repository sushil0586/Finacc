from django.contrib import admin
from .models import (
    department, designation, TaxRegime, InvestmentSection,
    CalculationType, BonusFrequency, CalculationValue, ComponentType,
    PayrollComponent, EntityPayrollComponentConfig, salarycomponent,
    employee, EmployeePayrollComponent, employeesalary,
    salarytrans, salarytransdetails, EmployeeInvestment,
    EmployeeInvestmentSummary, EmployeeLoan
)

admin.site.register(department)
admin.site.register(designation)
admin.site.register(TaxRegime)
admin.site.register(InvestmentSection)
admin.site.register(CalculationType)
admin.site.register(BonusFrequency)
admin.site.register(CalculationValue)
admin.site.register(ComponentType)
admin.site.register(PayrollComponent)
admin.site.register(EntityPayrollComponentConfig)
admin.site.register(salarycomponent)
admin.site.register(employee)
admin.site.register(EmployeePayrollComponent)
admin.site.register(employeesalary)
admin.site.register(salarytrans)
admin.site.register(salarytransdetails)
admin.site.register(EmployeeInvestment)
admin.site.register(EmployeeInvestmentSummary)
admin.site.register(EmployeeLoan)
