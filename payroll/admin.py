from django.contrib import admin

from payroll.models import salarycomponent,employeesalary,employee


# Register your models here.

admin.site.register(salarycomponent)
admin.site.register(employee)
admin.site.register(employeesalary)

