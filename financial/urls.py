from django.urls import path
from financial import views
from .views_meta import (
    AccountChoicesAPIView,
    AccountFormMetaAPIView,
    AccountingMastersMetaAPIView,
    LedgerFormMetaAPIView,
)
from .views_ledger import (
    AccountHeadV2ListCreateAPIView,
    AccountHeadV2RetrieveUpdateDestroyAPIView,
    AccountProfileV2ListCreateAPIView,
    AccountProfileV2RetrieveUpdateDestroyAPIView,
    AccountTypeV2ListCreateAPIView,
    AccountTypeV2RetrieveUpdateDestroyAPIView,
    AccountListPostV2APIView,
    BaseAccountListV2APIView,
    LedgerBalanceListAPIView,
    LedgerListCreateAPIView,
    LedgerRetrieveUpdateDestroyAPIView,
    LedgerSimpleListAPIView,
    SimpleAccountsV2APIView,
)


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
    path('invoiceAccounts',views.InvoiceBindApiView.as_view(), name = 'Trialbalance'),
    path('accountList',views.AccountListNewApiView.as_view(), name = 'Trialbalance'),
    path('accountListPost',views.AccountListPostApiView.as_view(), name = 'Trialbalance'),
    path('accounttype',views.accounttypeApiView.as_view(), name = 'Trialbalance'),
    path('accounttypejson',views.accounttypejsonApiView.as_view(), name = 'Trialbalance'),

    
    path('getaccountdetailsbygst',views.GetGstinDetails.as_view(), name = 'unittypeid'),
    path('baseaccountlist/', views.AccountListView.as_view(), name='account-list'),
    path('baseaccountlistv2/', BaseAccountListV2APIView.as_view(), name='account-list-v2'),
    path('shipping-details/', views.ShippingDetailsListCreateView.as_view(), name='shipping-details-list-create'),
    path('shipping-details/<int:pk>/', views.ShippingDetailsRetrieveUpdateDestroyView.as_view(), name='shipping-details-detail'),
    path('shipping-details/account/<int:account_id>/', views.ShippingDetailsByAccountView.as_view(), name='shipping-details-by-account'),
    path('contact-details/', views.ContactDetailsListCreateView.as_view(), name='shipping-details-list-create'),
    path('contact-details/<int:pk>/', views.ContactDetailsRetrieveUpdateDestroyView.as_view(), name='shipping-details-detail'),
    path('contact-details/account/<int:account_id>/', views.ContactDetailsByAccountView.as_view(), name='shipping-details-by-account'),
    path('staticaccounts/', views.StaticAccountsAPIView.as_view()),
    path('staticaccounts/<int:pk>/', views.StaticAccountsAPIView.as_view()),
    path('staticaccount-mapping/', views.StaticAccountMappingListCreateView.as_view(), name='staticaccount-mapping-list-create'),
    path('staticaccount-mapping/<int:pk>/', views.StaticAccountMappingRetrieveUpdateDestroyView.as_view(), name='staticaccount-mapping-detail'),
    path('staticaccountslist/', views.StaticAccountFlatListView.as_view(), name='staticaccounts-flat-list'),
    path('top-account-head/', views.TopAccountHeadAPIView.as_view(), name='top-account-head'),
    path('accountheads/entity/<int:entity_id>/', views.AccountHeadListByEntityAPIView.as_view(), name='accounthead-list-by-entity'),   
    path("meta/account-choices/", AccountChoicesAPIView.as_view(), name="meta-account-choices"),
    path("meta/account-form/", AccountFormMetaAPIView.as_view(), name="meta-account-form"),
    path("meta/accounting-masters/", AccountingMastersMetaAPIView.as_view(), name="meta-accounting-masters"),
    path("meta/ledger-form/", LedgerFormMetaAPIView.as_view(), name="meta-ledger-form"),
    path("accounts/simple", views.SimpleAccountsAPIView.as_view()),
    path("accounts/simplev2", SimpleAccountsV2APIView.as_view(), name="account-simple-v2"),
    path("accountListPostV2", AccountListPostV2APIView.as_view(), name="account-list-post-v2"),
    path("accounttypes-v2", AccountTypeV2ListCreateAPIView.as_view(), name="accounttype-v2-list-create"),
    path("accounttypes-v2/<int:pk>", AccountTypeV2RetrieveUpdateDestroyAPIView.as_view(), name="accounttype-v2-detail"),
    path("accountheads-v2", AccountHeadV2ListCreateAPIView.as_view(), name="accounthead-v2-list-create"),
    path("accountheads-v2/<int:pk>", AccountHeadV2RetrieveUpdateDestroyAPIView.as_view(), name="accounthead-v2-detail"),
    # Parallel ledger-first APIs. These are additive and keep all legacy
    # financial endpoints intact while new screens move to Ledger.
    path("ledgers", LedgerListCreateAPIView.as_view(), name="ledger-list-create"),
    path("ledgers/<int:pk>", LedgerRetrieveUpdateDestroyAPIView.as_view(), name="ledger-detail"),
    path("ledgers/simple", LedgerSimpleListAPIView.as_view(), name="ledger-simple-list"),
    path("ledger-balances", LedgerBalanceListAPIView.as_view(), name="ledger-balance-list"),
    path("accounts-v2", AccountProfileV2ListCreateAPIView.as_view(), name="account-profile-v2-list-create"),
    path("accounts-v2/<int:pk>", AccountProfileV2RetrieveUpdateDestroyAPIView.as_view(), name="account-profile-v2-detail"),
 

    

    


    


    
    
   
   
   
] 
