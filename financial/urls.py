from django.urls import path

from .views_meta import (
    AccountChoicesAPIView,
    AccountFormMetaAPIView,
    AccountingMastersMetaAPIView,
    LedgerFormMetaAPIView,
)
from .views_settings_hub import (
    SettingsHubAPIView,
    SettingsHubChoiceOverridesAPIView,
    SettingsHubLockPeriodsAPIView,
)
from .views_ledger import (
    AccountHeadV2ListCreateAPIView,
    AccountHeadV2RetrieveUpdateDestroyAPIView,
    AccountListPostV2APIView,
    AccountProfileV2ListCreateAPIView,
    AccountProfileV2RetrieveUpdateDestroyAPIView,
    AccountTypeV2ListCreateAPIView,
    AccountTypeV2RetrieveUpdateDestroyAPIView,
    BaseAccountListV2APIView,
    ContactDetailsByAccountView,
    ContactDetailsListCreateView,
    ContactDetailsRetrieveUpdateDestroyView,
    LedgerBalanceListAPIView,
    LedgerListCreateAPIView,
    LedgerRetrieveUpdateDestroyAPIView,
    LedgerSimpleListAPIView,
    ShippingDetailsByAccountView,
    ShippingDetailsListCreateAPIView,
    ShippingDetailsRetrieveUpdateDestroyView,
    SimpleAccountsV2APIView,
)
from .views_bulk_accounts import (
    AccountsBulkTemplateAPIView,
    AccountsBulkExportAPIView,
    AccountsBulkImportValidateAPIView,
    AccountsBulkImportCommitAPIView,
    AccountsBulkJobDetailAPIView,
    AccountsBulkJobErrorsExportAPIView,
)
from .views_invoice_custom_fields import (
    InvoiceCustomFieldDefinitionListCreateAPIView,
    InvoiceCustomFieldDefinitionDetailAPIView,
    InvoiceCustomFieldDefaultListCreateAPIView,
)


app_name = "financial"


urlpatterns = [
    # Canonical v2 endpoints (preferred)
    path("base-account-list-v2/", BaseAccountListV2APIView.as_view(), name="account-list-v2-canonical"),
    path("accounts/simple-v2", SimpleAccountsV2APIView.as_view(), name="account-simple-v2-canonical"),
    path("account-list-post-v2", AccountListPostV2APIView.as_view(), name="account-list-post-v2-canonical"),
    path("baseaccountlistv2/", BaseAccountListV2APIView.as_view(), name="account-list-v2"),
    path("meta/account-choices/", AccountChoicesAPIView.as_view(), name="meta-account-choices"),
    path("meta/account-form/", AccountFormMetaAPIView.as_view(), name="meta-account-form"),
    path("meta/accounting-masters/", AccountingMastersMetaAPIView.as_view(), name="meta-accounting-masters"),
    path("meta/ledger-form/", LedgerFormMetaAPIView.as_view(), name="meta-ledger-form"),
    path("settings-hub/", SettingsHubAPIView.as_view(), name="settings-hub"),
    path("settings-hub/<str:module>/lock-periods/", SettingsHubLockPeriodsAPIView.as_view(), name="settings-hub-lock-periods"),
    path("settings-hub/<str:module>/choice-overrides/", SettingsHubChoiceOverridesAPIView.as_view(), name="settings-hub-choice-overrides"),
    path("accounts/simplev2", SimpleAccountsV2APIView.as_view(), name="account-simple-v2"),
    path("accountListPostV2", AccountListPostV2APIView.as_view(), name="account-list-post-v2"),
    path("accounttypes-v2", AccountTypeV2ListCreateAPIView.as_view(), name="accounttype-v2-list-create"),
    path("accounttypes-v2/<int:pk>", AccountTypeV2RetrieveUpdateDestroyAPIView.as_view(), name="accounttype-v2-detail"),
    path("accountheads-v2", AccountHeadV2ListCreateAPIView.as_view(), name="accounthead-v2-list-create"),
    path("accountheads-v2/<int:pk>", AccountHeadV2RetrieveUpdateDestroyAPIView.as_view(), name="accounthead-v2-detail"),
    path("ledgers", LedgerListCreateAPIView.as_view(), name="ledger-list-create"),
    path("ledgers/<int:pk>", LedgerRetrieveUpdateDestroyAPIView.as_view(), name="ledger-detail"),
    path("ledgers/simple", LedgerSimpleListAPIView.as_view(), name="ledger-simple-list"),
    path("ledger-balances", LedgerBalanceListAPIView.as_view(), name="ledger-balance-list"),
    path("accounts-v2", AccountProfileV2ListCreateAPIView.as_view(), name="account-profile-v2-list-create"),
    path("accounts-v2/<int:pk>", AccountProfileV2RetrieveUpdateDestroyAPIView.as_view(), name="account-profile-v2-detail"),
    path("accounts-v2/bulk/template/", AccountsBulkTemplateAPIView.as_view(), name="accounts-v2-bulk-template"),
    path("accounts-v2/bulk/export/", AccountsBulkExportAPIView.as_view(), name="accounts-v2-bulk-export"),
    path("accounts-v2/bulk/import/validate/", AccountsBulkImportValidateAPIView.as_view(), name="accounts-v2-bulk-import-validate"),
    path("accounts-v2/bulk/import/commit/", AccountsBulkImportCommitAPIView.as_view(), name="accounts-v2-bulk-import-commit"),
    path("accounts-v2/bulk/jobs/<int:job_id>/", AccountsBulkJobDetailAPIView.as_view(), name="accounts-v2-bulk-job-detail"),
    path("accounts-v2/bulk/jobs/<int:job_id>/errors/", AccountsBulkJobErrorsExportAPIView.as_view(), name="accounts-v2-bulk-job-errors"),
    path("shipping-details/", ShippingDetailsListCreateAPIView.as_view(), name="shipping-details-list-create"),
    path("shipping-details/<int:pk>/", ShippingDetailsRetrieveUpdateDestroyView.as_view(), name="shipping-details-detail"),
    path("shipping-details/account/<int:account_id>/", ShippingDetailsByAccountView.as_view(), name="shipping-details-by-account"),
    path("contact-details/", ContactDetailsListCreateView.as_view(), name="contact-details-list-create"),
    path("contact-details/<int:pk>/", ContactDetailsRetrieveUpdateDestroyView.as_view(), name="contact-details-detail"),
    path("contact-details/account/<int:account_id>/", ContactDetailsByAccountView.as_view(), name="contact-details-by-account"),
    path("invoice-custom-fields/definitions/", InvoiceCustomFieldDefinitionListCreateAPIView.as_view(), name="invoice-custom-field-definitions"),
    path("invoice-custom-fields/definitions/<int:pk>/", InvoiceCustomFieldDefinitionDetailAPIView.as_view(), name="invoice-custom-field-definition-detail"),
    path("invoice-custom-fields/defaults/", InvoiceCustomFieldDefaultListCreateAPIView.as_view(), name="invoice-custom-field-defaults"),
]
