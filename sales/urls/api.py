from django.urls import path

from sales.views.sales_invoice_views import (
    SalesInvoiceListCreateAPIView,
    SalesInvoiceRetrieveUpdateAPIView,
    SalesInvoiceConfirmAPIView,
    SalesInvoicePostAPIView,
    SalesInvoiceCancelAPIView,
)
from sales.views.sales_choices_views import SalesChoicesAPIView
from sales.views.sales_settings_views import SalesSettingsAPIView

urlpatterns = [
    path("invoices/", SalesInvoiceListCreateAPIView.as_view(), name="sales-invoice-list-create"),
    path("invoices/<int:pk>/", SalesInvoiceRetrieveUpdateAPIView.as_view(), name="sales-invoice-detail"),

    path("invoices/<int:pk>/confirm/", SalesInvoiceConfirmAPIView.as_view(), name="sales-invoice-confirm"),
    path("invoices/<int:pk>/post/", SalesInvoicePostAPIView.as_view(), name="sales-invoice-post"),
    path("invoices/<int:pk>/cancel/", SalesInvoiceCancelAPIView.as_view(), name="sales-invoice-cancel"),

    path("choices/", SalesChoicesAPIView.as_view(), name="sales-choices"),
    path("settings/", SalesSettingsAPIView.as_view(), name="sales-settings"),
]
