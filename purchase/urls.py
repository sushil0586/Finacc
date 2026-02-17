from django.urls import path

from purchase.views.purchase_invoice import (
    PurchaseInvoiceListCreateAPIView,
    PurchaseInvoiceRetrieveUpdateDestroyAPIView,
    PurchaseInvoiceSearchAPIView,
)

from purchase.views.purchase_choices import PurchaseCompiledChoicesAPIView

from purchase.views.purchase_settings import PurchaseSettingsAPIView

from purchase.views.purchase_invoice_actions import (
    PurchaseInvoiceConfirmAPIView,
    PurchaseInvoicePostAPIView,
    PurchaseInvoiceCancelAPIView,
    PurchaseInvoiceRebuildTaxSummaryAPIView,
    PurchaseInvoiceCreateCreditNoteAPIView,
    PurchaseInvoiceCreateDebitNoteAPIView,
    PurchaseInvoiceITCBlockAPIView,
    PurchaseInvoiceITCPendingAPIView,
    PurchaseInvoiceITCClaimAPIView,
    PurchaseInvoiceITCReverseAPIView,
    PurchaseInvoice2BMatchStatusAPIView,
)
from purchase.views.purchase_readonly import (
    PurchaseInvoiceLinesListAPIView,
    PurchaseTaxSummaryListAPIView,
)

urlpatterns = [
    # CRUD
    path("purchase-invoices/", PurchaseInvoiceListCreateAPIView.as_view(), name="purchase-invoice-list-create"),
    path("purchase-invoices/<int:pk>/", PurchaseInvoiceRetrieveUpdateDestroyAPIView.as_view(), name="purchase-invoice-rud"),

    # Actions
    path("purchase-invoices/<int:pk>/confirm/", PurchaseInvoiceConfirmAPIView.as_view(), name="purchase-invoice-confirm"),
    path("purchase-invoices/<int:pk>/post/", PurchaseInvoicePostAPIView.as_view(), name="purchase-invoice-post"),
    path("purchase-invoices/<int:pk>/cancel/", PurchaseInvoiceCancelAPIView.as_view(), name="purchase-invoice-cancel"),
    path("purchase-invoices/<int:pk>/rebuild-tax-summary/", PurchaseInvoiceRebuildTaxSummaryAPIView.as_view(), name="purchase-invoice-rebuild-tax-summary"),

    # CN/DN from Invoice
    path("purchase-invoices/<int:pk>/create-credit-note/", PurchaseInvoiceCreateCreditNoteAPIView.as_view(), name="purchase-invoice-create-credit-note"),
    path("purchase-invoices/<int:pk>/create-debit-note/", PurchaseInvoiceCreateDebitNoteAPIView.as_view(), name="purchase-invoice-create-debit-note"),

    # ITC actions
    path("purchase-invoices/<int:pk>/itc/block/", PurchaseInvoiceITCBlockAPIView.as_view(), name="purchase-invoice-itc-block"),
    path("purchase-invoices/<int:pk>/itc/pending/", PurchaseInvoiceITCPendingAPIView.as_view(), name="purchase-invoice-itc-pending"),
    path("purchase-invoices/<int:pk>/itc/claim/", PurchaseInvoiceITCClaimAPIView.as_view(), name="purchase-invoice-itc-claim"),
    path("purchase-invoices/<int:pk>/itc/reverse/", PurchaseInvoiceITCReverseAPIView.as_view(), name="purchase-invoice-itc-reverse"),

    # GSTR-2B
    path("purchase-invoices/<int:pk>/gstr2b/status/", PurchaseInvoice2BMatchStatusAPIView.as_view(), name="purchase-invoice-2b-status"),
     
    # Read-only lists
    path("purchase-lines/", PurchaseInvoiceLinesListAPIView.as_view(), name="purchase-lines-list"),
    path("purchase-tax-summaries/", PurchaseTaxSummaryListAPIView.as_view(), name="purchase-tax-summaries-list"),
    path("settings/", PurchaseSettingsAPIView.as_view(), name="purchase-settings"),
    path("choices/", PurchaseCompiledChoicesAPIView.as_view(), name="purchase-compiled-choices"),
     path("purchase-invoices/search/", PurchaseInvoiceSearchAPIView.as_view(), name="purchase-invoice-search"),

]
