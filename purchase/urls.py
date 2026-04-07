from django.urls import path

from purchase.views.purchase_invoice import (
    PurchaseInvoiceListCreateAPIView,
    PurchaseInvoiceRetrieveUpdateDestroyAPIView,
    PurchaseServiceInvoiceListCreateAPIView,
    PurchaseServiceInvoiceRetrieveUpdateDestroyAPIView,
    PurchaseInvoiceSearchAPIView,
)
from purchase.views.purchase_attachment import (
    PurchaseInvoiceAttachmentDeleteAPIView,
    PurchaseInvoiceAttachmentDownloadAPIView,
    PurchaseInvoiceAttachmentListCreateAPIView,
)

from purchase.views.purchase_charge_type import (
    PurchaseChargeTypeListCreateAPIView,
    PurchaseChargeTypeRetrieveUpdateAPIView,
)
from purchase.views.purchase_withholding import PurchaseTdsSectionListAPIView

from purchase.views.purchase_choices import PurchaseCompiledChoicesAPIView
from purchase.views.purchase_meta import (
    PurchaseApMetaAPIView,
    PurchaseApSettlementFormMetaAPIView,
    PurchaseInvoiceDetailFormMetaAPIView,
    PurchaseInvoiceFormMetaAPIView,
    PurchaseInvoiceLinesMetaAPIView,
    PurchaseInvoiceSearchMetaAPIView,
    PurchaseInvoiceSummaryAPIView,
    PurchaseSettingsMetaAPIView,
    PurchaseStatutoryMetaAPIView,
    PurchaseWithholdingMetaAPIView,
)

from purchase.views.purchase_settings import PurchaseSettingsAPIView

from purchase.views.purchase_invoice_actions import (
    PurchaseInvoiceConfirmAPIView,
    PurchaseInvoicePostAPIView,
    PurchaseInvoiceUnpostAPIView,
    PurchaseInvoiceCancelAPIView,
    PurchaseInvoiceRebuildTaxSummaryAPIView,
    PurchaseInvoiceCreateCreditNoteAPIView,
    PurchaseInvoiceCreateDebitNoteAPIView,
    PurchaseInvoiceITCBlockAPIView,
    PurchaseInvoiceITCUnblockAPIView,
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
    VendorAdvanceBalanceListAPIView,
    VendorBillOpenItemListAPIView,
    VendorSettlementListCreateAPIView,
    VendorSettlementPostAPIView,
    VendorSettlementCancelAPIView,
    VendorStatementAPIView,
)
from purchase.views.purchase_statutory import (
    PurchaseStatutoryChallanListCreateAPIView,
    PurchaseStatutoryChallanDepositAPIView,
    PurchaseStatutoryChallanCancelAPIView,
    PurchaseStatutoryChallanApprovalAPIView,
    PurchaseStatutoryChallanEligibleLinesAPIView,
    PurchaseStatutoryChallanDetailAPIView,
    PurchaseStatutoryChallanExportAPIView,
    PurchaseStatutoryChallanPreviewNoAPIView,
    PurchaseStatutoryReturnListCreateAPIView,
    PurchaseStatutoryReturnFileAPIView,
    PurchaseStatutoryReturnCancelAPIView,
    PurchaseStatutoryReturnApprovalAPIView,
    PurchaseStatutoryReturnEligibleLinesAPIView,
    PurchaseStatutoryReturnDetailAPIView,
    PurchaseStatutoryReturnExportAPIView,
    PurchaseStatutorySummaryAPIView,
    PurchaseStatutoryItcStatusRegisterAPIView,
    PurchaseStatutoryReconciliationExceptionsAPIView,
    PurchaseStatutoryGlReconciliationAPIView,
    PurchaseStatutoryReturnNsdlExportAPIView,
    PurchaseStatutoryReturnForm16AIssueAPIView,
    PurchaseStatutoryReturnForm16ADownloadAPIView,
    PurchaseStatutoryReturnForm16AOfficialUploadAPIView,
    PurchaseStatutoryCaPackExportAPIView,
)
from purchase.views.purchase_gstr2b import (
    PurchaseGstr2bImportBatchListCreateAPIView,
    PurchaseGstr2bImportBatchRowsAPIView,
    PurchaseGstr2bImportBatchMatchAPIView,
    PurchaseGstr2bImportRowReviewAPIView,
)

