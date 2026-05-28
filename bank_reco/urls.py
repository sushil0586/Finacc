from django.urls import path

from .views import (
    BankRecoAuditTrailReportAPIView,
    BankRecoBrsReportAPIView,
    BankRecoCreateVoucherFromBankLineAPIView,
    BankRecoExceptionActionAPIView,
    BankRecoHealthAPIView,
    BankRecoGroupMatchAPIView,
    BankRecoImportCreateAPIView,
    BankRecoImportArchiveAPIView,
    BankRecoImportDetailAPIView,
    BankRecoImportPreviewAPIView,
    BankRecoImportAutoMatchAPIView,
    BankRecoImportLineListAPIView,
    BankRecoImportListAPIView,
    BankRecoImportValidateAPIView,
    BankRecoMetaAPIView,
    BankRecoMatchAPIView,
    BankRecoRunActionAPIView,
    BankRecoUnmatchedBankReportAPIView,
    BankRecoUnmatchedBooksReportAPIView,
    BankRecoUnmatchAPIView,
    BankRecoWorkspaceAPIView,
)


app_name = "bank_reco_api"

urlpatterns = [
    path("health/", BankRecoHealthAPIView.as_view(), name="bank-reco-health"),
    path("meta/", BankRecoMetaAPIView.as_view(), name="bank-reco-meta"),
    path("import/preview/", BankRecoImportPreviewAPIView.as_view(), name="bank-reco-import-preview"),
    path("import/", BankRecoImportCreateAPIView.as_view(), name="bank-reco-import-create"),
    path("imports/", BankRecoImportListAPIView.as_view(), name="bank-reco-import-list"),
    path("imports/<int:import_id>/", BankRecoImportDetailAPIView.as_view(), name="bank-reco-import-detail"),
    path("imports/<int:import_id>/archive/", BankRecoImportArchiveAPIView.as_view(), name="bank-reco-import-archive"),
    path("imports/<int:import_id>/lines/", BankRecoImportLineListAPIView.as_view(), name="bank-reco-import-lines"),
    path("imports/<int:import_id>/validate/", BankRecoImportValidateAPIView.as_view(), name="bank-reco-import-validate"),
    path("imports/<int:import_id>/auto-match/", BankRecoImportAutoMatchAPIView.as_view(), name="bank-reco-import-auto-match"),
    path("workspace/", BankRecoWorkspaceAPIView.as_view(), name="bank-reco-workspace"),
    path("match/", BankRecoMatchAPIView.as_view(), name="bank-reco-match"),
    path("group-match/", BankRecoGroupMatchAPIView.as_view(), name="bank-reco-group-match"),
    path("unmatch/", BankRecoUnmatchAPIView.as_view(), name="bank-reco-unmatch"),
    path("create-voucher-from-bank-line/", BankRecoCreateVoucherFromBankLineAPIView.as_view(), name="bank-reco-create-voucher-from-bank-line"),
    path("exception-action/", BankRecoExceptionActionAPIView.as_view(), name="bank-reco-exception-action"),
    path("runs/<int:run_id>/action/", BankRecoRunActionAPIView.as_view(), name="bank-reco-run-action"),
    path("reports/unmatched-bank/", BankRecoUnmatchedBankReportAPIView.as_view(), name="bank-reco-report-unmatched-bank"),
    path("reports/unmatched-books/", BankRecoUnmatchedBooksReportAPIView.as_view(), name="bank-reco-report-unmatched-books"),
    path("reports/audit-trail/", BankRecoAuditTrailReportAPIView.as_view(), name="bank-reco-report-audit-trail"),
    path("reports/brs/", BankRecoBrsReportAPIView.as_view(), name="bank-reco-report-brs"),
]
