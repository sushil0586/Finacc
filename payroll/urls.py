from django.urls import path
from payroll import views


app_name = 'payroll'


urlpatterns  = [

    path('salarycomponent',views.salarycomponentApiView.as_view(),name = 'salarycomponent'),
    path('employee',views.employeeApiView.as_view(),name = 'salarycomponent'),
    path('employee/<int:employee>',views.employeeupdatedelview.as_view(),name = 'salarycomponent'),
    path('employeesalary',views.employeesalaryApiView.as_view(),name = 'salarycomponent'),

    
]