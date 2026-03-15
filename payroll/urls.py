from django.urls import path

from payroll.views import (
    PayrollRunApproveAPIView,
    PayrollRunCalculateAPIView,
    PayrollRunListCreateAPIView,
    PayrollRunPayslipAPIView,
    PayrollRunPaymentHandoffAPIView,
    PayrollRunPaymentReconcileAPIView,
    PayrollRunPostAPIView,
    PayrollRunReverseAPIView,
    PayrollRunRetrieveAPIView,
    PayrollRunSubmitAPIView,
    PayrollRunSummaryAPIView,
)

app_name = "payroll"

urlpatterns = [
    path("runs/", PayrollRunListCreateAPIView.as_view(), name="payroll-run-list-create"),
    path("runs/<int:pk>/", PayrollRunRetrieveAPIView.as_view(), name="payroll-run-detail"),
    path("runs/<int:pk>/calculate/", PayrollRunCalculateAPIView.as_view(), name="payroll-run-calculate"),
    path("runs/<int:pk>/submit/", PayrollRunSubmitAPIView.as_view(), name="payroll-run-submit"),
    path("runs/<int:pk>/approve/", PayrollRunApproveAPIView.as_view(), name="payroll-run-approve"),
    path("runs/<int:pk>/post/", PayrollRunPostAPIView.as_view(), name="payroll-run-post"),
    path("runs/<int:pk>/reverse/", PayrollRunReverseAPIView.as_view(), name="payroll-run-reverse"),
    path("runs/<int:pk>/payment-handoff/", PayrollRunPaymentHandoffAPIView.as_view(), name="payroll-run-payment-handoff"),
    path("runs/<int:pk>/payment-reconcile/", PayrollRunPaymentReconcileAPIView.as_view(), name="payroll-run-payment-reconcile"),
    path("runs/<int:pk>/summary/", PayrollRunSummaryAPIView.as_view(), name="payroll-run-summary"),
    path(
        "runs/<int:pk>/payslips/<int:employee_run_id>/",
        PayrollRunPayslipAPIView.as_view(),
        name="payroll-run-payslip",
    ),
]
