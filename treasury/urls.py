from django.urls import path

from .views import (
    TreasuryChequeBookListCreateAPIView,
    TreasuryChequeLeafListAPIView,
    TreasuryCashForecastAPIView,
    TreasuryCashMovementCancelAPIView,
    TreasuryCashMovementListCreateAPIView,
    TreasuryPaymentBatchApproveAPIView,
    TreasuryPaymentBatchCancelAPIView,
    TreasuryPaymentBatchExportAPIView,
    TreasuryPaymentBatchListCreateAPIView,
    TreasuryPaymentBatchMarkFailedAPIView,
    TreasuryPaymentBatchMarkPaidAPIView,
    TreasuryPaymentBatchRetrieveAPIView,
    TreasuryPaymentBatchValidateAPIView,
    TreasuryPaymentInstrumentActionAPIView,
    TreasuryPaymentInstrumentListAPIView,
    TreasuryVendorPayableCandidateListAPIView,
)

app_name = "treasury"

urlpatterns = [
    path("cash-forecast/", TreasuryCashForecastAPIView.as_view(), name="cash-forecast"),
    path("cheque-books/", TreasuryChequeBookListCreateAPIView.as_view(), name="cheque-book-list-create"),
    path("cheque-leaves/", TreasuryChequeLeafListAPIView.as_view(), name="cheque-leaf-list"),
    path("cash-movements/", TreasuryCashMovementListCreateAPIView.as_view(), name="cash-movement-list-create"),
    path("cash-movements/<uuid:pk>/cancel/", TreasuryCashMovementCancelAPIView.as_view(), name="cash-movement-cancel"),
    path("payment-instruments/", TreasuryPaymentInstrumentListAPIView.as_view(), name="payment-instrument-list"),
    path("payment-instruments/<uuid:pk>/<slug:action>/", TreasuryPaymentInstrumentActionAPIView.as_view(), name="payment-instrument-action"),
    path("payment-batches/", TreasuryPaymentBatchListCreateAPIView.as_view(), name="payment-batch-list-create"),
    path("payment-batches/vendor-payables/", TreasuryVendorPayableCandidateListAPIView.as_view(), name="payment-batch-vendor-payables"),
    path("payment-batches/<uuid:pk>/", TreasuryPaymentBatchRetrieveAPIView.as_view(), name="payment-batch-detail"),
    path("payment-batches/<uuid:pk>/validate/", TreasuryPaymentBatchValidateAPIView.as_view(), name="payment-batch-validate"),
    path("payment-batches/<uuid:pk>/approve/", TreasuryPaymentBatchApproveAPIView.as_view(), name="payment-batch-approve"),
    path("payment-batches/<uuid:pk>/export/", TreasuryPaymentBatchExportAPIView.as_view(), name="payment-batch-export"),
    path("payment-batches/<uuid:pk>/paid/", TreasuryPaymentBatchMarkPaidAPIView.as_view(), name="payment-batch-paid"),
    path("payment-batches/<uuid:pk>/failed/", TreasuryPaymentBatchMarkFailedAPIView.as_view(), name="payment-batch-failed"),
    path("payment-batches/<uuid:pk>/cancel/", TreasuryPaymentBatchCancelAPIView.as_view(), name="payment-batch-cancel"),
]
