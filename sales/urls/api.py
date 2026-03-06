from django.urls import path
from sales.views.eway_views import (
    SalesInvoiceEWayPrefillAPIView,
    SalesInvoiceGenerateEWayAPIView,
    SalesInvoiceEWayB2CPrefillAPIView,
    SalesInvoiceEWayB2CGenerateAPIView,
    SalesInvoiceCancelEWayAPIView,
    SalesInvoiceEWayUpdateVehicleAPIView,
    SalesInvoiceEWayUpdateTransporterAPIView,
    SalesInvoiceEWayExtendValidityAPIView,
)


from sales.views.sales_invoice_views import (
    SalesInvoiceListCreateAPIView,
    SalesInvoiceRetrieveUpdateAPIView,
    SalesInvoiceConfirmAPIView,
    SalesInvoicePostAPIView,
    SalesInvoiceCancelAPIView,
    SalesInvoiceReverseAPIView,
    SalesInvoiceSettlementAPIView,
)

from sales.views.sales_invoice_compliance_api import (
    SalesInvoiceEnsureComplianceAPIView,
    SalesInvoiceGenerateIRNAPIView,
    SalesInvoiceCancelIRNAPIView,
    SalesInvoiceGetIRNDetailsAPIView,
    SalesInvoiceGetEWayByIRNAPIView,
   # SalesInvoiceGenerateEWayAPIView,
)
from sales.views.sales_choices_views import SalesChoicesAPIView
from sales.views.sales_settings_views import SalesSettingsAPIView
from sales.views.sales_charge_type_views import (
    SalesChargeTypeListCreateAPIView,
    SalesChargeTypeRetrieveUpdateAPIView,
)

urlpatterns = [
    path("invoices/", SalesInvoiceListCreateAPIView.as_view(), name="sales-invoice-list-create"),
    path("invoices/<int:pk>/", SalesInvoiceRetrieveUpdateAPIView.as_view(), name="sales-invoice-detail"),

    path("invoices/<int:pk>/confirm/", SalesInvoiceConfirmAPIView.as_view(), name="sales-invoice-confirm"),
    path("invoices/<int:pk>/post/", SalesInvoicePostAPIView.as_view(), name="sales-invoice-post"),
    path("invoices/<int:pk>/cancel/", SalesInvoiceCancelAPIView.as_view(), name="sales-invoice-cancel"),
    path("invoices/<int:pk>/reverse/", SalesInvoiceReverseAPIView.as_view(), name="sales-invoice-reverse"),
    path("invoices/<int:pk>/settlement/", SalesInvoiceSettlementAPIView.as_view(), name="sales-invoice-settlement"),

    path("choices/", SalesChoicesAPIView.as_view(), name="sales-choices"),
    path("settings/", SalesSettingsAPIView.as_view(), name="sales-settings"),
    path("charge-types/", SalesChargeTypeListCreateAPIView.as_view(), name="sales-charge-type-list"),
    path("charge-types/<int:pk>/", SalesChargeTypeRetrieveUpdateAPIView.as_view(), name="sales-charge-type-detail"),
    path("sales-invoices/<int:pk>/compliance/ensure/", SalesInvoiceEnsureComplianceAPIView.as_view()),
    path("sales-invoices/<int:pk>/compliance/generate-irn/", SalesInvoiceGenerateIRNAPIView.as_view()),
    path("sales-invoices/<int:pk>/compliance/cancel-irn/", SalesInvoiceCancelIRNAPIView.as_view()),
    path("sales-invoices/<int:pk>/compliance/get-irn-details/", SalesInvoiceGetIRNDetailsAPIView.as_view()),
    path("sales-invoices/<int:pk>/compliance/get-eway-by-irn/", SalesInvoiceGetEWayByIRNAPIView.as_view()),
    path("sales-invoices/<int:id>/compliance/eway/prefill/", SalesInvoiceEWayPrefillAPIView.as_view()),
    path("sales-invoices/<int:id>/compliance/generate-eway/", SalesInvoiceGenerateEWayAPIView.as_view()),
    path("sales-invoices/<int:id>/compliance/eway-b2c-prefill/", SalesInvoiceEWayB2CPrefillAPIView.as_view()),
    path("sales-invoices/<int:id>/compliance/generate-eway-b2c/", SalesInvoiceEWayB2CGenerateAPIView.as_view()),
    path("sales-invoices/<int:id>/compliance/cancel-eway/", SalesInvoiceCancelEWayAPIView.as_view()),
    path("sales-invoices/<int:id>/compliance/eway/update-vehicle/", SalesInvoiceEWayUpdateVehicleAPIView.as_view()),
    path("sales-invoices/<int:id>/compliance/eway/update-transporter/", SalesInvoiceEWayUpdateTransporterAPIView.as_view()),
    path("sales-invoices/<int:id>/compliance/eway/extend-validity/", SalesInvoiceEWayExtendValidityAPIView.as_view()),
]
