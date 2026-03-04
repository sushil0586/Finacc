from django.urls import path

from payments.views import (
    PaymentVoucherListCreateAPIView,
    PaymentVoucherRetrieveUpdateDestroyAPIView,
    PaymentVoucherConfirmAPIView,
    PaymentVoucherPostAPIView,
    PaymentVoucherCancelAPIView,
    PaymentSettingsAPIView,
    PaymentCompiledChoicesAPIView,
    PaymentVendorBillOpenItemListAPIView,
)


urlpatterns = [
    path("payment-vouchers/", PaymentVoucherListCreateAPIView.as_view(), name="payment-voucher-list-create"),
    path("payment-vouchers/<int:pk>/", PaymentVoucherRetrieveUpdateDestroyAPIView.as_view(), name="payment-voucher-rud"),
    path("payment-vouchers/<int:pk>/confirm/", PaymentVoucherConfirmAPIView.as_view(), name="payment-voucher-confirm"),
    path("payment-vouchers/<int:pk>/post/", PaymentVoucherPostAPIView.as_view(), name="payment-voucher-post"),
    path("payment-vouchers/<int:pk>/cancel/", PaymentVoucherCancelAPIView.as_view(), name="payment-voucher-cancel"),
    path("open-items/", PaymentVendorBillOpenItemListAPIView.as_view(), name="payment-open-items-list"),
    path("settings/", PaymentSettingsAPIView.as_view(), name="payment-settings"),
    path("choices/", PaymentCompiledChoicesAPIView.as_view(), name="payment-choices"),
]
