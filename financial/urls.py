from django.urls import path
from financial import views


app_name = 'financial'

urlpatterns  = [

   
    path('accounthead',views.accountHeadApiView.as_view(),name = 'accounthead'),
    path('accounthead/<int:id>',views.accountHeadupdatedelApiView.as_view(), name = 'accountheadid'),
    path('account',views.accountApiView.as_view(),name ='account'),
    path('account/<int:id>',views.accountupdatedelApiView.as_view(),name = 'accountid'),
    path('accountcash',views.accountApiView2.as_view(),name ='account'),
    path('customaccounts',views.customApiView2.as_view(),name ='account'),
    path('accountbind',views.accountApiView3.as_view(),name ='account')


    


    
    
   
   
   
] 