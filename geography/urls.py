from django.urls import path
from geography import views


app_name = 'geography'

urlpatterns  = [

   
    path('country',views.CountryApiView.as_view(),name = 'country'),
    path('country/<int:id>',views.CountryApiView.as_view(), name = 'countryid'),
    path('state', views.StateApiView.as_view() ,name = 'state'),
    path('state/<int:id>',views.StateApiView.as_view(), name = 'stateid'),
    path('district',views.DistrictApiView.as_view(),name = 'district'),
    path('district/<int:id>',views.DistrictApiView.as_view(), name = 'districtid'),
    path('city', views.CityApiView.as_view() ,name = 'city'),
    path('city/<int:id>',views.CityApiView.as_view(), name = 'cityid'),
   
   
   
    
   
] 