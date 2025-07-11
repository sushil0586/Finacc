from django.urls import path
from invoice import views
from .views import PurchaseOrderAttachmentAPIView, PurchaseOrderAttachmentDownloadAPIView, PurchaseOrderAttachmentDeleteAPIView


app_name = 'invoice'

urlpatterns  = [

   
    path('purchaseimport',views.purchaseorderimportApiView.as_view(),name = 'salesorder'),
    path('purchaseimport/<int:id>',views.purchaseorderimportupdatedelview.as_view(),name = 'salesorder'),
    path('saleinvoice',views.SalesOderHeaderApiView.as_view(),name = 'salesorder'),
    path('salesorder',views.SalesOderApiView.as_view(),name = 'salesorder'),
    path('gstorderservices',views.gstorderservicesApiView.as_view(),name = 'saleservices'),
    path('gstorderservices/<int:id>',views.gstserviceupdatedelview.as_view(), name = 'salesorder'),
    path('gstservicesvbno/<int:billno>',views.gstserviceprevnextview.as_view(), name = 'salesorder'),
    path('jobworkchalan',views.jobworkchalanApiView.as_view(),name = 'saleservices'),
    path('jobworkchalan/<int:id>',views.jobworkchalanupdatedelview.as_view(), name = 'salesorder'),
    path('jobworkchalanvbno/<int:voucherno>',views.jobworkchalanpreviousview.as_view(), name = 'salesorder'),
    path('saleinvoice/<int:id>',views.salesOrderupdatedelview.as_view(), name = 'salesorder'),
    path('salesorder/<int:id>',views.saleOrderupdatedelview.as_view(), name = 'salesorder'),
    path('saleinvoicepdf/<int:id>',views.salesOrderpdfview.as_view(), name = 'salesorder'),
    path('sales-order-pdf/',views.SalesOrderPDFViewprint.as_view(), name = 'salesorder'),
    path('salepdf',views.salesorderpdf.as_view(), name = 'salesorder'),
    path('salesorderdetails',views.salesOrderdetailsApiView.as_view(),name = 'salesorder'),
    # path('salesorderdetails/<int:id>',views.salesOrderdetailsApiView.as_view(), name = 'salesorder'),
    path('purchaseinvoice',views.purchaseorderApiView.as_view(),name = 'purchaseorder'),
    path('purchaseinvoice/<int:id>',views.purchaseorderupdatedelview.as_view(), name = 'purchaseorder'),
    path('purchaseorder',views.newpurchaseorderApiView.as_view(),name = 'purchaseorder'),
    path('purchaseorder/<int:id>',views.newpurchaseorderupdatedelview.as_view(), name = 'purchaseorder'),
    # path('purchaseorderdetails',views.PurchaseOrderDetailsApiView.as_view(),name = 'purchaseorder'),
    # path('purchaseorderdetails/<int:id>',views.purchaseorderupdatedelview.as_view(), name = 'purchaseorder'),
    path('voucherno',views.purchaseordelatestview.as_view(), name = 'purchaseorder'),
    path('povoucherno',views.newpurchaseordelatestview.as_view(), name = 'purchaseorder'),
    path('billno',views.salesorderlatestview.as_view(), name = 'purchaseorder'),
    path('sobillno',views.saleorderlatestview.as_view(), name = 'purchaseorder'),
    path('gstservicesbillno',views.gstorderlatestview.as_view(), name = 'purchaseorder'),
    path('jobworkbillno',views.jobworklatestview.as_view(), name = 'purchaseorder'),
    path('prbillno',views.purchasereturnlatestview.as_view(), name = 'purchaseorder'),
    path('journal',views.JournalApiView.as_view(), name = 'journal'),
    path('srvoucherno',views.salesreturnlatestview.as_view(), name = 'journal'),
    path('pivoucherno',views.purchaseimportlatestview.as_view(), name = 'journal'),
    path('salesreturn',views.salesreturnApiView.as_view(), name = 'journal'),
    path('salesreturn/<int:id>',views.salesreturnupdatedelview.as_view(), name = 'journal'),
    path('jvouccherno',views.journalordelatestview.as_view(), name = 'purchaseorder'),
    path('svouccherno',views.stockordelatestview.as_view(), name = 'purchaseorder'),
    path('pvouccherno',views.productionlatestview.as_view(), name = 'purchaseorder'),
    path('bvouccherno',views.bankordelatestview.as_view(), name = 'purchaseorder'),
    path('cvouccherno',views.cashordelatestview.as_view(), name = 'purchaseorder'),
    path('purchasereturn',views.PurchaseReturnApiView.as_view(),name = 'salesorder'),
    path('gstview',views.gstview.as_view(),name = 'salesorder'),    
    path('purchasereturn/<int:id>',views.PurchaseReturnupdatedelview.as_view(), name = 'salesorder'),
    path('purchasereturndetails',views.PurchaseOrderDetailsApiView.as_view(),name = 'salesorder'),
    path('purchasereturndetails/<int:id>',views.PurchaseOrderDetailsApiView.as_view(), name = 'salesorder'),
    path('prvoucherno',views.PurchaseReturnlatestview.as_view(), name = 'journal'),
    #path('trialbalance',views.TrialbalanceApiView.as_view(), name = 'Trialbalance'),
    #path('trialbalancebyaccounthead',views.TrialbalancebyaccountheadApiView.as_view(), name = 'Trialbalance'),
    #path('trialbalancebyaccount',views.TrialbalancebyaccountApiView.as_view(), name = 'Trialbalance'),
    path('Trialview',views.Trialview.as_view(), name = 'Trialbalance'),
    path('trialviewaccount',views.Trialviewaccount.as_view(), name = 'Trialbalance'),
    #path('daybook',views.daybookviewapi.as_view(), name = 'Trialbalance'),
    path('journalmain',views.journalmainApiView.as_view(), name = 'journal'),
    path('journalmain/<int:id>',views.journalmainupdateapiview.as_view(), name = 'journal'),
    path('saleinvoicebno/<int:billno>',views.salesOrderpreviousview.as_view(), name = 'journal'),
    path('saleorderbno/<int:billno>',views.saleOrderpreviousview.as_view(), name = 'journal'),

    path('purchasereturnbno/<int:billno>',views.PurchaseReturnpreviousview.as_view(), name = 'journal'),
    path('purchaseinvoicevno/<int:voucherno>',views.purchaseorderpreviousview.as_view(), name = 'journal'),
    path('purchaseordervno/<int:voucherno>',views.purchaseordernewpreviousview.as_view(), name = 'journal'),
    path('purchaseimportvno/<int:voucherno>',views.purchaseorderimportpreviousview.as_view(), name = 'journal'),
    path('journalmainvno/<int:voucherno>',views.journalmainpreviousapiview.as_view(), name = 'journal'),
    path('salesreturnvno/<int:voucherno>',views.salesreturnpreviousview.as_view(), name = 'journal'),
    path('stockmainvno/<int:voucherno>',views.stockmainpreviousapiview.as_view(), name = 'journal'),
    path('stockmain',views.stockmainApiView.as_view(), name = 'journal'),
    path('stockmainvno/<int:voucherno>',views.stockmainpreviousapiview.as_view(), name = 'journal'),
    #path('stockmain',views.stockmainApiView.as_view(), name = 'journal'),
    path('productionmainvno/<int:voucherno>',views.productionpreviousapiview.as_view(), name = 'journal'),
    path('productionmain',views.productionmainApiView.as_view(), name = 'journal'),
    path('production/<int:id>',views.productionmainupdateapiview.as_view(), name = 'journal'),
    path('stockmain/<int:id>',views.stockmainupdateapiview.as_view(), name = 'journal'),
    #path('stockviewapi',views.stockviewapi.as_view(), name = 'journal'),
    #path('purchasebook',views.purchasebyaccountapi.as_view(), name = 'purchasebook'),
    #path('salebook',views.salebyaccountapi.as_view(), name = 'salebok'),
    #path('cashbook',views.cbviewapi.as_view(), name = 'Trialbalance'),
    #path('ledgerbook',views.ledgerviewapi.as_view(), name = 'Trialbalance'),
    #path('ledgersummary',views.ledgersummarylatest.as_view(), name = 'Trialbalance'),
    #path('stockledgersummary',views.stockledgersummaryapi.as_view(), name = 'Trialbalance'),
    #path('stockledgerbook',views.stockledgerbookapi.as_view(), name = 'Trialbalance'),
    #path('incomeandexpensesstatement',views.incomeandexpensesstatement.as_view(), name = 'Trialbalance'),
    #path('gstr1b2bapi',views.gstr1b2bapi.as_view(), name = 'Trialbalance'),
    #path('gstr1b2baapi',views.gstr1b2baapi.as_view(), name = 'Trialbalance'),
    #path('gstr1b2clargeapi',views.gstr1b2clargeapi.as_view(), name = 'Trialbalance'),
    #path('gstr1b2csmallapi',views.gstr1b2csmallapi.as_view(), name = 'Trialbalance'),
    #path('gstr1hsnapi',views.gstrhsnapi.as_view(), name = 'Trialbalance'),
    path('purchasetaxtype',views.purchasetaxtypeApiView.as_view(), name = 'purchasetaxtype'),
    path('tdsmain',views.tdsmainApiView.as_view(), name = 'tdsmain'),
    path('tdsmain/<int:id>',views.tdsmainupdatedel.as_view(), name = 'tdsmain'),
    path('tdsmainvno/<int:voucherno>',views.tdsmainpreviousapiview.as_view(), name = 'tdsmainp'),
    path('tdsvoucherno',views.tdsordelatestview.as_view(), name = 'purchaseorder'),
    path('tdstype',views.tdstypeApiView.as_view(), name = 'purchaseorder'),
    path('tdscancel/<int:id>',views.tdsmaincancel.as_view(), name = 'tdsmain'),
    path('receiptvouchercancel/<int:id>',views.ReceiptVouchercancel.as_view(), name = 'tdsmain'),
    path('saleinvoicecancel/<int:id>',views.salesordercancel.as_view(), name = 'tdsmain'),
    path('saleordercancel/<int:id>',views.saleordercancel.as_view(), name = 'tdsmain'),
    path('jobworkcancel/<int:id>',views.jobworkchalancancel.as_view(), name = 'tdsmain'),
    path('gstservicescancel/<int:id>',views.gstservicescancel.as_view(), name = 'tdsmain'),
    path('purchaseinvoicecancel/<int:id>',views.purchaseordercancel.as_view(), name = 'tdsmain'),
    path('purchaseordercancel/<int:id>',views.newpurchaseordercancel.as_view(), name = 'tdsmain'),
    path('purchaseimportcancel/<int:id>',views.purchaseimportcancel.as_view(), name = 'tdsmain'),
    path('purchasereturncancel/<int:id>',views.purchasereturncancel.as_view(), name = 'tdsmain'),
    path('salesreturncancel/<int:id>',views.salesreturncancel.as_view(), name = 'tdsmain'),
    path('journalmaincancel/<int:id>',views.journalmaincancel.as_view(), name = 'tdsmain'),
    path('productioncancel/<int:id>',views.productionmaincancel.as_view(), name = 'tdsmain'),
    path('tdsmain1',views.tdsmainApiView1.as_view({'get': 'list'}), name = 'tdsmain'),
    #path('balancesheet',views.balancestatement.as_view(), name = 'Trialbalance'),
    path('balancestatementxl',views.balancestatementxl.as_view(), name = 'Trialbalance'),
    #path('tradingaccountstatement',views.tradingaccountstatement.as_view(), name = 'Trialbalance'),
    path('stockmaincancel',views.stockmaincancel.as_view(), name = 'Trialbalance'),
    #path('dashboardkpis',views.dashboardkpis.as_view(), name = 'Trialbalance'),
    #path('dashboardgraphkpis',views.dashboardgraphkpis.as_view(), name = 'Trialbalance'),
    path('tdsreturn',views.tdsreturnApiView.as_view(), name = 'Trialbalance'),
    path('tdslist',views.tdslist.as_view(), name = 'Trialbalance'),
    path('dcnote',views.debitcreditnoteApiView.as_view(), name = 'Trialbalance'),
    path('dcnote/<int:id>',views.debitcreditnoteupdatedelApiView.as_view(), name = 'Trialbalance'),
    path('dcnotebyvno/<int:voucherno>',views.debitcreditnotebyvoucherno.as_view(), name = 'Trialbalance'),
    path('dcnotelatestvno',views.debitcreditlatestvnoview.as_view(), name = 'Trialbalance'),
    path('debitcreditcancel/<int:id>',views.debitcreditcancel.as_view(), name = 'Trialbalance'),
    path('balancesheetclosing',views.balancesheetclosingapiView.as_view(), name = 'Trialbalance'),
    path('getgstindetails',views.getgstindetails.as_view(), name = 'Trialbalance'),
    path('InvoiceTypes',views.InvoiceTypeViewSet.as_view(), name = 'InvoiceTypeViewSet'),
    path('combinedapi',views.CombinedTypeApiView.as_view(), name = 'InvoiceTypeViewSet'),

    
    path('gstb2b',views.viewb2b.as_view(), name = 'gstb2b'),
    path('gstb2cl',views.viewb2clarge.as_view(), name = 'b2cLarge'),
    path('gstb2cs',views.viewb2cs.as_view(), name = 'gstb2cs'),
    path('gstbyhsn',views.gstbyhsn.as_view(), name = 'gstbyhsn'),
    path('gstbycdnr',views.viewcdnr.as_view(), name = 'gstbyhsn'),
    path('gstxls',views.CombinedB2B_B2CLarge.as_view(), name = 'gstbyhsn'),

    
    path('attachments/', PurchaseOrderAttachmentAPIView.as_view(), name='upload-attachment'),
    path('attachments/<int:purchase_order_id>/', PurchaseOrderAttachmentAPIView.as_view(), name='list-attachments'),
    path('attachments/download/<int:attachment_id>/', PurchaseOrderAttachmentDownloadAPIView.as_view(), name='download-attachment'),
    path('attachments/delete/<int:attachment_id>/', PurchaseOrderAttachmentDeleteAPIView.as_view(), name='delete-attachment'),
    #path('generate-invoice/', generate_invoice_pdf, name='generate-invoice'),
    

    

    
    #path('closingstock', views.closingstockView.as_view(), name='closingstockView'),
    #path('closingstockview', views.closingstocknew.as_view(), name='closingstockView--1'),
    path('sales-order-gst-summary/', views.SalesOrderGSTSummaryView.as_view(), name='sales-order-gst-summary'),
    path("sales-order/<int:id>/", views.SalesOrderenvoiceDetailView.as_view(), name="sales-order-detail"),
    path("distance", views.PincodeDistanceAPIView.as_view(), name="sales-order-detail"),
    path('default-values/', views.DefaultValuesByEntityListCreateAPIView.as_view(), name='default-values-list-create'),
    path('default-values/<int:pk>/', views.DefaultValuesByEntityRetrieveUpdateDestroyAPIView.as_view(), name='default-values-detail'),
    path('billnos/', views.BillNoListView.as_view(), name='billno-list'),
    path('months/', views.MonthListAPIView.as_view(), name='month-list'),
    path('paymentmodes/', views.PaymentmodesListAPIView.as_view(), name='paymentmodes-list'),
    path('settings/', views.SalesInvoiceSettingsView.as_view()),
    path('settings/<int:pk>/', views.SalesInvoiceSettingsView.as_view()),
    path('doctype/', views.DoctypeAPIView.as_view(), name='doctype-list'),       # GET list with optional ?entity=ID
    path('doctype/<int:pk>/', views.DoctypeAPIView.as_view(), name='doctype-detail'),  # GET specific doctype by ID

    path('getlatestreceiptvno/', views.GetReceiptNumberAPIView.as_view(), name='doctype-detail'),  # GET specific doctype by ID
    path('create-receipt-voucher/', views.CreateReceiptVoucherAPIView.as_view(), name='create-receipt-voucher'),
    path('salesorderslistbyaccountid/', views.SalesOrderHeaderListView.as_view(), name='sales-order-list'),
    path('receipt-vouchers/', views.ReceiptVoucherListCreateAPIView.as_view(), name='receipt-voucher-list-create'),
    path('receipt-vouchers/<int:pk>/', views.ReceiptVoucherDetailAPIView.as_view(), name='receipt-voucher-detail'),
    path('receiptvoucherpdf/<int:pk>/', views.ReceiptVoucherDetailPdfAPIView.as_view(), name='receipt-voucher-detail'),
    path('receiptvoucherbyvoucherid/', views.ReceiptVoucherLookupAPIView.as_view(), name='receipt-voucher-detail'),
    path('sales-orders/<int:pk>/pdf/', views.SalesOrderPDFViewlatest.as_view(), name='sales-order-pdf'),
    path('salesorder/update-adddetails/<int:pk>/', views.UpdateAddDetailsAPIView.as_view(), name='update-adddetails'),
    path('salesorder/get-adddetails/<int:pk>/', views.GetAddDetailsAPIView.as_view(), name='get-adddetails'),
    path('salesreturn/update-adddetails/<int:pk>/', views.UpdateAddDetailsAPIViewSR.as_view(), name='update-adddetails'),
    path('salesreturn/get-adddetails/<int:pk>/', views.GetAddDetailsAPIViewSR.as_view(), name='get-adddetails'),
    path('purchasereturn/update-adddetails/<int:pk>/', views.UpdateAddDetailsAPIViewPR.as_view(), name='update-adddetails'),
    path('purchasereturn/get-adddetails/<int:pk>/', views.GetAddDetailsAPIViewPR.as_view(), name='get-adddetails'),
    path('purchasereturnpdf/<int:id>',views.purchaseRerurnpdfview.as_view(), name = 'salesorder'),
    path('salereturnpdf/<int:id>',views.Salereturnpdfview.as_view(), name = 'salesorder'),

    
    # path('settings/purchase/', views.PurchaseSettingsView.as_view()),
    # path('settings/purchase/<int:pk>/', views.PurchaseSettingsView.as_view()),

    # path('settings/receipt/', views.ReceiptSettingsView.as_view()),
    # path('settings/receipt/<int:pk>/', views.ReceiptSettingsView.as_view()),

    

    

    


    

    

    


    
    
   
   
   
] 