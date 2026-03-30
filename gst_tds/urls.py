from django.urls import path

from gst_tds.views import (
    GstTdsConfigAPIView,
    GstTdsContractLedgerListAPIView,
    GstTdsContractLedgerSummaryAPIView,
)


urlpatterns = [
    path("config/", GstTdsConfigAPIView.as_view(), name="gst-tds-config"),
    path("contract-ledgers/", GstTdsContractLedgerListAPIView.as_view(), name="gst-tds-contract-ledgers"),
    path("contract-ledgers/summary/", GstTdsContractLedgerSummaryAPIView.as_view(), name="gst-tds-contract-ledgers-summary"),
]
