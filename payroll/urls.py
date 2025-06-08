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
    path('calculation-types/', views.CalculationTypeListAPIView.as_view(), name='calculation-type-list'),
    path('bonus-frequencies/', views.BonusFrequencyListAPIView.as_view(), name='bonus-frequency-list'),
    path('calculation-values/', views.CalculationValueListAPIView.as_view(), name='calculation-value-list'),
    path('component-types/', views.ComponentTypeListAPIView.as_view(), name='component-type-list'),
    path('payroll-component/', views.PayrollComponentAPIView.as_view()),  # For POST
    path('payroll-component/<int:pk>/', views.PayrollComponentAPIView.as_view()),  # For PUT
    path('payroll-component/entity/<int:entity_id>/', views.PayrollComponentByEntityAPIView.as_view()), # GET by entity
    path('payroll-component/detail/<int:pk>/', views.PayrollComponentDetailAPIView.as_view()), # GET by component id
]