from django.urls import path
from entity import views


app_name = 'entity'

urlpatterns  = [

    path('entityadd',views.entityAddApiView.as_view(),name = 'entityadd'),
    path('entity',views.userroleApiView.as_view(),name = 'entity'),
    path('entitylist',views.userroleApiView.as_view(),name = 'entitylist'),
    path('entity/<int:id>',views.userroleupdatedel.as_view(), name = 'entity1'),
    #path('album/<int:id>',views.Albumupdatedel.as_view(), name = 'Album2'),
    path('entityDetails', views.entityDetailsApiView.as_view() ,name = 'entityDetails'),
    path('entityDetails/<int:id>',views.entityDetailsApiView.as_view(), name = 'entityDetails1'),
    path('unittype', views.unitTypeApiView.as_view() ,name = 'unittype'),
    path('constitution', views.ConstitutionApiView.as_view() ,name = 'unittype'),
    path('role', views.roleApiView.as_view() ,name = 'unittype'),
    path('unittype/<int:id>',views.unitTypeApiView.as_view(), name = 'unittypeid'),
  #  path('user',views.AuthApiView.as_view(), name = 'user'),
    path('entityfy',views.EntityFinancialYearApiView.as_view(), name = 'user'),
    path('entityfylist',views.entityfinancialyeaListView.as_view(), name = 'user'),
    path('subentity',views.subentityApiView.as_view(),name = 'entityadd'),
    path('subentity/<int:id>',views.subentityupdatedelview.as_view(), name = 'unittypeid'),
    path('rolelatest',views.rolenewApiView.as_view(),name = 'entityadd'),
    path('rolelatest/<int:id>',views.rolenewupdatedelview.as_view(), name = 'unittypeid'),
    path('subentitybyentity',views.subentitybyentityApiView.as_view(), name = 'unittypeid'),
    path('menudetails',views.menudetails.as_view(), name = 'unittypeid'),
    path('roledetailsbyroleid',views.roledetails.as_view(), name = 'unittypeid'),
    path('entitydetailsbyuser',views.entitydetailsbyuser.as_view(), name = 'unittypeid'),
    path('userdetailsbyentity',views.userdetailsbyentity.as_view(), name = 'unittypeid'),
    path('userAddApiView',views.userAddApiView.as_view(), name = 'unittypeid'),
    path('getentitybygst',views.getgstindetails.as_view(), name = 'unittypeid'),
    path('getyearsbyentity',views.EntityFinancialYearView.as_view(), name = 'unittypeid'),
    path('entitymasterdetails',views.MasterDataView.as_view(), name = 'unittypeid'),
    path('bankaccounts/', views.BankAccountCreateView.as_view(), name='bankaccount-create'),
    path('bankaccounts/<int:pk>/', views.BankAccountDetailView.as_view(), name='bankaccount-detail'),
    path('bankaccounts/entity/<int:entity_id>/', views.BankAccountListByEntityView.as_view(), name='bankaccount-by-entity'),
    path('entity/create/', views.EntityCreateUpdateAPIView.as_view(), name='entity-create'),
    path('entity/update/<int:pk>/', views.EntityCreateUpdateAPIView.as_view(), name='entity-update'),
    path('entity/<int:id>/', views.EntityRetrieveAPIView.as_view(), name='entity-detail'),
    

    

    

    

    

    

    

    

    # path('entityuser', views.entityUserApiView.as_view() ,name = 'unittype'),
    # path('entityuser/<int:id>',views.entityUserApiView.as_view(), name = 'unittypeid'),
    # path('entityuseradd', views.entityUseraddApiView .as_view() ,name = 'unittype'),
   
   
    
   
] 