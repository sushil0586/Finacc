from django.urls import path
from financial import views


app_name = 'financial'

urlpatterns  = [

   
    path('accounthead',views.AccountHeadApiView.as_view(),name = 'accounthead'),
    path('accounthead/<int:id>',views.AccountHeadUpdateDeleteApiView.as_view(), name = 'accountheadid'),
    path('account',views.accountApiView.as_view(),name ='account'),
    path('account/<int:id>',views.accountupdatedelApiView.as_view(),name = 'accountid'),
    path('accountcash',views.accountApiView2.as_view(),name ='account'),
    path('customaccounts',views.CustomApiView2.as_view(),name ='account'),
    path('customaccountsnew',views.customApiView4.as_view(),name ='account'),
    path('customaccountservices',views.customApiView3.as_view(),name ='account'),
   # path('accountbind',views.accountApiView3.as_view(),name ='account'),
    path('accountheadbinding',views.accountheadApiView3.as_view(),name ='accounthead'),
    #path('accountList',views.accountListApiView.as_view(),name ='accounthead'),
    path('accountcode',views.AccountCodeLatestView.as_view(), name = 'purchaseorder'),
    path('accountbind',views.AccountBindApiView.as_view(), name = 'Trialbalance'),
    path('accountList',views.AccountListNewApiView.as_view(), name = 'Trialbalance'),
    path('accountListPost',views.AccountListPostApiView.as_view(), name = 'Trialbalance'),
    path('accounttype',views.accounttypeApiView.as_view(), name = 'Trialbalance'),
    path('getaccountdetailsbygst',views.GetGstinDetails.as_view(), name = 'unittypeid'),
    path('accountslist/', views.AccountListView.as_view(), name='account-list'),
    path('shipping-details/', views.ShippingDetailsListCreateView.as_view(), name='shipping-details-list-create'),
    path('shipping-details/<int:pk>/', views.ShippingDetailsRetrieveUpdateDestroyView.as_view(), name='shipping-details-detail'),
    path('shipping-details/account/<int:account_id>/', views.ShippingDetailsByAccountView.as_view(), name='shipping-details-by-account'),
    

    

    

    


    


    
    
   
   
   
] 