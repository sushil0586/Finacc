from django.urls import path
from .views import LocalizedStringsAPIView

urlpatterns = [
    path("strings", LocalizedStringsAPIView.as_view(), name="localized-strings"),
]