urlpatterns = [
    # CRUD
    path("purchase-invoices/", PurchaseInvoiceListCreateAPIView.as_view(), name="purchase-invoice-list-create"),
    path("purchase-invoices/<int:pk>/", PurchaseInvoiceRetrieveUpdateDestroyAPIView.as_view(), name="purchase-invoice-rud"),
    path("purchase-invoices/<int:pk>/attachments/", PurchaseInvoiceAttachmentListCreateAPIView.as_view(), name="purchase-invoice-attachments"),
    path("purchase-invoices/<int:pk>/attachments/<int:attachment_id>/", PurchaseInvoiceAttachmentDeleteAPIView.as_view(), name="purchase-invoice-attachment-delete"),
    path("purchase-invoices/<int:pk>/attachments/<int:attachment_id>/download/", PurchaseInvoiceAttachmentDownloadAPIView.as_view(), name="purchase-invoice-attachment-download"),
    path("purchase-service-invoices/", PurchaseServiceInvoiceListCreateAPIView.as_view(), name="purchase-service-invoice-list-create"),
    path("purchase-service-invoices/<int:pk>/", PurchaseServiceInvoiceRetrieveUpdateDestroyAPIView.as_view(), name="purchase-service-invoice-rud"),
    path("purchase-service-invoices/<int:pk>/attachments/", PurchaseInvoiceAttachmentListCreateAPIView.as_view(), name="purchase-service-invoice-attachments"),
    path("purchase-service-invoices/<int:pk>/attachments/<int:attachment_id>/", PurchaseInvoiceAttachmentDeleteAPIView.as_view(), name="purchase-service-invoice-attachment-delete"),
    path("purchase-service-invoices/<int:pk>/attachments/<int:attachment_id>/download/", PurchaseInvoiceAttachmentDownloadAPIView.as_view(), name="purchase-service-invoice-attachment-download"),

    # Actions
    path("purchase-invoices/<int:pk>/confirm/", PurchaseInvoiceConfirmAPIView.as_view(), name="purchase-invoice-confirm"),
    path("purchase-invoices/<int:pk>/post/", PurchaseInvoicePostAPIView.as_view(), name="purchase-invoice-post"),
    path("purchase-invoices/<int:pk>/unpost/", PurchaseInvoiceUnpostAPIView.as_view(), name="purchase-invoice-unpost"),
    path("purchase-invoices/<int:pk>/cancel/", PurchaseInvoiceCancelAPIView.as_view(), name="purchase-invoice-cancel"),
    path("purchase-invoices/<int:pk>/rebuild-tax-summary/", PurchaseInvoiceRebuildTaxSummaryAPIView.as_view(), name="purchase-invoice-rebuild-tax-summary"),
    path("purchase-service-invoices/<int:pk>/confirm/", PurchaseInvoiceConfirmAPIView.as_view(), name="purchase-service-invoice-confirm"),
    path("purchase-service-invoices/<int:pk>/post/", PurchaseInvoicePostAPIView.as_view(), name="purchase-service-invoice-post"),
    path("purchase-service-invoices/<int:pk>/unpost/", PurchaseInvoiceUnpostAPIView.as_view(), name="purchase-service-invoice-unpost"),
    path("purchase-service-invoices/<int:pk>/cancel/", PurchaseInvoiceCancelAPIView.as_view(), name="purchase-service-invoice-cancel"),
    path("purchase-service-invoices/<int:pk>/rebuild-tax-summary/", PurchaseInvoiceRebuildTaxSummaryAPIView.as_view(), name="purchase-service-invoice-rebuild-tax-summary"),
    path("charge-types/", PurchaseChargeTypeListCreateAPIView.as_view(), name="purchase-charge-type-list"),
    path("charge-types/<int:pk>/", PurchaseChargeTypeRetrieveUpdateAPIView.as_view(), name="purchase-charge-type-detail"),
    path("tds-sections/", PurchaseTdsSectionListAPIView.as_view(), name="purchase-tds-sections-list"),
    path("entities/<int:entity_id>/tds-sections/", PurchaseTdsSectionListAPIView.as_view(), name="purchase-entity-tds-sections-list"),
    # CN/DN from Invoice
    path("purchase-invoices/<int:pk>/create-credit-note/", PurchaseInvoiceCreateCreditNoteAPIView.as_view(), name="purchase-invoice-create-credit-note"),
    path("purchase-invoices/<int:pk>/create-debit-note/", PurchaseInvoiceCreateDebitNoteAPIView.as_view(), name="purchase-invoice-create-debit-note"),
    path("purchase-service-invoices/<int:pk>/create-credit-note/", PurchaseInvoiceCreateCreditNoteAPIView.as_view(), name="purchase-service-invoice-create-credit-note"),
    path("purchase-service-invoices/<int:pk>/create-debit-note/", PurchaseInvoiceCreateDebitNoteAPIView.as_view(), name="purchase-service-invoice-create-debit-note"),

    # ITC actions
    path("purchase-invoices/<int:pk>/itc/block/", PurchaseInvoiceITCBlockAPIView.as_view(), name="purchase-invoice-itc-block"),
    path("purchase-invoices/<int:pk>/itc/unblock/", PurchaseInvoiceITCUnblockAPIView.as_view(), name="purchase-invoice-itc-unblock"),
    path("purchase-invoices/<int:pk>/itc/pending/", PurchaseInvoiceITCPendingAPIView.as_view(), name="purchase-invoice-itc-pending"),
    path("purchase-invoices/<int:pk>/itc/claim/", PurchaseInvoiceITCClaimAPIView.as_view(), name="purchase-invoice-itc-claim"),
    path("purchase-invoices/<int:pk>/itc/reverse/", PurchaseInvoiceITCReverseAPIView.as_view(), name="purchase-invoice-itc-reverse"),
    path("purchase-service-invoices/<int:pk>/itc/block/", PurchaseInvoiceITCBlockAPIView.as_view(), name="purchase-service-invoice-itc-block"),
    path("purchase-service-invoices/<int:pk>/itc/unblock/", PurchaseInvoiceITCUnblockAPIView.as_view(), name="purchase-service-invoice-itc-unblock"),
    path("purchase-service-invoices/<int:pk>/itc/pending/", PurchaseInvoiceITCPendingAPIView.as_view(), name="purchase-service-invoice-itc-pending"),
    path("purchase-service-invoices/<int:pk>/itc/claim/", PurchaseInvoiceITCClaimAPIView.as_view(), name="purchase-service-invoice-itc-claim"),
    path("purchase-service-invoices/<int:pk>/itc/reverse/", PurchaseInvoiceITCReverseAPIView.as_view(), name="purchase-service-invoice-itc-reverse"),

    # GSTR-2B
    path("purchase-invoices/<int:pk>/gstr2b/status/", PurchaseInvoice2BMatchStatusAPIView.as_view(), name="purchase-invoice-2b-status"),
    path("purchase-service-invoices/<int:pk>/gstr2b/status/", PurchaseInvoice2BMatchStatusAPIView.as_view(), name="purchase-service-invoice-2b-status"),
     
    # Read-only lists
    path("purchase-lines/", PurchaseInvoiceLinesListAPIView.as_view(), name="purchase-lines-list"),
    path("purchase-tax-summaries/", PurchaseTaxSummaryListAPIView.as_view(), name="purchase-tax-summaries-list"),
    path("ap/open-items/", VendorBillOpenItemListAPIView.as_view(), name="purchase-ap-open-items-list"),
    path("ap/open-advances/", VendorAdvanceBalanceListAPIView.as_view(), name="purchase-ap-open-advances-list"),
    path("ap/settlements/", VendorSettlementListCreateAPIView.as_view(), name="purchase-ap-settlement-list-create"),
    path("ap/settlements/<int:pk>/post/", VendorSettlementPostAPIView.as_view(), name="purchase-ap-settlement-post"),
    path("ap/settlements/<int:pk>/cancel/", VendorSettlementCancelAPIView.as_view(), name="purchase-ap-settlement-cancel"),
    path("ap/vendor-statement/", VendorStatementAPIView.as_view(), name="purchase-ap-vendor-statement"),
    path("statutory/challans/", PurchaseStatutoryChallanListCreateAPIView.as_view(), name="purchase-statutory-challan-list-create"),
    path("statutory/challans/export", PurchaseStatutoryChallanExportAPIView.as_view(), name="purchase-statutory-challan-export"),
    path("statutory/challans/export/", PurchaseStatutoryChallanExportAPIView.as_view(), name="purchase-statutory-challan-export-slash"),
    path("statutory/challans/preview-no/", PurchaseStatutoryChallanPreviewNoAPIView.as_view(), name="purchase-statutory-challan-preview-no"),
    path("statutory/challans/eligible-lines/", PurchaseStatutoryChallanEligibleLinesAPIView.as_view(), name="purchase-statutory-challan-eligible-lines"),
    path("statutory/challans/<int:pk>/", PurchaseStatutoryChallanDetailAPIView.as_view(), name="purchase-statutory-challan-detail"),
    path("statutory/challans/<int:pk>/deposit/", PurchaseStatutoryChallanDepositAPIView.as_view(), name="purchase-statutory-challan-deposit"),
    path("statutory/challans/<int:pk>/cancel/", PurchaseStatutoryChallanCancelAPIView.as_view(), name="purchase-statutory-challan-cancel"),
    path("statutory/challans/<int:pk>/approval/", PurchaseStatutoryChallanApprovalAPIView.as_view(), name="purchase-statutory-challan-approval"),
    path("statutory/returns/", PurchaseStatutoryReturnListCreateAPIView.as_view(), name="purchase-statutory-return-list-create"),
    path("statutory/returns/export", PurchaseStatutoryReturnExportAPIView.as_view(), name="purchase-statutory-return-export"),
    path("statutory/returns/export/", PurchaseStatutoryReturnExportAPIView.as_view(), name="purchase-statutory-return-export-slash"),
    path("statutory/returns/eligible-lines/", PurchaseStatutoryReturnEligibleLinesAPIView.as_view(), name="purchase-statutory-return-eligible-lines"),
    path("statutory/returns/<int:pk>/", PurchaseStatutoryReturnDetailAPIView.as_view(), name="purchase-statutory-return-detail"),
    path("statutory/returns/<int:pk>/file/", PurchaseStatutoryReturnFileAPIView.as_view(), name="purchase-statutory-return-file"),
    path("statutory/returns/<int:pk>/cancel/", PurchaseStatutoryReturnCancelAPIView.as_view(), name="purchase-statutory-return-cancel"),
    path("statutory/returns/<int:pk>/approval/", PurchaseStatutoryReturnApprovalAPIView.as_view(), name="purchase-statutory-return-approval"),
    path("statutory/returns/<int:pk>/nsdl-export/", PurchaseStatutoryReturnNsdlExportAPIView.as_view(), name="purchase-statutory-return-nsdl-export"),
    path("statutory/returns/<int:pk>/form16a/", PurchaseStatutoryReturnForm16AIssueAPIView.as_view(), name="purchase-statutory-return-form16a"),
    path("statutory/returns/<int:pk>/form16a/<int:issue_no>/download/", PurchaseStatutoryReturnForm16ADownloadAPIView.as_view(), name="purchase-statutory-return-form16a-download"),
    path("statutory/returns/<int:pk>/form16a/<int:issue_no>/official-upload/", PurchaseStatutoryReturnForm16AOfficialUploadAPIView.as_view(), name="purchase-statutory-return-form16a-official-upload"),
    path("statutory/summary/", PurchaseStatutorySummaryAPIView.as_view(), name="purchase-statutory-summary"),
    path("statutory/itc-status-register/", PurchaseStatutoryItcStatusRegisterAPIView.as_view(), name="purchase-statutory-itc-status-register"),
    path("statutory/reconciliation-exceptions/", PurchaseStatutoryReconciliationExceptionsAPIView.as_view(), name="purchase-statutory-reconciliation-exceptions"),
    path("statutory/reconciliation-gl/", PurchaseStatutoryGlReconciliationAPIView.as_view(), name="purchase-statutory-reconciliation-gl"),
    path("statutory/export/ca-pack/", PurchaseStatutoryCaPackExportAPIView.as_view(), name="purchase-statutory-ca-pack-export"),
    path("settings/", PurchaseSettingsAPIView.as_view(), name="purchase-settings"),
    path("choices/", PurchaseCompiledChoicesAPIView.as_view(), name="purchase-compiled-choices"),
    path("meta/invoice-form/", PurchaseInvoiceFormMetaAPIView.as_view(), name="purchase-invoice-form-meta"),
    path("meta/invoice-detail-form/", PurchaseInvoiceDetailFormMetaAPIView.as_view(), name="purchase-invoice-detail-form-meta"),
    path("meta/invoice-search/", PurchaseInvoiceSearchMetaAPIView.as_view(), name="purchase-invoice-search-meta"),
    path("meta/invoice-lines/", PurchaseInvoiceLinesMetaAPIView.as_view(), name="purchase-invoice-lines-meta"),
    path("meta/settings/", PurchaseSettingsMetaAPIView.as_view(), name="purchase-settings-meta"),
    path("meta/withholding/", PurchaseWithholdingMetaAPIView.as_view(), name="purchase-withholding-meta"),
    path("meta/statutory/", PurchaseStatutoryMetaAPIView.as_view(), name="purchase-statutory-meta"),
    path("purchase-invoices/<int:pk>/summary/", PurchaseInvoiceSummaryAPIView.as_view(), name="purchase-invoice-summary"),
    path("purchase-service-invoices/search/", PurchaseServiceInvoiceListCreateAPIView.as_view(), name="purchase-service-invoice-search"),
    path("purchase-service-invoices/<int:pk>/summary/", PurchaseInvoiceSummaryAPIView.as_view(), name="purchase-service-invoice-summary"),
    path("ap/meta/", PurchaseApMetaAPIView.as_view(), name="purchase-ap-meta"),
    path("ap/meta/settlement-form/", PurchaseApSettlementFormMetaAPIView.as_view(), name="purchase-ap-settlement-form-meta"),
    path("purchase-invoices/search/", PurchaseInvoiceSearchAPIView.as_view(), name="purchase-invoice-search"),
    path("gstr2b/import-batches/", PurchaseGstr2bImportBatchListCreateAPIView.as_view(), name="purchase-gstr2b-import-batch-list-create"),
    path("gstr2b/import-batches/<int:pk>/rows/", PurchaseGstr2bImportBatchRowsAPIView.as_view(), name="purchase-gstr2b-import-batch-rows"),
    path("gstr2b/import-batches/<int:pk>/match/", PurchaseGstr2bImportBatchMatchAPIView.as_view(), name="purchase-gstr2b-import-batch-match"),
    path("gstr2b/import-rows/<int:pk>/review/", PurchaseGstr2bImportRowReviewAPIView.as_view(), name="purchase-gstr2b-import-row-review"),

]
