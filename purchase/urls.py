from django.urls import path

from purchase.views.purchase_invoice import (
    PurchaseInvoiceListCreateAPIView,
    PurchaseInvoiceRetrieveUpdateDestroyAPIView,
    PurchaseInvoiceSearchAPIView,
)

from purchase.views.purchase_charge_type import (
    PurchaseChargeTypeListCreateAPIView,
    PurchaseChargeTypeRetrieveUpdateAPIView,
)
from purchase.views.purchase_withholding import PurchaseTdsSectionListAPIView

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
from purchase.views.purchase_ap import (
    VendorBillOpenItemListAPIView,
    VendorSettlementListCreateAPIView,
    VendorSettlementPostAPIView,
    VendorSettlementCancelAPIView,
    VendorStatementAPIView,
)
from purchase.views.purchase_statutory import (
    PurchaseStatutoryChallanListCreateAPIView,
    PurchaseStatutoryChallanDepositAPIView,
    PurchaseStatutoryReturnListCreateAPIView,
    PurchaseStatutoryReturnFileAPIView,
    PurchaseStatutorySummaryAPIView,
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
    path("charge-types/", PurchaseChargeTypeListCreateAPIView.as_view(), name="purchase-charge-type-list"),
    path("charge-types/<int:pk>/", PurchaseChargeTypeRetrieveUpdateAPIView.as_view(), name="purchase-charge-type-detail"),
    path("tds-sections/", PurchaseTdsSectionListAPIView.as_view(), name="purchase-tds-sections-list"),
    path("entities/<int:entity_id>/tds-sections/", PurchaseTdsSectionListAPIView.as_view(), name="purchase-entity-tds-sections-list"),
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
    path("ap/open-items/", VendorBillOpenItemListAPIView.as_view(), name="purchase-ap-open-items-list"),
    path("ap/settlements/", VendorSettlementListCreateAPIView.as_view(), name="purchase-ap-settlement-list-create"),
    path("ap/settlements/<int:pk>/post/", VendorSettlementPostAPIView.as_view(), name="purchase-ap-settlement-post"),
    path("ap/settlements/<int:pk>/cancel/", VendorSettlementCancelAPIView.as_view(), name="purchase-ap-settlement-cancel"),
    path("ap/vendor-statement/", VendorStatementAPIView.as_view(), name="purchase-ap-vendor-statement"),
    path("statutory/challans/", PurchaseStatutoryChallanListCreateAPIView.as_view(), name="purchase-statutory-challan-list-create"),
    path("statutory/challans/<int:pk>/deposit/", PurchaseStatutoryChallanDepositAPIView.as_view(), name="purchase-statutory-challan-deposit"),
    path("statutory/returns/", PurchaseStatutoryReturnListCreateAPIView.as_view(), name="purchase-statutory-return-list-create"),
    path("statutory/returns/<int:pk>/file/", PurchaseStatutoryReturnFileAPIView.as_view(), name="purchase-statutory-return-file"),
    path("statutory/summary/", PurchaseStatutorySummaryAPIView.as_view(), name="purchase-statutory-summary"),
    path("settings/", PurchaseSettingsAPIView.as_view(), name="purchase-settings"),
    path("choices/", PurchaseCompiledChoicesAPIView.as_view(), name="purchase-compiled-choices"),
    path("purchase-invoices/search/", PurchaseInvoiceSearchAPIView.as_view(), name="purchase-invoice-search"),

]
