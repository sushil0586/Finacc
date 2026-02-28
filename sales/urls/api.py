from django.urls import path
from sales.views.eway_views import SalesInvoiceEWayPrefillAPIView, SalesInvoiceGenerateEWayAPIView


from sales.views.sales_invoice_views import (
    SalesInvoiceListCreateAPIView,
    SalesInvoiceRetrieveUpdateAPIView,
    SalesInvoiceConfirmAPIView,
    SalesInvoicePostAPIView,
    SalesInvoiceCancelAPIView,
)

from sales.views.sales_invoice_compliance_api import (
    SalesInvoiceEnsureComplianceAPIView,
    SalesInvoiceGenerateIRNAPIView,
   # SalesInvoiceGenerateEWayAPIView,
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
    path("sales-invoices/<int:pk>/compliance/ensure/", SalesInvoiceEnsureComplianceAPIView.as_view()),
    path("sales-invoices/<int:pk>/compliance/generate-irn/", SalesInvoiceGenerateIRNAPIView.as_view()),
    path("sales-invoices/<int:id>/compliance/eway/prefill/", SalesInvoiceEWayPrefillAPIView.as_view()),
    path("sales-invoices/<int:id>/  ", SalesInvoiceGenerateEWayAPIView.as_view()),
]
