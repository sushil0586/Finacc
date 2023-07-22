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
    path('balancesheet',views.balancestatement.as_view(), name = 'Trialbalance'),
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
    path('ledgerdetail1',views.ledgerapiApiView.as_view(), name = 'Trialbalance'),
    path('stockledgerdetails',views.stockledgerdetailsget.as_view(), name = 'Trialbalance'),
    path('stockledgerdetailpost',views.stockledgerdetails.as_view(), name = 'Trialbalance'),
    path('stockledgersummary',views.stockledgersummary.as_view(), name = 'Trialbalance'),
    path('stockledgersummarypost',views.stockledgersummarypost.as_view(), name = 'Trialbalance'),
    path('cashbookdetails',views.cashbookdetails.as_view(), name = 'Trialbalance'),
    path('daybookdetails',views.daydetails.as_view(), name = 'Trialbalance'),
    path('cashbook',views.cbviewapi.as_view(), name = 'Trialbalance'),
    path('salebook',views.salebyaccountapi.as_view(), name = 'salebok'),
    path('printvoucher',views.printvoucherapi.as_view(), name = 'salebok'),
    path('purchasebook',views.purchasebyaccountapi.as_view(), name = 'purchasebook'),
    path('daybook',views.daybookviewapi.as_view(), name = 'Trialbalance'),
    path('trialbalance',views.TrialbalanceApiView.as_view(), name = 'Trialbalance'),
    path('trialbalancebyaccounthead',views.TrialbalancebyaccountheadApiView.as_view(), name = 'Trialbalance'),
    path('trialbalancebyaccount',views.TrialbalancebyaccountApiView.as_view(), name = 'Trialbalance'),
    path('accountbalance',views.accountbalance.as_view(), name = 'Trialbalance'),
    path('netprofitbalance',views.netprofitbalance.as_view(), name = 'Trialbalance'),
    path('accountList',views.accountListapiview.as_view(), name = 'Trialbalance'),
    path('accountheadList',views.accountheadListapiview.as_view(), name = 'Trialbalance'),
    path('productlist',views.productListapiview.as_view(), name = 'Trialbalance'),
    path('productcategoryList',views.productcategoryListapiview.as_view(), name = 'Trialbalance'),
    path('stocktypeList',views.stocktypeListapiview.as_view(), name = 'Trialbalance'),
    path('accountbind',views.accountbindapiview.as_view(), name = 'Trialbalance'),


    

    

    


    

    

    


   # path('__debug__/', include(debug_toolbar.urls))


    
]