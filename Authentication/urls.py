from Authentication import views
from django.urls import path

app_name = 'Authentication'

urlpatterns  = [

    path('register',views.RegisterApiView.as_view(), name = 'register'),
    path('login',views.LoginApiView.as_view(), name = 'login'),
    path('user',views.AuthApiView.as_view(), name = 'user'),
    path('changepassword',views.ChangePasswordView.as_view(), name = 'ChangePassword'),
    path('menus',views.MenusApiView.as_view(), name = 'MenusApiView'),
    path('submenus',views.subMenusApiView.as_view(), name = 'MenusApiView'),

    
]