from django.urls import path
from payroll import views


app_name = 'payroll'


urlpatterns  = [

    path('salarycomponent',views.salarycomponentApiView.as_view(),name = 'salarycomponent'),
    path('salarycomponent/<int:id>',views.salarycomponentupdatedelApiView.as_view(),name = 'salarycomponent'),
    # path('employee',views.employeeApiView.as_view(),name = 'salarycomponent'),
    # path('employee/<int:employee>',views.employeeupdatedelview.as_view(),name = 'salarycomponent'),
    path('employeesalary',views.employeesalaryApiView.as_view(),name = 'salarycomponent'),
    path('designation',views.designationApiView.as_view(),name = 'salarycomponent'),
    path('department',views.departmentApiView.as_view(),name = 'salarycomponent'),
    path('getsalarystructure',views.getsalarystructure.as_view(),name = 'salarycomponent'),
    path('employee/<int:id>/', views.EmployeePayrollAPIView.as_view(), name='employee-detail'),
    path('employee/', views.EmployeePayrollAPIView.as_view(), name='employee-create'),
    path('employees/entity/<int:entity_id>/', views.EmployeesByEntityAPIView.as_view(), name='employees-by-entity'),
    path('calculate-salary/', views.CalculateSalaryComponentsView.as_view(), name='calculate-salary-components'),
    path('payroll-components/<int:entity_id>/', views.ActivePayrollComponentsByEntity.as_view(), name='active-payroll-components'),

    

    
]