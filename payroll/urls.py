from django.urls import path
from payroll import views


app_name = 'payroll'


urlpatterns  = [

    path('salarycomponent',views.salarycomponentApiView.as_view(),name = 'salarycomponent'),
    path('salarycomponent/<int:id>',views.salarycomponentupdatedelApiView.as_view(),name = 'salarycomponent'),
    path('employee',views.employeeApiView.as_view(),name = 'salarycomponent'),
    path('employee/<int:employee>',views.employeeupdatedelview.as_view(),name = 'salarycomponent'),
    path('employeesalary',views.employeesalaryApiView.as_view(),name = 'salarycomponent'),
    path('designation',views.designationApiView.as_view(),name = 'salarycomponent'),
    path('department',views.departmentApiView.as_view(),name = 'salarycomponent'),
    path('employeelist',views.employeeListApiView.as_view(),name = 'salarycomponent'),
    path('employeelistfull/<int:employee>',views.employeeListfullApiView.as_view(),name = 'salarycomponent'),
    path('getsalarystructure',views.getsalarystructure.as_view(),name = 'salarycomponent'),


    

    
]