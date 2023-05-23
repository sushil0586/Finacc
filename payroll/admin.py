from django.contrib import admin

from payroll.models import salarycomponent,employeesalary,employee,department,designation


# Register your models here.

admin.site.register(salarycomponent)
admin.site.register(employee)
admin.site.register(employeesalary)
admin.site.register(department)
admin.site.register(designation)

