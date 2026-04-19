from django.urls import path

from .views import (
    RetailCloseBatchDetailAPIView,
    RetailCloseBatchListAPIView,
    RetailMetaAPIView,
    RetailSessionCloseAPIView,
    RetailSessionOpenAPIView,
    RetailTicketCompleteAPIView,
    RetailTicketDetailAPIView,
    RetailTicketListCreateAPIView,
)

app_name = "retail"

urlpatterns = [
    path("meta/", RetailMetaAPIView.as_view(), name="meta"),
    path("sessions/open/", RetailSessionOpenAPIView.as_view(), name="session-open"),
    path("sessions/<int:pk>/close/", RetailSessionCloseAPIView.as_view(), name="session-close"),
    path("close-batches/", RetailCloseBatchListAPIView.as_view(), name="close-batch-list"),
    path("close-batches/<int:pk>/", RetailCloseBatchDetailAPIView.as_view(), name="close-batch-detail"),
    path("tickets/", RetailTicketListCreateAPIView.as_view(), name="ticket-list-create"),
    path("tickets/<int:pk>/", RetailTicketDetailAPIView.as_view(), name="ticket-detail"),
    path("tickets/<int:pk>/complete/", RetailTicketCompleteAPIView.as_view(), name="ticket-complete"),
]
