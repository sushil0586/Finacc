from django.urls import path

from payments.views import (
    PaymentVoucherListCreateAPIView,
    PaymentVoucherRetrieveUpdateDestroyAPIView,
    PaymentVoucherConfirmAPIView,
    PaymentVoucherPostAPIView,
    PaymentVoucherApprovalAPIView,
    PaymentVoucherCancelAPIView,
    PaymentVoucherSettlementSummaryAPIView,
    PaymentVoucherUnpostAPIView,
    PaymentSettingsAPIView,
    PaymentCompiledChoicesAPIView,
    PaymentVendorAdvanceBalanceListAPIView,
    PaymentVendorBillOpenItemListAPIView,
    PaymentModeListAPIView,
    PaymentVoucherPDFAPIView,
)


urlpatterns = [
    path("payment-vouchers/", PaymentVoucherListCreateAPIView.as_view(), name="payment-voucher-list-create"),
    path("payment-vouchers/<int:pk>/", PaymentVoucherRetrieveUpdateDestroyAPIView.as_view(), name="payment-voucher-rud"),
    path("payment-vouchers/<int:pk>/confirm/", PaymentVoucherConfirmAPIView.as_view(), name="payment-voucher-confirm"),
    path("payment-vouchers/<int:pk>/post/", PaymentVoucherPostAPIView.as_view(), name="payment-voucher-post"),
    path("payment-vouchers/<int:pk>/approval/", PaymentVoucherApprovalAPIView.as_view(), name="payment-voucher-approval"),
    path("payment-vouchers/<int:pk>/unpost/", PaymentVoucherUnpostAPIView.as_view(), name="payment-voucher-unpost"),
    path("payment-vouchers/<int:pk>/cancel/", PaymentVoucherCancelAPIView.as_view(), name="payment-voucher-cancel"),
    path("payment-vouchers/<int:pk>/settlement-summary/", PaymentVoucherSettlementSummaryAPIView.as_view(), name="payment-voucher-settlement-summary"),
    path("payment-vouchers/<int:pk>/pdf/", PaymentVoucherPDFAPIView.as_view(), name="payment-voucher-pdf"),
    path("open-items/", PaymentVendorBillOpenItemListAPIView.as_view(), name="payment-open-items-list"),
    path("open-advances/", PaymentVendorAdvanceBalanceListAPIView.as_view(), name="payment-open-advances-list"),
    path("payment-modes/", PaymentModeListAPIView.as_view(), name="payment-mode-list"),
    path("settings/", PaymentSettingsAPIView.as_view(), name="payment-settings"),
    path("choices/", PaymentCompiledChoicesAPIView.as_view(), name="payment-choices"),
]
