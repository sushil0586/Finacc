from Authentication import views
from django.urls import path

app_name = 'Authentication'

urlpatterns  = [

    path('register',views.RegisterApiView.as_view(), name = 'register'),
    path('login',views.LoginApiView.as_view(), name = 'login'),
    path('logout',views.LogoutApiView.as_view(), name = 'logout'),
    path('refresh',views.RefreshTokenApiView.as_view(), name = 'refresh'),
    path('forgotpassword',views.ForgotPasswordApiView.as_view(), name = 'forgotpassword'),
    path('resetpassword',views.ResetPasswordApiView.as_view(), name = 'resetpassword'),
    path('request-email-verification',views.RequestEmailVerificationApiView.as_view(), name = 'request-email-verification'),
    path('resend-email-verification',views.ResendEmailVerificationApiView.as_view(), name = 'resend-email-verification'),
    path('verify-email',views.VerifyEmailApiView.as_view(), name = 'verify-email'),
    path('user',views.AuthApiView.as_view(), name = 'user'),
    path('me',views.AuthMeView.as_view(), name = 'me'),
    path('changepassword',views.ChangePasswordView.as_view(), name = 'ChangePassword'),

    
]

