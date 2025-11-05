from django.urls import path,include
from reports import views



app_name = 'reports'


urlpatterns  = [
    path('closingstockview', views.closingstocknew.as_view(), name='closingstockView'),
    path('closingstockbalance', views.closingstockBalance.as_view(), name='closingstockView'),
    path('closingstock', views.closingstockView.as_view(), name='closingstockView'),
    path('dashboardkpis',views.dashboardkpis.as_view(), name = 'Trialbalance'),
    path('dashboardgraphkpis',views.dashboardgraphkpis.as_view(), name = 'Trialbalance'),
    path('tradingaccountstatement',views.tradingaccountstatement.as_view(), name = 'Trialbalance'),
    path('balancesheet',views.BalanceStatement.as_view(), name = 'Trialbalance'),
    path('gstr1hsnapi',views.gstrhsnapi.as_view(), name = 'Trialbalance'),
    path('gstr1b2csmallapi',views.gstr1b2csmallapi.as_view(), name = 'Trialbalance'),
    path('gstr1b2clargeapi',views.gstr1b2clargeapi.as_view(), name = 'Trialbalance'),
    path('gstr1b2baapi',views.gstr1b2baapi.as_view(), name = 'Trialbalance'),
    path('gstr1b2bapi',views.gstr1b2bapi.as_view(), name = 'Trialbalance'),
    path('incomeandexpensesstatement',views.incomeandexpensesstatement.as_view(), name = 'Trialbalance'),
    path('stockledgerbook',views.stockledgerbookapi.as_view(), name = 'Trialbalance'),
    path('ledgersummary',views.ledgersummarylatestget.as_view(), name = 'Trialbalance'),
    path('ledgersummarypost',views.ledgersummarylatest.as_view(), name = 'Trialbalance'),
    path('ledgerbook',views.ledgerviewapi.as_view(), name = 'Trialbalance'),
    path('ledgerdetails',views.ledgerdetails.as_view(), name = 'Trialbalance'),
    path('interestdetails',views.interestdetails.as_view(), name = 'Trialbalance'),
    path('gstr3b1',views.gstr3b1.as_view(), name = 'Trialbalance'),

    
    path('ledgerdetail1',views.ledgerapiApiView.as_view(), name = 'Trialbalance'),
    path('stockledgerdetails',views.stockledgerdetailsget.as_view(), name = 'Trialbalance'),
    path('stockledgerdetailpost',views.stockledgerdetails.as_view(), name = 'Trialbalance'),
    path('stockledgersummary',views.stockledgersummary.as_view(), name = 'Trialbalance'),
    path('stockledgersummarypost',views.stockledgersummarypost.as_view(), name = 'Trialbalance'),
    path('cashbookdetails',views.cashbookdetails.as_view(), name = 'Trialbalance'),
    path('cashbooksummary',views.cashbooksummary.as_view(), name = 'Trialbalance'),
    
    path('daybookdetails',views.DayDetails.as_view(), name = 'Trialbalance'),
    path('cashbook',views.cbviewapi.as_view(), name = 'Trialbalance'),
    path('salebook',views.salebyaccountapi.as_view(), name = 'salebok'),
    path('printvoucher',views.printvoucherapi.as_view(), name = 'salebok'),
    path('purchasebook',views.purchasebyaccountapi.as_view(), name = 'purchasebook'),
    path('daybook',views.daybookviewapi.as_view(), name = 'Trialbalance'),
    path('trialbalance',views.TrialbalanceApiView.as_view(), name = 'Trialbalance'),
    path('trialbalancenew',views.TrialBalanceViewFinal.as_view(), name = 'Trialbalance'),
    path('trialbalancebyaccounthead',views.TrialbalancebyaccountheadApiView.as_view(), name = 'Trialbalance'),
    path('trialbalancebyaccountheadnew',views.TrialBalanceViewaccountFinal.as_view(), name = 'Trialbalance'),
    
    path('trialbalancebyaccount',views.TrialbalancebyaccountApiView.as_view(), name = 'Trialbalance'),
    path('accountbalance',views.accountbalance.as_view(), name = 'Trialbalance'),
    path('netprofitbalance',views.netprofitbalance.as_view(), name = 'Trialbalance'),
    path('accountList',views.accountListapiview.as_view(), name = 'Trialbalance'),
    path('accountheadList',views.accountheadListapiview.as_view(), name = 'Trialbalance'),
    path('productlist',views.productListapiview.as_view(), name = 'Trialbalance'),
    path('productcategoryList',views.productcategoryListapiview.as_view(), name = 'Trialbalance'),
    path('stocktypeList',views.stocktypeListapiview.as_view(), name = 'Trialbalance'),
    path('accountbind',views.accountbindapiview.as_view(), name = 'Trialbalance'),
    path('stock-summary/', views.StockSummaryAPIView.as_view(), name='stock-summary'),
    path('stock-day-book/', views.StockDayBookReportView.as_view(), name='stock-day-book'),
    path('stockbooksummary/', views.StockSummaryView.as_view(), name='stock-day-book'),
    path('stockbookreport/', views.StockLedgerBookView.as_view(), name='stock-day-book'),
    path('transaction-types/', views.TransactionTypeListView.as_view(), name='transaction-type-list'),
    path('accounts-receivable-aging/', views.AccountsReceivableAgingReport.as_view(), name='accounts-receivable-aging'),
    path('accounts-payable-aging/', views.AccountsPayableAgingReportView.as_view(), name='accounts-receivable-aging'),
    path('emialculator/', views.EMICalculatorAPIView.as_view(), name='accounts-receivable-aging'),
    path('sales-order-gst-summary/', views.GSTSummaryView.as_view(), name='sales-order-gst-summary'),
    path('trial-balance/', views.TrialbalanceApiViewJournal.as_view(), name='sales-order-gst-summary'),
    path('trial-balance/accounts/', views.TrialbalanceApiViewJournalByAccount.as_view(), name='sales-order-gst-summary'),
    path('cash_book/', views.CashBookAPIView.as_view(), name='sales-order-gst-summary'),
    path('day_book/', views.DayBookAPIView.as_view(), name='sales-order-gst-summary'),
    path('day_book-xlsx/', views.DayBookExcelAPIView.as_view(), name='sales-order-gst-summary'),
    path('day_book-pdf/', views.DayBookPDFAPIView.as_view(), name='sales-order-gst-summary'),

    
    
    
    path('trial-balance/account-ledger/', views.TrialbalanceApiViewJournalByAccountLedger.as_view(), name='sales-order-gst-summary'),
    path("ledger-summary", views.LedgerSummaryJournalline.as_view(), name="ledger-summary"),
    path("ledger-summary-excel", views.LedgerSummaryExcelAPIView.as_view(), name="ledger-summary"),
    path("ledger-summary-pdf", views.LedgerSummaryPDFAPIView.as_view(), name="ledger-summary"),
    path("ledger-details", views.ledgerjournaldetails.as_view(), name="ledger-details"),
    path("trading-account", views.tradingaccountstatementJournaline.as_view(), name="ledger-details"),
    path("profitloss-account", views.profitandlossstatement.as_view(), name="ledger-details"),
    path("balancesheet-statement", views.balancesheetstatement.as_view(), name="ledger-details"),
    path("balance-sheet.xlsx", views.BalanceSheetExcelAPIView.as_view(), name="balance-sheet-excel"),
    path("balance-sheetpdf", views.BalanceSheetPDFAPIView.as_view(), name="balance-sheet-pdf"),
    path("trial-balance.xlsx", views.TrialbalanceExcelApiView.as_view(), name="trial-balance-excel"),
    path("trading-account-xlsx", views.TradingAccountExcelAPIView.as_view(),name="trading-account.xlsx"),
    path("trading-account-pdf", views.TradingAccountPDFAPIView.as_view(),name="trading-account.xlsx"),
    path("profitloss-account-xlsx", views.ProfitAndLossExcelAPIView.as_view(),name="trading-account.xlsx"),
    path("profitloss-account-pdf", views.ProfitAndLossPDFAPIView.as_view(),name="trading-account.xlsx"),
    path("cashbook-xlsx", views.CashBookExcelAPIView.as_view(), name="cashbook-excel"),
    path("cashbook-pdf", views.CashBookPDFAPIView.as_view(), name="cashbook-excel"),
    path("ledger-details-xlsx", views.LedgerJournalExcelAPIView.as_view(), name="ledger-details"),
    path("ledger-details-pdf", views.LedgerJournalPDFAPIView.as_view(), name="ledger-details"),

    
    
    

    

    


    

    

    


    

    

    


   # path('__debug__/', include(debug_toolbar.urls))


    
]