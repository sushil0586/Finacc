from django.urls import path
from payroll import views

from .views import (
    OptionSetListCreateAPIView, OptionListCreateAPIView,
    BusinessUnitListCreateAPIView, DepartmentListCreateAPIView,
    LocationListCreateAPIView, CostCenterListCreateAPIView,
    EmployeeListCreateAPIView, EmployeeDetailAPIView,
    GradeBandListCreateAPIView, GradeBandRetrieveUpdateDestroyAPIView,
    DesignationListCreateAPIView, DesignationRetrieveUpdateDestroyAPIView,ManagersListView,EmployeeSummaryView,
    CompensationPreviewAPIView,
    CompensationOverrideAPIView,
    CompensationRecalculateAPIView,
    CompensationApplyAPIView,
    PayStructureDropdownAPIView,
    PayStructureListAPIView,
    PayStructureMetaAPIView,
)


app_name = 'payroll'


urlpatterns  = [

    path('salarycomponent',views.salarycomponentApiView.as_view(),name = 'salarycomponent'),
    path('salarycomponent/<int:id>',views.salarycomponentupdatedelApiView.as_view(),name = 'salarycomponent'),
    # path('employee',views.employeeApiView.as_view(),name = 'salarycomponent'),
    # path('employee/<int:employee>',views.employeeupdatedelview.as_view(),name = 'salarycomponent'),
    path('employeesalary',views.employeesalaryApiView.as_view(),name = 'salarycomponent'),
    path('getsalarystructure',views.getsalarystructure.as_view(),name = 'salarycomponent'),
    path('employee/<int:id>/', views.EmployeePayrollAPIView.as_view(), name='employee-detail'),
    path('employee/', views.EmployeePayrollAPIView.as_view(), name='employee-create'),
    path('employees/entity/<int:entity_id>/', views.EmployeesByEntityAPIView.as_view(), name='employees-by-entity'),
    path('calculate-salary/', views.CalculatePayrollFromCTCAPIView.as_view(), name='calculate-salary-components'),
    path('payroll-components/<int:entity_id>/', views.ActivePayrollComponentsByEntity.as_view(), name='active-payroll-components'),
    path('calculation-types/', views.CalculationTypeListAPIView.as_view(), name='calculation-type-list'),
    path('bonus-frequencies/', views.BonusFrequencyListAPIView.as_view(), name='bonus-frequency-list'),
    path('calculation-values/', views.CalculationValueListAPIView.as_view(), name='calculation-value-list'),
    path('component-types/', views.ComponentTypeListAPIView.as_view(), name='component-type-list'),
    path('payroll-component/', views.PayrollComponentAPIView.as_view()),  # For POST
    path('payroll-component/<int:pk>/', views.PayrollComponentAPIView.as_view()),  # For PUT
    path('payroll-component/entity/<int:entity_id>/', views.PayrollComponentByEntityAPIView.as_view()), # GET by entity
    path('payroll-component/detail/<int:pk>/', views.PayrollComponentDetailAPIView.as_view()), # GET by component id
    path('payroll-component/delete/<int:id>', views.PayrollComponentDeleteAPIView.as_view(), name='payroll-component-delete'),
    path("entity-components/", views.EntityPayrollComponentListCreateView.as_view(), name="entity-component-list"),
    path("entity-components/<int:pk>/", views.EntityPayrollComponentDetailView.as_view(), name="entity-component-detail"),
    path("pay-structures/", views.PayStructureListCreateView.as_view(), name="paystructure-list-create"),
    path("pay-structures/nested-create/", views.PayStructureNestedCreateView.as_view(), name="paystructure-nested-create"),
    path("pay-structures/<int:pk>/", views.PayStructureDetailView.as_view(), name="paystructure-detail"),

    # Items
    path("pay-structure-items/", views.PayStructureComponentListCreateView.as_view(), name="paystructureitem-list-create"),
    path("pay-structure-items/<int:pk>/", views.PayStructureComponentDetailView.as_view(), name="paystructureitem-detail"),

    # Resolve preview (read-only) & Apply (Option A)
    path("pay-structures/resolve/", views.PayStructureResolveView.as_view(), name="paystructure-resolve"),
    path("pay-structures/<int:pk>/apply/", views.ApplyStructureToEntityView.as_view(), name="paystructure-apply"),
    path("option-sets/", OptionSetListCreateAPIView.as_view(), name="optionset-list-create"),
    path("options/", OptionListCreateAPIView.as_view(), name="option-list-create"),

    # entity-scoped lists
    path("business-units/", BusinessUnitListCreateAPIView.as_view(), name="businessunit-list-create"),
    path("departments/", DepartmentListCreateAPIView.as_view(), name="department-list-create"),
    path("locations/", LocationListCreateAPIView.as_view(), name="location-list-create"),
    path("cost-centers/", CostCenterListCreateAPIView.as_view(), name="costcenter-list-create"),
    path("employees/", EmployeeListCreateAPIView.as_view(), name="employee-list-create"),
    path("employees/<int:pk>/", EmployeeDetailAPIView.as_view(), name="employee-detail"),
    path("grade-bands/",     GradeBandListCreateAPIView.as_view(), name="gradeband-list-create"),
    path("grade-bands/<int:pk>/", GradeBandRetrieveUpdateDestroyAPIView.as_view(), name="gradeband-detail"),
    path("designations/",    DesignationListCreateAPIView.as_view(), name="designation-list-create"),
    path("designations/<int:pk>/", DesignationRetrieveUpdateDestroyAPIView.as_view(), name="designation-detail"),
    path("managers/", ManagersListView.as_view(), name="managers-list"),
    path("employees/summary", EmployeeSummaryView.as_view(), name="employee-summary"),
    path("comp/preview/", CompensationPreviewAPIView.as_view(), name="payroll-comp-preview"),
    path("comp/<int:pk>/override/", CompensationOverrideAPIView.as_view(), name="payroll-comp-override"),
    path("comp/<int:pk>/recalculate/", CompensationRecalculateAPIView.as_view(), name="payroll-comp-recalculate"),
    path("comp/<int:pk>/apply/", CompensationApplyAPIView.as_view(), name="payroll-comp-apply"),
    path("paystructures/dropdown", PayStructureDropdownAPIView.as_view(), name="paystructure-dropdown"),
    path("paystructures",           PayStructureListAPIView.as_view(),     name="paystructure-list"),
    path("paystructures/meta",     PayStructureMetaAPIView.as_view(),     name="paystructure-meta"),
]