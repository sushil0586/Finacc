from django.urls import path

from .views import DashboardHomeMetaAPIView


app_name = "dashboard_api"

urlpatterns = [
    path("home/meta/", DashboardHomeMetaAPIView.as_view(), name="home-meta"),
]

