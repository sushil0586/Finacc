from django.urls import path

from vouchers.views import (
    VoucherListCreateAPIView,
    VoucherRetrieveUpdateDestroyAPIView,
    VoucherConfirmAPIView,
    VoucherPostAPIView,
    VoucherApprovalAPIView,
    VoucherCancelAPIView,
    VoucherUnpostAPIView,
    VoucherSummaryAPIView,
    VoucherSettingsAPIView,
    VoucherCompiledChoicesAPIView,
    VoucherPDFAPIView,
    VoucherFormMetaAPIView,
    VoucherDetailFormMetaAPIView,
    VoucherSearchMetaAPIView,
    VoucherSettingsMetaAPIView,
)

urlpatterns = [
    path("meta/voucher-form/", VoucherFormMetaAPIView.as_view(), name="voucher-form-meta"),
    path("meta/voucher-detail-form/", VoucherDetailFormMetaAPIView.as_view(), name="voucher-detail-form-meta"),
    path("meta/voucher-search/", VoucherSearchMetaAPIView.as_view(), name="voucher-search-meta"),
    path("meta/settings/", VoucherSettingsMetaAPIView.as_view(), name="voucher-settings-meta"),
    path("vouchers/", VoucherListCreateAPIView.as_view(), name="voucher-list-create"),
    path("vouchers/<int:pk>/", VoucherRetrieveUpdateDestroyAPIView.as_view(), name="voucher-rud"),
    path("vouchers/<int:pk>/confirm/", VoucherConfirmAPIView.as_view(), name="voucher-confirm"),
    path("vouchers/<int:pk>/post/", VoucherPostAPIView.as_view(), name="voucher-post"),
    path("vouchers/<int:pk>/approval/", VoucherApprovalAPIView.as_view(), name="voucher-approval"),
    path("vouchers/<int:pk>/unpost/", VoucherUnpostAPIView.as_view(), name="voucher-unpost"),
    path("vouchers/<int:pk>/cancel/", VoucherCancelAPIView.as_view(), name="voucher-cancel"),
    path("vouchers/<int:pk>/summary/", VoucherSummaryAPIView.as_view(), name="voucher-summary"),
    path("vouchers/<int:pk>/pdf/", VoucherPDFAPIView.as_view(), name="voucher-pdf"),
    path("settings/", VoucherSettingsAPIView.as_view(), name="voucher-settings"),
    path("choices/", VoucherCompiledChoicesAPIView.as_view(), name="voucher-choices"),
]
