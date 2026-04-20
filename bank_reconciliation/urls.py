from django.urls import path

from .views import (
    BankReconciliationAutoMatchAPIView,
    BankReconciliationCandidatesAPIView,
    BankReconciliationHubAPIView,
    BankReconciliationImportAPIView,
    BankReconciliationExceptionAPIView,
    BankReconciliationExceptionResolveAPIView,
    BankReconciliationManualMatchAPIView,
    BankReconciliationOptionsAPIView,
    BankReconciliationLockAPIView,
    BankReconciliationPreviewAPIView,
    BankStatementImportProfileAPIView,
    BankReconciliationUnmatchAPIView,
    BankReconciliationSplitMatchAPIView,
    BankReconciliationSummaryAPIView,
    BankReconciliationSessionDetailAPIView,
    BankReconciliationSessionListCreateAPIView,
    BankReconciliationUploadAPIView,
)


app_name = "bank_reconciliation_api"

urlpatterns = [
    path("meta/", BankReconciliationHubAPIView.as_view(), name="bank-reconciliation-hub"),
    path("options/", BankReconciliationOptionsAPIView.as_view(), name="bank-reconciliation-options"),
    path("sessions/", BankReconciliationSessionListCreateAPIView.as_view(), name="bank-reconciliation-session-list"),
    path("sessions/<int:session_id>/", BankReconciliationSessionDetailAPIView.as_view(), name="bank-reconciliation-session-detail"),
    path("sessions/<int:session_id>/imports/", BankReconciliationImportAPIView.as_view(), name="bank-reconciliation-session-imports"),
    path("sessions/<int:session_id>/imports/upload/", BankReconciliationUploadAPIView.as_view(), name="bank-reconciliation-session-import-upload"),
    path("sessions/<int:session_id>/imports/preview/", BankReconciliationPreviewAPIView.as_view(), name="bank-reconciliation-session-import-preview"),
    path("profiles/", BankStatementImportProfileAPIView.as_view(), name="bank-reconciliation-import-profiles"),
    path("sessions/<int:session_id>/candidates/", BankReconciliationCandidatesAPIView.as_view(), name="bank-reconciliation-session-candidates"),
    path("sessions/<int:session_id>/auto-match/", BankReconciliationAutoMatchAPIView.as_view(), name="bank-reconciliation-session-auto-match"),
    path("sessions/<int:session_id>/match/", BankReconciliationManualMatchAPIView.as_view(), name="bank-reconciliation-session-manual-match"),
    path("sessions/<int:session_id>/unmatch/", BankReconciliationUnmatchAPIView.as_view(), name="bank-reconciliation-session-unmatch"),
    path("sessions/<int:session_id>/split-match/", BankReconciliationSplitMatchAPIView.as_view(), name="bank-reconciliation-session-split-match"),
    path("sessions/<int:session_id>/exceptions/", BankReconciliationExceptionAPIView.as_view(), name="bank-reconciliation-session-exceptions"),
    path("sessions/<int:session_id>/exceptions/resolve/", BankReconciliationExceptionResolveAPIView.as_view(), name="bank-reconciliation-session-exception-resolve"),
    path("sessions/<int:session_id>/summary/", BankReconciliationSummaryAPIView.as_view(), name="bank-reconciliation-session-summary"),
    path("sessions/<int:session_id>/lock/", BankReconciliationLockAPIView.as_view(), name="bank-reconciliation-session-lock"),
]
