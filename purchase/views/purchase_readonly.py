from rest_framework import generics, permissions, filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import serializers

from purchase.models.purchase_core import PurchaseInvoiceLine, PurchaseTaxSummary


class PurchaseInvoiceLineROSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchaseInvoiceLine
        fields = "__all__"


class PurchaseTaxSummaryROSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchaseTaxSummary
        fields = "__all__"


class PurchaseInvoiceLinesListAPIView(generics.ListAPIView):
    serializer_class = PurchaseInvoiceLineROSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["header", "taxability", "is_service", "gst_rate", "is_itc_eligible"]
    ordering_fields = ["header", "line_no", "id"]
    ordering = ["header", "line_no"]

    def get_queryset(self):
        return PurchaseInvoiceLine.objects.select_related("header", "product", "uom")


class PurchaseTaxSummaryListAPIView(generics.ListAPIView):
    serializer_class = PurchaseTaxSummaryROSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["header", "taxability", "is_service", "gst_rate", "is_reverse_charge"]
    ordering_fields = ["header", "gst_rate", "taxability"]
    ordering = ["header", "gst_rate"]

    def get_queryset(self):
        return PurchaseTaxSummary.objects.select_related("header")
