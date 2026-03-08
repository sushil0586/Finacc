from django.urls import path

from receipts.views import (
    ReceiptVoucherListCreateAPIView,
    ReceiptVoucherRetrieveUpdateDestroyAPIView,
    ReceiptVoucherConfirmAPIView,
    ReceiptVoucherPostAPIView,
    ReceiptVoucherApprovalAPIView,
    ReceiptVoucherCancelAPIView,
    ReceiptVoucherSettlementSummaryAPIView,
    ReceiptVoucherUnpostAPIView,
    ReceiptSettingsAPIView,
    ReceiptCompiledChoicesAPIView,
    ReceiptCustomerAdvanceBalanceListAPIView,
    ReceiptCustomerBillOpenItemListAPIView,
    ReceiptModeListAPIView,
    ReceiptVoucherPDFAPIView,
)


urlpatterns = [
    path("receipt-vouchers/", ReceiptVoucherListCreateAPIView.as_view(), name="receipt-voucher-list-create"),
    path("receipt-vouchers/<int:pk>/", ReceiptVoucherRetrieveUpdateDestroyAPIView.as_view(), name="receipt-voucher-rud"),
    path("receipt-vouchers/<int:pk>/confirm/", ReceiptVoucherConfirmAPIView.as_view(), name="receipt-voucher-confirm"),
    path("receipt-vouchers/<int:pk>/post/", ReceiptVoucherPostAPIView.as_view(), name="receipt-voucher-post"),
    path("receipt-vouchers/<int:pk>/approval/", ReceiptVoucherApprovalAPIView.as_view(), name="receipt-voucher-approval"),
    path("receipt-vouchers/<int:pk>/unpost/", ReceiptVoucherUnpostAPIView.as_view(), name="receipt-voucher-unpost"),
    path("receipt-vouchers/<int:pk>/cancel/", ReceiptVoucherCancelAPIView.as_view(), name="receipt-voucher-cancel"),
    path("receipt-vouchers/<int:pk>/settlement-summary/", ReceiptVoucherSettlementSummaryAPIView.as_view(), name="receipt-voucher-settlement-summary"),
    path("receipt-vouchers/<int:pk>/pdf/", ReceiptVoucherPDFAPIView.as_view(), name="receipt-voucher-pdf"),
    path("open-items/", ReceiptCustomerBillOpenItemListAPIView.as_view(), name="receipt-open-items-list"),
    path("open-advances/", ReceiptCustomerAdvanceBalanceListAPIView.as_view(), name="receipt-open-advances-list"),
    path("receipt-modes/", ReceiptModeListAPIView.as_view(), name="receipt-mode-list"),
    path("settings/", ReceiptSettingsAPIView.as_view(), name="receipt-settings"),
    path("choices/", ReceiptCompiledChoicesAPIView.as_view(), name="receipt-choices"),
]
