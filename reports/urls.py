from django.urls import path

from reports.api.financial import (
    BalanceSheetAPIView,
    FinancialReportsMetaAPIView,
    LedgerBookAPIView,
    ProfitAndLossAPIView,
    TrialBalanceAPIView,
)
from reports.api.assets_views import (
    AssetEventCSVAPIView,
    AssetEventExcelAPIView,
    AssetEventPDFAPIView,
    AssetEventPrintAPIView,
    AssetEventReportAPIView,
    AssetHistoryAPIView,
    DepreciationScheduleAPIView,
    DepreciationScheduleCSVAPIView,
    DepreciationScheduleExcelAPIView,
    DepreciationSchedulePDFAPIView,
    DepreciationSchedulePrintAPIView,
    FixedAssetRegisterAPIView,
    FixedAssetRegisterCSVAPIView,
    FixedAssetRegisterExcelAPIView,
    FixedAssetRegisterPDFAPIView,
    FixedAssetRegisterPrintAPIView,
)
from reports.api.book_views import CashbookAPIView, DaybookAPIView, DaybookEntryDetailAPIView
from reports.api.purchase_register_view import PurchaseRegisterAPIView
from reports.api.sales_register_view import SalesRegisterAPIView
from reports.api.receivables_views import (
    CustomerOutstandingReportAPIView,
    CustomerOutstandingCSVAPIView,
    CustomerOutstandingExcelAPIView,
    CustomerOutstandingPDFAPIView,
    CustomerOutstandingPrintAPIView,
    ReceivableAgingReportAPIView,
    ReceivableAgingCSVAPIView,
    ReceivableAgingExcelAPIView,
    ReceivableAgingPDFAPIView,
    ReceivableAgingPrintAPIView,
)


app_name = "reports"


urlpatterns = [
    path("financial/meta/", FinancialReportsMetaAPIView.as_view(), name="financial-meta"),
    path("financial/daybook/", DaybookAPIView.as_view(), name="financial-daybook"),
    path("financial/daybook/<int:entry_id>/", DaybookEntryDetailAPIView.as_view(), name="financial-daybook-detail"),
    path("financial/cashbook/", CashbookAPIView.as_view(), name="financial-cashbook"),
    path("purchases/register/", PurchaseRegisterAPIView.as_view(), name="purchase-register"),
    path("sales/register/", SalesRegisterAPIView.as_view(), name="sales-register"),
    path("financial/trial-balance/", TrialBalanceAPIView.as_view(), name="financial-trial-balance"),
    path("financial/ledger-book/", LedgerBookAPIView.as_view(), name="financial-ledger-book"),
    path("financial/profit-loss/", ProfitAndLossAPIView.as_view(), name="financial-profit-loss"),
    path("financial/balance-sheet/", BalanceSheetAPIView.as_view(), name="financial-balance-sheet"),
    path("fixed-assets/register/", FixedAssetRegisterAPIView.as_view(), name="fixed-asset-register"),
    path("fixed-assets/register/excel/", FixedAssetRegisterExcelAPIView.as_view(), name="fixed-asset-register-excel"),
    path("fixed-assets/register/pdf/", FixedAssetRegisterPDFAPIView.as_view(), name="fixed-asset-register-pdf"),
    path("fixed-assets/register/csv/", FixedAssetRegisterCSVAPIView.as_view(), name="fixed-asset-register-csv"),
    path("fixed-assets/register/print/", FixedAssetRegisterPrintAPIView.as_view(), name="fixed-asset-register-print"),
    path("fixed-assets/depreciation-schedule/", DepreciationScheduleAPIView.as_view(), name="depreciation-schedule"),
    path("fixed-assets/depreciation-schedule/excel/", DepreciationScheduleExcelAPIView.as_view(), name="depreciation-schedule-excel"),
    path("fixed-assets/depreciation-schedule/pdf/", DepreciationSchedulePDFAPIView.as_view(), name="depreciation-schedule-pdf"),
    path("fixed-assets/depreciation-schedule/csv/", DepreciationScheduleCSVAPIView.as_view(), name="depreciation-schedule-csv"),
    path("fixed-assets/depreciation-schedule/print/", DepreciationSchedulePrintAPIView.as_view(), name="depreciation-schedule-print"),
    path("fixed-assets/events/", AssetEventReportAPIView.as_view(), name="fixed-asset-events"),
    path("fixed-assets/events/excel/", AssetEventExcelAPIView.as_view(), name="fixed-asset-events-excel"),
    path("fixed-assets/events/pdf/", AssetEventPDFAPIView.as_view(), name="fixed-asset-events-pdf"),
    path("fixed-assets/events/csv/", AssetEventCSVAPIView.as_view(), name="fixed-asset-events-csv"),
    path("fixed-assets/events/print/", AssetEventPrintAPIView.as_view(), name="fixed-asset-events-print"),
    path("fixed-assets/history/", AssetHistoryAPIView.as_view(), name="fixed-asset-history"),
    path("receivables/customer-outstanding/", CustomerOutstandingReportAPIView.as_view(), name="customer-outstanding-report"),
    path("receivables/customer-outstanding/excel/", CustomerOutstandingExcelAPIView.as_view(), name="customer-outstanding-report-excel"),
    path("receivables/customer-outstanding/pdf/", CustomerOutstandingPDFAPIView.as_view(), name="customer-outstanding-report-pdf"),
    path("receivables/customer-outstanding/csv/", CustomerOutstandingCSVAPIView.as_view(), name="customer-outstanding-report-csv"),
    path("receivables/customer-outstanding/print/", CustomerOutstandingPrintAPIView.as_view(), name="customer-outstanding-report-print"),
    path("receivables/aging/", ReceivableAgingReportAPIView.as_view(), name="receivable-aging-report"),
    path("receivables/aging/excel/", ReceivableAgingExcelAPIView.as_view(), name="receivable-aging-report-excel"),
    path("receivables/aging/pdf/", ReceivableAgingPDFAPIView.as_view(), name="receivable-aging-report-pdf"),
    path("receivables/aging/csv/", ReceivableAgingCSVAPIView.as_view(), name="receivable-aging-report-csv"),
    path("receivables/aging/print/", ReceivableAgingPrintAPIView.as_view(), name="receivable-aging-report-print"),
]
